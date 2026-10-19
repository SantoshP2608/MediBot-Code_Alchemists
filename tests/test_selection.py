import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.config.settings import CONSTANTS
from backend.api.app import create_app
from backend.data.medicine_database import explicit_medicine_mentions, normalize, suggest_products
from backend.models.schemas import Extraction, Medicine, TurnUpdate


def record(name, drugs=None, category='OTC'):
    return {'name': name, 'composition': drugs or [{'drug': 'Paracetamol', 'strength': '500mg'}],
            'regulatory': category, 'side_effects': ['Example effect'], 'uses': ['Example use']}


class SelectionTests(unittest.TestCase):
    def test_ingredient_uses_and_side_effects_preserve_intent_after_selection(self):
        for intent, field in [('uses_of_medicine', 'uses'), ('side_effects', 'side_effects')]:
            result = self.chat([intent], [Medicine(name='Paracetamol 500mg tablets', strength=None)])
            self.assertEqual(result['reason'], 'ingredient_selection')
            with patch('backend.services.conversation.extract_query') as model:
                selected = self.client.post('/api/select', json=self.selection_payload(result)).json()['result']
            self.assertEqual(selected['results'][0]['intent'], intent)
            self.assertTrue(selected['results'][0]['data'][0][field])
            model.assert_not_called()

    def test_ingredient_strength_matches_requested_component_not_other_ingredient(self):
        self.rows.append(record('Wrong Combination Tablet', [
            {'drug': 'Paracetamol', 'strength': '250mg'}, {'drug': 'Other', 'strength': '500mg'}]))
        choices = suggest_products(Medicine(name='Paracetamol 500mg tablets', strength=None))
        self.assertNotIn('Wrong Combination Tablet', [row['name'] for row in choices])

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
        self.assertEqual(selected['message'], CONSTANTS["regulatory"]["doctor_disclaimer"])
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

    def add_dolo(self):
        self.rows.extend([record('Dolo 500 Tablet'), record('Dolo 650 Tablet'),
                          record('Dolo 250 Suspension')])

    def test_price_of_dolo_offers_clickable_choices_when_model_omits_brand(self):
        self.add_dolo()
        empty = TurnUpdate(relation='new_request', intent_operation='replace', intents=['price_comparison'],
                           medicine_operation='replace', medicines=[], unresolved_question=None)
        with patch('backend.services.conversation.extract_query', return_value=empty):
            result = self.client.post('/api/chat', json={'message': 'price of dolo',
                'session_id': self.session, 'request_id': str(uuid4())}).json()['result']
        self.assertEqual(result['reason'], 'ambiguous_medicine')
        names = [row['name'] for row in result['medicine_choices']]
        self.assertIn('Dolo 500 Tablet', names)
        self.assertIn('Dolo 650 Tablet', names)
        with patch('backend.services.price.get_prices', return_value=[]), \
                patch('backend.services.conversation.extract_query') as model:
            selected = self.client.post('/api/select', json=self.selection_payload(result)).json()['result']
        self.assertEqual(selected['results'][0]['intent'], 'price_comparison')
        model.assert_not_called()

    def test_dolo_tablet_matches_across_omitted_strength_and_excludes_suspension(self):
        self.add_dolo()
        self.rows.append(record('Nvm Dolo Tablet SR'))
        result = self.chat(medicines=[Medicine(name='Dolo tablet', strength=None)], text='Price of Dolo tablet')
        self.assertEqual(result['reason'], 'ambiguous_medicine')
        self.assertEqual({row['name'] for row in result['medicine_choices']},
                         {'Dolo 500 Tablet', 'Dolo 650 Tablet'})

    def test_model_clarification_does_not_hide_product_choices(self):
        self.add_dolo()
        extraction = Extraction(medicines=[Medicine(name='Dolo', strength=None)],
                                intents=['price_comparison'], needs_clarification=True,
                                clarification_question='Which medicine?')
        with patch('backend.services.conversation.extract_query', return_value=extraction):
            result = self.client.post('/api/chat', json={'message': 'Price of Dolo',
                'session_id': self.session, 'request_id': str(uuid4())}).json()['result']
        self.assertTrue(result['medicine_choices'])

    def test_selecting_product_without_intent_preserves_it_while_asking_for_intent(self):
        self.add_dolo()
        update = TurnUpdate(relation='new_request', intent_operation='keep', intents=[],
                            medicine_operation='replace', medicines=[Medicine(name='Dolo tablet', strength=None)],
                            unresolved_question=None)
        with patch('backend.services.conversation.extract_query', return_value=update):
            result = self.client.post('/api/chat', json={'message': 'Dolo tablet',
                'session_id': self.session, 'request_id': str(uuid4())}).json()['result']
        selected = self.client.post('/api/select', json=self.selection_payload(result)).json()['result']
        self.assertEqual(selected['reason'], 'missing_intent')
        self.assertNotIn('medicine_choices', selected)
        update = update.model_copy(update={'relation': 'continuation', 'intent_operation': 'replace',
                                          'intents': ['price_comparison'], 'medicine_operation': 'keep', 'medicines': []})
        with patch('backend.services.conversation.extract_query', return_value=update), \
                patch('backend.services.price.get_prices', return_value=[]):
            answer = self.client.post('/api/chat', json={'message': 'Prices',
                'session_id': self.session, 'request_id': str(uuid4())}).json()['result']
        self.assertEqual(answer['results'][0]['intent'], 'price_comparison')
        self.assertEqual(answer['results'][0]['data'][0]['original']['medicine'], 'Dolo 500 Tablet')

    def test_generic_ingredient_offers_valid_products_despite_conflicting_prefix_records(self):
        ingredient = [{'drug': 'Diclofenac', 'strength': '75mg'}]
        self.rows = [record('Diclofenac Sodium  Injection', [{'drug': 'Diclofenac', 'strength': None}], 'Schedule H'),
                     record('Diclofenac Sodium Injection', ingredient, 'Schedule H'),
                     record('Verified Brand Injection', ingredient, 'Schedule H')]
        result = self.chat(medicines=[Medicine(name='Diclofenac', strength=None)], text='Price of Diclofenac')
        self.assertEqual(result['reason'], 'ingredient_selection')
        self.assertEqual([c['name'] for c in result['medicine_choices']], ['Verified Brand Injection'])
        with patch('backend.services.price.get_prices', return_value=[]), \
                patch('backend.services.conversation.extract_query') as model:
            selected = self.client.post('/api/select', json=self.selection_payload(result)).json()['result']
        self.assertEqual(selected['results'][0]['intent'], 'price_comparison')
        self.assertEqual(selected['disclaimer'], CONSTANTS["regulatory"]["schedule_hg_disclaimer"])
        model.assert_not_called()

    def test_ingredient_does_not_auto_select_single_prefix_match_after_cleanup(self):
        ingredient = [{'drug': 'Diclofenac', 'strength': '75mg'}]
        self.rows = [record('Diclofenac Sodium Injection', ingredient, 'Schedule H'),
                     record('Verified Brand Injection', ingredient, 'Schedule H')]
        result = self.chat(medicines=[Medicine(name='Diclofenac', strength=None)])
        self.assertEqual(result['action'], 'clarify')
        self.assertEqual(len(result['medicine_choices']), 2)

    def test_exact_conflicting_product_still_returns_error(self):
        ingredient = [{'drug': 'Diclofenac', 'strength': '75mg'}]
        self.rows = [record('Diclofenac Sodium Injection', ingredient),
                     record('Diclofenac Sodium  Injection', [{'drug': 'Diclofenac', 'strength': '25mg'}]),
                     record('Verified Brand Injection', ingredient)]
        result = self.chat(medicines=[Medicine(name='Diclofenac Sodium Injection', strength=None)])
        self.assertEqual(result['reason'], 'conflicting_medicine_records')
        self.assertNotIn('medicine_choices', result)


if __name__ == '__main__':
    unittest.main()
