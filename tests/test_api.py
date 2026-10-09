import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient
from backend.api.app import create_app
from backend.config.settings import CONSTANTS
from backend.models.schemas import Extraction
from backend.services.sessions import SessionCapacityError, SessionStore


def extraction(medicines=None, intents=None, question=None):
    return Extraction(medicines=medicines or [], intents=intents or ['side_effects'],
                      needs_clarification=bool(question), clarification_question=question)


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.store = SessionStore()
        self.client = TestClient(create_app(self.store))
        self.session = str(uuid4())

    def send(self, text='Question', session=None, request=None):
        return self.client.post('/api/chat', json={'message': text,
            'session_id': session or self.session, 'request_id': request or str(uuid4())})

    def test_health_and_invalid_requests_do_not_call_model(self):
        self.assertEqual(self.client.get('/api/health').json(), {'status': 'ok'})
        with patch('backend.services.conversation.extract_query') as model:
            for message in ['', '   ', 'a' * (CONSTANTS['api']['max_message_length'] + 1), 42]:
                self.assertEqual(self.send(message).status_code, 422)
            self.assertEqual(self.send(session='bad UUID').status_code, 422)
            self.assertEqual(self.client.post('/api/chat', json={'message': 'ok',
                'request_id': str(uuid4()), 'intents': ['general_health']}).status_code, 422)
        model.assert_not_called()

    def test_clarification_preserves_context_and_sessions_are_isolated(self):
        with patch('backend.services.conversation.extract_query', side_effect=[
                extraction(question='Which medicine?'), extraction(intents=['availability']),
                extraction(intents=['availability'])]) as model:
            first = self.send('Side effects?')
            self.assertEqual(first.json()['result']['action'], 'clarify')
            self.assertEqual(first.headers['cache-control'], 'no-store')
            self.send('Stock instead?')
            self.send('Other chat', session=str(uuid4()))
        self.assertEqual(model.call_args_list[1].kwargs['pending_request'], 'Side effects?')
        self.assertEqual(model.call_args_list[1].kwargs['clarification_question'], 'Which medicine?')
        self.assertEqual(model.call_args_list[2].kwargs['previous_messages'], [])
        self.assertIsNone(self.store.sessions[self.session].conversation.pending_request)

    def test_retries_are_idempotent_and_id_cannot_change_message(self):
        request = str(uuid4())
        with patch('backend.services.conversation.extract_query', return_value=extraction(intents=['availability'])) as model:
            first = self.send(request=request)
            second = self.send(request=request)
            conflict = self.send('Different', request=request)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(conflict.status_code, 409)
        model.assert_called_once()
        self.assertEqual(self.store.sessions[self.session].conversation.previous_messages, ['Question'])

    def test_failures_do_not_advance_context_and_can_be_retried(self):
        request = str(uuid4())
        with patch('backend.services.conversation.extract_query', side_effect=[
                RuntimeError('offline'), extraction(intents=['availability'])]) as model, \
                patch('backend.services.conversation.logger.exception'):
            first = self.send(request=request)
            self.assertEqual(first.json()['result']['action'], 'error')
            self.assertEqual(self.store.sessions[self.session].conversation.previous_messages, [])
            second = self.send(request=request)
        self.assertEqual(second.json()['result']['action'], 'block')
        self.assertEqual(model.call_count, 2)

    def test_schedule_rules_and_database_information_through_http(self):
        for schedule in ['OTC', 'Schedule H', 'Schedule G', 'Schedule X']:
            with self.subTest(schedule=schedule):
                database = (('example tablet', {'name': 'Example Tablet', 'regulatory': schedule,
                            'side_effects': ['Example effect'], 'uses': ['Example use']}),)
                answer = extraction([{'name': 'Example Tablet', 'strength': None}],
                                    ['side_effects', 'uses_of_medicine'])
                with patch('backend.services.conversation.extract_query', return_value=answer), \
                        patch('backend.data.medicine_database.load_database', return_value=database):
                    result = self.send().json()['result']
                if schedule == 'Schedule X':
                    self.assertEqual(result['action'], 'block')
                    self.assertEqual(result['reason'], 'schedule_x')
                    self.assertIsNone(result['message'])
                    self.assertNotIn('results', result)
                else:
                    self.assertEqual(result['action'], 'response')
                    self.assertEqual(result['results'][0]['data'][0]['side_effects'], ['Example effect'])
                    self.assertEqual(result['results'][1]['data'][0]['uses'], ['Example use'])
                    self.assertEqual('disclaimer' in result, schedule != 'OTC')

    def test_general_health_without_medicine(self):
        with patch('backend.services.conversation.extract_query', return_value=extraction(intents=['general_health'])), \
                patch('backend.llm.chatbot.get_response', return_value='General health answer'):
            result = self.send('Tell me about sleep').json()['result']
        self.assertEqual(result['results'][0]['data'], 'General health answer')

    def test_price_failure_keeps_h_g_disclaimer_and_pending_context(self):
        database = (('example tablet', {'name': 'Example Tablet', 'regulatory': 'Schedule H'}),)
        answer = extraction([{'name': 'Example Tablet', 'strength': None}], ['price_comparison'])
        with patch('backend.services.conversation.extract_query', return_value=answer), \
                patch('backend.data.medicine_database.load_database', return_value=database), \
                patch('backend.services.price.get_prices', side_effect=RuntimeError('offline')), \
                patch('backend.services.conversation.logger.exception'):
            result = self.send().json()['result']
        self.assertEqual(result['action'], 'error')
        self.assertEqual(result['disclaimer'], CONSTANTS['regulatory']['doctor_disclaimer'])
        self.assertEqual(self.store.sessions[self.session].conversation.previous_messages, [])

    def test_prices_and_alternatives_use_same_quotes_and_never_return_internal_continue(self):
        medicine = {'name': 'Example Tablet', 'regulatory': 'OTC', 'substitutes': ['Alternative Tablet'],
                    'composition': [{'drug': 'Example', 'strength': '650mg'}]}
        alternative = {**medicine, 'name': 'Alternative Tablet', 'substitutes': []}
        database = (('example tablet', medicine), ('alternative tablet', alternative))
        answer = extraction([{'name': 'Example Tablet', 'strength': None}], ['price_comparison', 'alternative_search'])
        with patch('backend.services.conversation.extract_query', return_value=answer), \
                patch('backend.data.medicine_database.load_database', return_value=database), \
                patch('backend.services.price.get_prices', return_value=[
                    {'medicine': name, 'status': 'no_prices', 'quotes': []}
                    for name in ['Example Tablet', 'Alternative Tablet']]) as prices:
            result = self.send().json()['result']
        self.assertEqual(result['action'], 'response')
        self.assertNotIn('resolved_medicines', result)
        self.assertEqual(result['results'][0]['data'], result['results'][1]['data'])
        comparison = result['results'][0]['data'][0]
        self.assertNotIn('max_potential_savings_percent', comparison)
        self.assertEqual(comparison['alternatives'][0]['prices']['quotes'], [])
        self.assertEqual(prices.call_args.args[0], ['Example Tablet', 'Alternative Tablet'])
        prices.assert_called_once()

    def test_missing_session_id_creates_anonymous_session_and_cors_allows_frontend(self):
        with patch('backend.services.conversation.extract_query', return_value=extraction(intents=['availability'])):
            result = self.client.post('/api/chat', json={'message': 'Availability?', 'request_id': str(uuid4())})
        self.assertIn(result.json()['session_id'], self.store.sessions)
        allowed = self.client.options('/api/chat', headers={'Origin': 'http://localhost:5173',
            'Access-Control-Request-Method': 'POST', 'Access-Control-Request-Headers': 'Content-Type'})
        self.assertEqual(allowed.headers['access-control-allow-origin'], 'http://localhost:5173')
        denied = self.client.options('/api/chat', headers={'Origin': 'http://untrusted.example',
            'Access-Control-Request-Method': 'POST'})
        self.assertNotIn('access-control-allow-origin', denied.headers)

    def test_concurrent_retry_runs_once(self):
        started, release = Event(), Event()
        request = str(uuid4())
        def extract(*args, **kwargs):
            started.set()
            self.assertTrue(release.wait(5))
            return extraction(intents=['availability'])
        with patch('backend.services.conversation.extract_query', side_effect=extract) as model:
            with ThreadPoolExecutor(max_workers=2) as pool:
                first = pool.submit(self.send, request=request)
                self.assertTrue(started.wait(5))
                second = pool.submit(self.send, request=request)
                release.set()
                self.assertEqual(first.result().json(), second.result().json())
        model.assert_called_once()

    def test_session_expiration_capacity_and_active_session_protection(self):
        now = [0]
        store = SessionStore(clock=lambda: now[0])
        with patch.dict(CONSTANTS['api'], max_sessions=1, session_ttl_seconds=10):
            with store.acquire('one'):
                now[0] = 20
                with self.assertRaises(SessionCapacityError):
                    with store.acquire('two'):
                        pass
            now[0] = 31
            with store.acquire('two'):
                self.assertNotIn('one', store.sessions)
        with patch.dict(CONSTANTS['api'], max_sessions=0):
            response = self.send()
        self.assertEqual(response.status_code, 503)


if __name__ == '__main__':
    unittest.main()
