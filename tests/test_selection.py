import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.api.app import create_app
from backend.data.medicine_database import explicit_medicine_mentions, normalize, suggest_products
from backend.models.schemas import Extraction, Medicine


def record(name, drugs=None, category='OTC'):
    return {'name': name, 'composition': drugs or [{'drug': 'Paracetamol', 'strength': '500mg'}],
            'regulatory': category, 'side_effects': ['Example effect'], 'uses': ['Example use']}


class SelectionTests(unittest.TestCase):
    def setUp(self):
        self.rows = [record('Zed 500 Tablet'), record('Pure 500 Tablet'),
                     record('Alpha Plus Tablet', [{'drug': 'Paracetamol', 'strength': '500mg'},
                                                 {'drug': 'Other', 'strength': '100mg'}]),
                     record('Hidden Tablet', category='Schedule X'),
                     record('Unverified Tablet', category='Unknown')]
        self.database = patch('backend.data.medicine_database.load_database',
                              side_effect=lambda: tuple((normalize(r['name']), r) for r in self.rows))
        self.database.start()
        self.addCleanup(self.database.stop)
        self.client = TestClient(create_app())
        self.session = str(uuid4())

    def chat(self, intents=None, medicines=None, text='Price of paracetamol'):
        extraction = Extraction(medicines=medicines or [Medicine(name='paracetamol', strength=None)],
                                intents=intents or ['price_comparison'], needs_clarification=False,
                                clarification_question=None)
        with patch('backend.services.conversation.extract_query', return_value=extraction):
            return self.client.post('/api/chat', json={'message': text,
                'session_id': self.session, 'request_id': str(uuid4())}).json()['result']

    def selection_payload(self, result, choice=0):
        return {'session_id': self.session, 'request_id': str(uuid4()),
                'selection_offer': result['selection_offer'],
                'product_id': result['medicine_choices'][choice]['product_id']}

    def test_ingredient_search_sorts_single_products_before_combinations_and_excludes_restricted(self):
        result = self.chat()
        choices = result['medicine_choices']
        self.assertEqual([c['name'] for c in choices],
                         ['Pure 500 Tablet', 'Zed 500 Tablet', 'Alpha Plus Tablet'])
        self.assertEqual([c['combination'] for c in choices], [False, False, True])
        self.assertEqual(choices[0]['composition'][0]['strength'], '500mg')
        self.assertEqual(result['action'], 'clarify')

    def test_selection_retains_price_intent_skips_extraction_and_retries_once(self):
        result = self.chat()
        payload = self.selection_payload(result)
        with patch('backend.services.conversation.extract_query') as model, \
                patch('backend.services.price.get_prices', return_value=[]) as prices:
            selected = self.client.post('/api/select', json=payload)
            retry = self.client.post('/api/select', json=payload)
        self.assertEqual(selected.status_code, 200)
        result = selected.json()['result']
        self.assertEqual(result['action'], 'response')
        self.assertEqual(result['results'][0]['intent'], 'price_comparison')
        self.assertEqual(result['results'][0]['data'][0]['original']['medicine'], 'Pure 500 Tablet')
        self.assertEqual(selected.json(), retry.json())
        model.assert_not_called()
        prices.assert_called_once()

    def test_intent_change_invalidates_old_choices_and_selection_uses_latest_intent(self):
        old = self.chat()
        new = self.chat(['side_effects'], text='Side effects instead')
        stale = self.client.post('/api/select', json=self.selection_payload(old))
        self.assertEqual(stale.status_code, 409)
        selected = self.client.post('/api/select', json=self.selection_payload(new)).json()['result']
        self.assertEqual(selected['results'][0]['intent'], 'side_effects')

    def test_forged_selection_and_wrong_session_are_rejected_without_model(self):
        payload = self.selection_payload(self.chat())
        with patch('backend.services.conversation.extract_query') as model:
            forged = payload | {'product_id': str(uuid4())}
            self.assertEqual(self.client.post('/api/select', json=forged).status_code, 409)
            other_session = payload | {'session_id': str(uuid4())}
            self.assertEqual(self.client.post('/api/select', json=other_session).status_code, 409)
            self.assertEqual(self.client.post('/api/select', json=payload | {'name': 'Injected'}).status_code, 422)
        model.assert_not_called()

    def test_product_is_revalidated_for_schedule_x_before_routing(self):
        payload = self.selection_payload(self.chat())
        for row in self.rows:
            if row['name'] == 'Pure 500 Tablet':
                row['regulatory'] = 'Schedule X'
        with patch('backend.services.price.get_prices') as prices:
            selected = self.client.post('/api/select', json=payload).json()['result']
        self.assertEqual(selected['reason'], 'schedule_x')
        self.assertIsNone(selected['message'])
        prices.assert_not_called()

    def test_selection_replaces_only_unresolved_medicine(self):
        result = self.chat(['side_effects'], [Medicine(name='Zed 500 Tablet', strength=None),
                                           Medicine(name='paracetamol', strength=None)])
        selected = self.client.post('/api/select', json=self.selection_payload(result)).json()['result']
        self.assertEqual([r['medicine'] for r in selected['results'][0]['data']],
                         ['Zed 500 Tablet', 'Pure 500 Tablet'])

    def test_conflicting_products_are_excluded_and_strength_filter_accepts_missing_units(self):
        self.rows.append(record('Pure 500 Tablet', category='Schedule H'))
        self.rows.append(record('Small 120 Tablet', [{'drug': 'Paracetamol', 'strength': '120mg'}]))
        names = [r['name'] for r in suggest_products(Medicine(name='paracetamol', strength='500'))]
        self.assertNotIn('Pure 500 Tablet', names)
        self.assertNotIn('Small 120 Tablet', names)
        self.assertEqual(names, ['Zed 500 Tablet', 'Alpha Plus Tablet'])

    def test_completed_or_abandoned_request_rejects_previous_choices(self):
        result = self.chat()
        self.chat(['other'], text='Forget it')
        self.assertEqual(self.client.post('/api/select', json=self.selection_payload(result)).status_code, 409)

    def test_model_omission_still_offers_products_for_literal_ingredient(self):
        empty = Extraction(medicines=[], intents=['price_comparison'],
                           needs_clarification=False, clarification_question=None)
        with patch('backend.services.conversation.extract_query', return_value=empty):
            result = self.client.post('/api/chat', json={'message': 'Price of paracetamol',
                'session_id': self.session, 'request_id': str(uuid4())}).json()['result']
        self.assertEqual(result['action'], 'clarify')
        self.assertTrue(result['medicine_choices'])
        self.assertNotEqual(result['reason'], 'missing_medicine')

    def test_screenshot_query_recovers_exact_product_and_keeps_price_intent(self):
        self.rows.append(record('Paracetamol Tablet'))
        empty = Extraction(medicines=[], intents=['price_comparison'],
                           needs_clarification=False, clarification_question=None)
        with patch('backend.services.conversation.extract_query', return_value=empty), \
                patch('backend.services.price.get_prices', return_value=[]):
            result = self.client.post('/api/chat', json={
                'message': 'price comparison of paracetamol tablet',
                'session_id': self.session, 'request_id': str(uuid4())}).json()['result']
        self.assertEqual(result['action'], 'response')
        self.assertEqual(result['results'][0]['intent'], 'price_comparison')
        self.assertEqual(result['results'][0]['data'][0]['original']['medicine'], 'Paracetamol Tablet')

    def test_literal_recovery_preserves_strength_and_multiple_mentions_without_substrings(self):
        mentions = explicit_medicine_mentions('Compare paracetamol 500mg and Zed 500 Tablet prices')
        self.assertEqual([(m.name, m.strength) for m in mentions],
                         [('Paracetamol', '500mg'), ('Zed 500 Tablet', None)])
        self.assertEqual(explicit_medicine_mentions('Price of unparacetamol'), [])
        self.assertEqual(explicit_medicine_mentions('Price of something for fever'), [])


if __name__ == '__main__':
    unittest.main()
