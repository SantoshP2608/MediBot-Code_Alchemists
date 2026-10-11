import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.models.schemas import TurnUpdate
from backend.services.conversation import Conversation, process_message


def turn(intents=None, medicines=None, relation='new_request',
         intent_operation='replace', medicine_operation='replace', question=None):
    return TurnUpdate(relation=relation, intent_operation=intent_operation,
                      intents=intents or [], medicine_operation=medicine_operation,
                      medicines=medicines or [], unresolved_question=question)


def product(name='Example', strength=None):
    return {'name': name, 'strength': strength}


class ClarificationTests(unittest.TestCase):
    def setUp(self):
        self.state = Conversation()
        self.database = (
            ('example 500 tablet', {'name': 'Example 500 Tablet', 'regulatory': 'OTC',
                                    'side_effects': ['Effect 500'], 'uses': ['Use 500']}),
            ('example 650 tablet', {'name': 'Example 650 Tablet', 'regulatory': 'OTC',
                                    'side_effects': ['Effect 650'], 'uses': ['Use 650']}),
        )
        self.lookup = patch('backend.data.medicine_database.load_database', return_value=self.database)
        self.lookup.start()
        self.addCleanup(self.lookup.stop)

    def send(self, message, update):
        with patch('backend.services.conversation.extract_query', return_value=update):
            return process_message(self.state, message)[1]

    def test_medicine_reply_keeps_intent_and_does_not_repeat_old_question(self):
        first = self.send('Side effects?', turn(['side_effects']))
        self.assertEqual(first['reason'], 'missing_medicine')
        reply = turn(medicines=[product('Example', '650')], relation='continuation',
                     intent_operation='keep', question=first['message'])
        result = self.send('Example 650', reply)
        self.assertEqual(result['action'], 'response')
        self.assertEqual(result['results'][0]['intent'], 'side_effects')
        self.assertEqual(result['results'][0]['data'][0]['side_effects'], ['Effect 650'])
        self.assertIsNone(self.state.pending_extraction)

    def test_strength_reply_uses_stored_product_and_candidates(self):
        first = self.send('Example side effects', turn(['side_effects'], [product()]))
        self.assertEqual(first['reason'], 'ambiguous_medicine')
        self.assertEqual(len(first['candidates']), 2)
        with patch('backend.services.conversation.extract_query', return_value=turn(
                medicines=[product('Example', '650')], relation='continuation',
                intent_operation='keep')) as model:
            result = process_message(self.state, '650')[1]
        pending = model.call_args.kwargs['pending_state']
        self.assertEqual(pending['medicines'], [product()])
        self.assertEqual(pending['candidates'], first['candidates'])
        self.assertEqual(result['action'], 'response')

    def test_replacing_intent_updates_pending_request_even_if_still_missing_medicine(self):
        self.send('Side effects?', turn(['side_effects']))
        result = self.send('Uses instead', turn(['uses_of_medicine'], relation='continuation',
                          medicine_operation='keep'))
        self.assertEqual(result['reason'], 'missing_medicine')
        self.assertEqual(self.state.pending_request, 'Uses instead')
        self.assertEqual(self.state.pending_extraction.intents, ['uses_of_medicine'])
        result = self.send('Example 650', turn(medicines=[product('Example', '650')],
                           relation='continuation', intent_operation='keep'))
        self.assertEqual(result['results'][0]['intent'], 'uses_of_medicine')

    def test_adding_intent_keeps_existing_intent_and_medicine(self):
        self.send('Example side effects', turn(['side_effects'], [product()]))
        self.send('Also its uses', turn(['uses_of_medicine'], relation='continuation',
                  intent_operation='add', medicine_operation='keep'))
        self.assertEqual(self.state.pending_extraction.intents, ['side_effects', 'uses_of_medicine'])
        self.assertEqual(self.state.pending_extraction.medicines[0].name, 'Example')
        result = self.send('Example 650', turn(medicines=[product('Example', '650')],
                           relation='continuation', intent_operation='keep'))
        self.assertEqual([r['intent'] for r in result['results']], ['side_effects', 'uses_of_medicine'])

    def test_new_topic_discards_pending_medicine_and_history_for_answer(self):
        self.send('Example side effects', turn(['side_effects'], [product()]))
        with patch('backend.llm.chatbot.get_response', return_value='Sleep information') as chat:
            result = self.send('Forget that. Tell me about sleep', turn(['general_health']))
        self.assertEqual(result['action'], 'response')
        chat.assert_called_once_with('Forget that. Tell me about sleep', previous_messages=[])
        self.assertIsNone(self.state.pending_extraction)

    def test_new_task_requiring_clarification_replaces_entire_old_task(self):
        self.send('Example side effects', turn(['side_effects'], [product()]))
        self.send('Different question: compare Unknown prices',
                  turn(['price_comparison'], [product('Unknown')]))
        self.assertEqual(self.state.pending_extraction.intents, ['price_comparison'])
        self.assertEqual(self.state.pending_extraction.medicines[0].name, 'Unknown')
        self.assertEqual(self.state.pending_request, 'Different question: compare Unknown prices')

    def test_medicine_without_intent_asks_for_intent_then_retains_product(self):
        result = self.send('Example 650', turn(medicines=[product('Example', '650')]))
        self.assertEqual(result['reason'], 'missing_intent')
        result = self.send('Uses', turn(['uses_of_medicine'], relation='continuation',
                                      medicine_operation='keep'))
        self.assertEqual(result['results'][0]['data'][0]['uses'], ['Use 650'])

    def test_repeated_clarification_explains_obstacle_then_clears_stalled_task(self):
        self.send('Side effects?', turn(['side_effects']))
        reply = turn(relation='continuation', intent_operation='keep', medicine_operation='keep')
        second = self.send('Not sure', reply)
        self.assertIn('missing information', second['message'])
        third = self.send('Still not sure', reply)
        self.assertEqual(third['reason'], 'clarification_stalled')
        self.assertIsNone(self.state.pending_extraction)

    def test_unclear_answer_to_missing_intent_remains_clarification_not_other_block(self):
        self.send('Example 650', turn(medicines=[product('Example', '650')]))
        result = self.send('Not sure', turn(relation='continuation', intent_operation='keep',
                                           medicine_operation='keep'))
        self.assertEqual(result['action'], 'clarify')
        self.assertEqual(result['reason'], 'missing_intent')

    def test_correcting_product_drops_old_product_and_strength(self):
        self.send('Unknown 500 side effects', turn(['side_effects'], [product('Unknown', '500')]))
        result = self.send('Actually Example 650', turn(medicines=[product('Example', '650')],
                           relation='continuation', intent_operation='keep'))
        self.assertEqual(result['action'], 'response')
        self.assertEqual(len(result['results'][0]['data']), 1)
        self.assertEqual(result['results'][0]['data'][0]['medicine'], 'Example 650 Tablet')

    def test_multi_medicine_clarification_preserves_both_products(self):
        self.send('Side effects of Example and Example 650', turn(['side_effects'],
                  [product(), product('Example', '650')]))
        result = self.send('The first is Example 500', turn(
            medicines=[product('Example', '500'), product('Example', '650')],
            relation='continuation', intent_operation='keep'))
        self.assertEqual(result['action'], 'response')
        self.assertEqual([r['medicine'] for r in result['results'][0]['data']],
                         ['Example 500 Tablet', 'Example 650 Tablet'])

    def test_missing_regulatory_data_does_not_ask_user_to_fix_database(self):
        with patch('backend.data.medicine_database.load_database', return_value=(
                ('unknown tablet', {'name': 'Unknown Tablet'}),)):
            result = self.send('Unknown Tablet side effects',
                               turn(['side_effects'], [product('Unknown Tablet')]))
        self.assertEqual(result['action'], 'error')
        self.assertEqual(result['reason'], 'unknown_regulatory_status')
        self.assertIsNone(self.state.pending_extraction)

    def test_blocked_intent_cannot_be_lost_by_keep_operation(self):
        self.send('Side effects?', turn(['side_effects']))
        result = self.send('Tell me how to take it', turn(['usage_information'],
                           relation='continuation', intent_operation='keep', medicine_operation='keep'))
        self.assertEqual(result['action'], 'block')
        self.assertIsNone(self.state.pending_extraction)

    def test_schedule_x_wins_even_when_intent_missing(self):
        with patch('backend.data.medicine_database.load_database', return_value=(
                ('restricted tablet', {'name': 'Restricted Tablet', 'regulatory': 'Schedule X'}),)):
            result = self.send('Restricted Tablet', turn(medicines=[product('Restricted Tablet')]))
        self.assertEqual(result['reason'], 'schedule_x')
        self.assertIsNone(result['message'])

    def test_failed_model_call_leaves_pending_state_for_retry(self):
        self.send('Side effects?', turn(['side_effects']))
        pending = self.state.pending_extraction.model_dump()
        with patch('backend.services.conversation.extract_query', side_effect=ConnectionError()), \
                patch('backend.services.conversation.logger.exception'):
            result = process_message(self.state, 'Example 650')[1]
        self.assertEqual(result['action'], 'error')
        self.assertEqual(self.state.pending_extraction.model_dump(), pending)
        self.assertEqual(self.state.previous_messages, ['Side effects?'])

    def test_http_uses_turn_schema_and_preserves_retry_idempotency(self):
        updates = [turn(['side_effects']), turn(medicines=[product('Example', '650')],
                   relation='continuation', intent_operation='keep')]
        responses = [SimpleNamespace(message=SimpleNamespace(content=u.model_dump_json())) for u in updates]
        client = TestClient(create_app())
        session, request = str(uuid4()), str(uuid4())
        with patch('backend.llm.extractor.client.chat', side_effect=responses) as chat:
            first = client.post('/api/chat', json={'message': 'Side effects?',
                                'session_id': session, 'request_id': str(uuid4())})
            payload = {'message': 'Example 650', 'session_id': session, 'request_id': request}
            second = client.post('/api/chat', json=payload)
            retry = client.post('/api/chat', json=payload)
        self.assertEqual(first.json()['result']['action'], 'clarify')
        self.assertEqual(second.json()['result']['action'], 'response')
        self.assertEqual(second.json(), retry.json())
        self.assertEqual(chat.call_count, 2)
        self.assertEqual(chat.call_args.kwargs['format'], TurnUpdate.model_json_schema())
        context = json.loads(chat.call_args.kwargs['messages'][1]['content'])
        self.assertEqual(context['pending_state']['intents'], ['side_effects'])


if __name__ == '__main__':
    unittest.main()
