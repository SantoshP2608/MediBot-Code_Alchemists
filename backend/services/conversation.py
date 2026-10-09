"""Conversation processing shared by the CLI and HTTP interface."""
from dataclasses import dataclass, field
import logging

from backend.config.settings import CONSTANTS
from backend.llm.extractor import extract_query
from backend.services.response import handle_response
from backend.safety.safety_guard import check_safety, make_result

logger = logging.getLogger(__name__)


@dataclass
class Conversation:
    previous_messages: list[str] = field(default_factory=list)
    pending_request: str | None = None
    clarification_question: str | None = None


def process_message(state, message):
    extraction = None
    try:
        extraction = extract_query(message, previous_messages=state.previous_messages,
                                   pending_request=state.pending_request,
                                   clarification_question=state.clarification_question)
        result = handle_response(extraction, message, state.previous_messages)
        if result['action'] == 'clarify':
            state.pending_request = state.pending_request or message
            state.clarification_question = result['message']
        else:
            state.pending_request = state.clarification_question = None
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
