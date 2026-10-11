"""Conversation processing shared by the CLI and HTTP interface."""
from dataclasses import dataclass, field
import logging
from uuid import uuid4

from backend.config.settings import CONSTANTS
from backend.llm.extractor import extract_turn as extract_query
from backend.models.schemas import BLOCKED_INTENTS, Extraction, Medicine, TurnUpdate
from backend.data.medicine_database import explicit_medicine_mentions, find_medicine, suggest_products
from backend.services.response import handle_response
from backend.safety.safety_guard import check_safety, make_result

logger = logging.getLogger(__name__)


@dataclass
class Conversation:
    previous_messages: list[str] = field(default_factory=list)
    pending_request: str | None = None
    clarification_question: str | None = None
    pending_extraction: Extraction | None = None
    clarification_reason: str | None = None
    candidates: list[str] = field(default_factory=list)
    clarification_repeats: int = 0
    missing_intent: bool = False
    selection_offer: str | None = None
    selection_choices: dict[str, Medicine] = field(default_factory=dict)
    selection_medicine_index: int | None = None

    def clear_pending(self):
        self.pending_request = self.clarification_question = None
        self.pending_extraction = self.clarification_reason = None
        self.candidates = []
        self.clarification_repeats = 0
        self.missing_intent = False
        self.selection_offer = None
        self.selection_choices = {}
        self.selection_medicine_index = None


def offer_products(state, extraction, result):
    """Bind product choices to the current unresolved medicine and task."""
    state.selection_offer = None
    state.selection_choices = {}
    state.selection_medicine_index = None
    if result['reason'] not in {'ambiguous_medicine', 'medicine_not_found'}:
        return
    for index, medicine in enumerate(extraction.medicines):
        if len(find_medicine(medicine)) == 1:
            continue
        records = suggest_products(medicine)
        if not records:
            return
        state.selection_offer = str(uuid4())
        state.selection_medicine_index = index
        choices = []
        for record in records:
            product_id = str(uuid4())
            state.selection_choices[product_id] = Medicine(name=record['name'], strength=None)
            composition = record.get('composition', [])
            choices.append({'product_id': product_id, 'name': record['name'],
                            'composition': composition, 'combination': len(composition) > 1})
        result['selection_offer'] = state.selection_offer
        result['medicine_choices'] = choices
        result['message'] = CONSTANTS['messages']['select_medicine']
        return


def process_selection(state, product_id, offer_id):
    if (not state.pending_extraction or state.selection_offer != offer_id
            or product_id not in state.selection_choices or state.selection_medicine_index is None):
        raise ValueError(CONSTANTS['messages']['stale_selection'])
    medicine = state.selection_choices[product_id]
    return process_message(state, medicine.name, selected_medicine=medicine)


def resolve_turn(turn, pending, pending_missing_intent=False):
    """Merge intent operations deterministically; revalidate medicines downstream."""
    related = turn.relation == 'continuation' and pending is not None
    intents = list(pending.intents) if related and not pending_missing_intent else []
    if turn.intent_operation == 'replace' or not related:
        intents = list(turn.intents)
    elif turn.intent_operation == 'add':
        intents = list(dict.fromkeys(intents + turn.intents))
    # Never drop newly detected prohibited intents, even if the operation is keep.
    intents = list(dict.fromkeys(intents + [i for i in turn.intents if i in BLOCKED_INTENTS]))
    medicines = (pending.medicines + turn.medicines
                 if related and turn.medicine_operation == 'keep' else turn.medicines)
    question = (turn.unresolved_question or '').strip() or None
    return Extraction(medicines=medicines, intents=intents or ['other'],
                      needs_clarification=bool(question), clarification_question=question), not intents


def process_message(state, message, selected_medicine=None):
    extraction = None
    try:
        pending_state = None
        if state.pending_extraction is not None:
            pending_state = state.pending_extraction.model_dump() | {
                'reason': state.clarification_reason, 'candidates': state.candidates,
            }
            if state.missing_intent:
                pending_state['intents'] = []
        if selected_medicine is not None:
            medicines = list(state.pending_extraction.medicines)
            medicines[state.selection_medicine_index] = selected_medicine
            turn = Extraction(**(state.pending_extraction.model_dump() | {
                'medicines': medicines, 'needs_clarification': False, 'clarification_question': None,
            }))
        else:
            turn = extract_query(message, previous_messages=state.previous_messages,
                                   pending_request=state.pending_request,
                                   clarification_question=state.clarification_question,
                                   pending_state=pending_state)
        new_request = isinstance(turn, TurnUpdate) and turn.relation == 'new_request'
        missing_intent = False
        if isinstance(turn, TurnUpdate):
            extraction, missing_intent = resolve_turn(turn, state.pending_extraction, state.missing_intent)
            # A supplied product is validated by the database, not by repeating
            # the model's old medicine question. Other ambiguity still matters.
            if (not new_request and turn.intent_operation == 'keep'
                    and turn.medicine_operation == 'replace' and turn.medicines
                    and state.clarification_reason in {
                        'missing_medicine', 'missing_medicine_name',
                        'medicine_not_found', 'ambiguous_medicine'}):
                extraction = Extraction(**(extraction.model_dump() | {
                    'needs_clarification': False, 'clarification_question': None,
                }))
        else:
            extraction = turn
        if (selected_medicine is None and not extraction.medicines
                and set(extraction.intents).intersection({
                    'price_comparison', 'alternative_search', 'side_effects', 'uses_of_medicine'})):
            mentions = explicit_medicine_mentions(message)
            if mentions:
                extraction = Extraction(**(extraction.model_dump() | {'medicines': mentions}))
        effective_message = message
        if not new_request and state.pending_request:
            effective_message = state.pending_request + '\nClarification reply: ' + message
        if missing_intent:
            safety = check_safety(extraction)
            if safety['reason'] == 'schedule_x':
                result = safety
            else:
                result = make_result('clarify', 'missing_intent',
                                     extraction.clarification_question or CONSTANTS['messages']['missing_intent'])
                if safety.get('disclaimer'):
                    result['disclaimer'] = safety['disclaimer']
        else:
            result = handle_response(extraction, effective_message,
                                     [] if new_request else state.previous_messages)
        if result['action'] == 'clarify':
            question = result['message']
            same = (not new_request and state.pending_extraction is not None
                    and state.pending_extraction.medicines == extraction.medicines
                    and state.pending_extraction.intents == extraction.intents
                    and state.clarification_reason == result['reason'])
            state.clarification_repeats = state.clarification_repeats + 1 if same else 0
            if state.clarification_repeats:
                result['message'] = CONSTANTS['messages']['clarification_no_progress'].format(
                    question=result['message'])
            if new_request or not state.pending_request or (
                    isinstance(turn, TurnUpdate) and turn.intent_operation != 'keep'):
                state.pending_request = message
            state.pending_extraction = extraction
            state.missing_intent = missing_intent
            state.clarification_question = question
            state.clarification_reason = result['reason']
            state.candidates = result.get('candidates', [])
            offer_products(state, extraction, result)
            state.clarification_question = result['message']
            if state.clarification_repeats >= 2:
                result = make_result('error', 'clarification_stalled',
                                     CONSTANTS['messages']['clarification_stalled']) | {
                    key: value for key, value in result.items() if key == 'disclaimer'
                }
                state.clear_pending()
        else:
            state.clear_pending()
        state.previous_messages = (state.previous_messages + [message])[-CONSTANTS['ollama']['history_limit']:]
        return extraction, result
    except Exception:
        logger.exception(CONSTANTS['messages']['request_failure_log'])
        result = make_result('error', 'request_processing_failed', CONSTANTS['messages']['request_failed'])
        if extraction is not None:
            try:
                safety = check_safety(extraction)
                if safety['reason'] == 'schedule_x':
                    return None, safety
                if safety.get('disclaimer'):
                    result['disclaimer'] = safety['disclaimer']
            except Exception:
                logger.exception(CONSTANTS['messages']['request_failure_log'])
        return None, result
