import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from backend.models.schemas import Extraction
from backend.services.response import normalize, handle_response


def request(intents, medicines=None, **overrides):
    return Extraction(
        medicines=medicines if medicines is not None else [{"name": "Example", "strength": "650"}],
        intents=intents,
        needs_clarification=False,
        clarification_question=None,
        **overrides,
    )


class ResponseTests(unittest.TestCase):
    def setUp(self):
        self.record = {
            "name": "Example 650mg Tablet",
            "uses": ["Example use"],
            "side_effects": ["Example effect"],
            "substitutes": ["Replacement 650mg Tablet"],
            "regulatory": "OTC",
        }
        self.database = patch(
            "backend.data.medicine_database.load_database",
            return_value=(
                (normalize(self.record["name"]), self.record),
                (normalize("Replacement 650mg Tablet"), {"name": "Replacement 650mg Tablet", "regulatory": "OTC"}),
            ),
        )
        self.loader = self.database.start()
        self.addCleanup(self.database.stop)

    def test_block_and_clarification_do_not_dispatch(self):
        with patch("backend.services.response.call_service") as service:
            blocked = handle_response(request(["prescribing_request", "price_comparison"]))
            ambiguous = Extraction(
                medicines=[], intents=["side_effects"],
                needs_clarification=True, clarification_question="Which medicine?",
            )
            clarified = handle_response(ambiguous)
        self.assertEqual(blocked["action"], "block")
        self.assertEqual(clarified["action"], "clarify")
        service.assert_not_called()
        self.loader.assert_called()

    def test_multiple_database_intents_return_fields(self):
        result = handle_response(request(["side_effects", "uses_of_medicine"]))
        self.assertEqual(result["results"][0]["data"][0]["side_effects"], ["Example effect"])
        self.assertEqual(result["results"][1]["data"][0]["uses"], ["Example use"])

    def test_substitute_prices_use_database_names(self):
        prices = Mock(return_value=[{"price": 10}])
        with patch.dict("sys.modules", {"backend.services.price": SimpleNamespace(get_prices=prices)}):
            result = handle_response(request(["alternative_search"]))
        prices.assert_called_once_with(["Example 650mg Tablet", "Replacement 650mg Tablet"], intent="alternative_search")
        self.assertEqual(result["results"][0]["data"][0]["alternatives"][0]["medicine"], "Replacement 650mg Tablet")

    def test_availability_blocks_mixed_price_request_without_service_calls(self):
        prices = Mock(return_value=[])
        with patch.dict("sys.modules", {"backend.services.price": SimpleNamespace(get_prices=prices)}):
            result = handle_response(request(["price_comparison", "availability"]))
        self.assertEqual(result["action"], "block")
        self.assertEqual(result["reason"], "availability")
        prices.assert_not_called()
        self.loader.assert_called()

    def test_general_health_without_medicine_passes_context(self):
        chatbot = Mock(return_value="Example answer")
        with patch.dict("sys.modules", {"backend.llm.chatbot": SimpleNamespace(get_response=chatbot)}):
            result = handle_response(request(["general_health"], []), "Sleep tips?", ["Earlier"])
        self.assertEqual(result["action"], "response")
        chatbot.assert_called_once_with("Sleep tips?", previous_messages=["Earlier"])

    def test_missing_future_module_returns_pending_status(self):
        with patch("backend.services.response.importlib.import_module", side_effect=ModuleNotFoundError(name="backend.services.price")):
            result = handle_response(request(["price_comparison"]))
        self.assertEqual(result["results"][0]["status"], "not_implemented")

    def test_not_found_and_ambiguous_products_ask_for_clarification(self):
        missing = handle_response(request(["side_effects"], [{"name": "Unknown", "strength": None}]))
        self.assertEqual(missing["reason"], "medicine_not_found")
        other = {**self.record, "name": "Example 500mg Tablet"}
        self.loader.return_value += ((normalize(other["name"]), other),)
        ambiguous = handle_response(request(["side_effects"], [{"name": "Example", "strength": None}]))
        self.assertEqual(ambiguous["reason"], "ambiguous_medicine")
        self.assertEqual(len(ambiguous["candidates"]), 2)
        resolved = handle_response(request(["side_effects"]))
        self.assertEqual(resolved["action"], "response")

    def test_empty_fields_and_substitutes_are_explicit(self):
        self.record["side_effects"] = []
        self.record["substitutes"] = []
        with patch("backend.services.response.call_service", return_value={"status": "ok", "data": []}) as service:
            result = handle_response(request(["side_effects", "alternative_search"]))
        self.assertEqual(result["results"][0]["data"][0]["status"], "no_data")
        self.assertEqual(result["results"][1]["data"][0]["alternatives"], [])
        service.assert_called_once()

    def test_h_and_g_add_disclaimer_to_every_route(self):
        for schedule in ("Schedule H", "Schedule G"):
            self.record["regulatory"] = schedule
            for intent in ("price_comparison", "alternative_search",
                           "side_effects", "uses_of_medicine", "general_health"):
                with self.subTest(schedule=schedule, intent=intent):
                    with patch("backend.services.response.call_service", return_value={"status": "ok", "data": []}):
                        result = handle_response(request([intent]), "Example question")
                    self.assertEqual(result["action"], "response")
                    self.assertEqual(result["disclaimer"], "Please consult a doctor.")

    def test_x_suppresses_all_routes_before_services(self):
        self.record["regulatory"] = "Schedule X"
        for intent in ("price_comparison", "availability", "alternative_search",
                       "side_effects", "uses_of_medicine", "general_health"):
            with self.subTest(intent=intent):
                with patch("backend.services.response.call_service") as service:
                    result = handle_response(request([intent]))
                self.assertEqual(result["action"], "block")
                self.assertEqual(result["reason"], "schedule_x")
                self.assertIsNone(result["message"])
                self.assertNotIn("results", result)
                service.assert_not_called()

    def test_x_in_mixed_request_suppresses_everything(self):
        restricted = {"name": "Restricted Tablet", "regulatory": "Schedule X"}
        self.loader.return_value += ((normalize(restricted["name"]), restricted),)
        with patch("backend.services.response.call_service") as service:
            result = handle_response(request(
                ["side_effects", "price_comparison"],
                [{"name": "Example", "strength": "650"},
                 {"name": "Restricted Tablet", "strength": None}],
            ))
        self.assertEqual(result["action"], "block")
        self.assertEqual(result["reason"], "schedule_x")
        service.assert_not_called()

    def test_substitute_regulatory_checks(self):
        substitute = self.loader.return_value[1][1]
        substitute["regulatory"] = "Schedule G"
        with patch("backend.services.response.call_service", return_value={"status": "ok", "data": []}):
            result = handle_response(request(["alternative_search"]))
        self.assertEqual(result["disclaimer"], "Please consult a doctor.")
        substitute["regulatory"] = "Schedule X"
        self.record["substitutes"].append("Unknown Product")
        with patch("backend.services.response.call_service", return_value={"status": "ok", "data": []}) as service:
            result = handle_response(request(["alternative_search"]))
        self.assertEqual(result["results"][0]["data"][0]["alternatives"], [])
        service.assert_called_once_with("backend.services.price", "get_prices", ["Example 650mg Tablet"], intent="alternative_search")

    def test_unknown_regulatory_label_does_not_dispatch(self):
        self.record.pop("regulatory")
        with patch("backend.services.response.call_service") as service:
            result = handle_response(request(["side_effects"]))
        self.assertEqual(result["reason"], "unknown_regulatory_status")
        service.assert_not_called()

    def test_otc_has_no_disclaimer(self):
        result = handle_response(request(["side_effects"]))
        self.assertNotIn("disclaimer", result)

    def test_strength_units_can_be_verified_from_single_ingredient(self):
        self.record["name"] = "Example 650 Tablet"
        self.record["composition"] = [{"drug": "Ingredient", "strength": "650mg"}]
        self.loader.return_value = ((normalize(self.record["name"]), self.record),)
        result = handle_response(request(["side_effects"], [{"name": "Example", "strength": "650mg"}]))
        self.assertEqual(result["action"], "response")
        wrong = handle_response(request(["side_effects"], [{"name": "Example", "strength": "650mcg"}]))
        self.assertEqual(wrong["reason"], "medicine_not_found")

    def test_identical_duplicate_records_do_not_force_clarification(self):
        self.loader.return_value += ((normalize(self.record["name"]), dict(self.record)),)
        result = handle_response(request(["side_effects"]))
        self.assertEqual(result["action"], "response")

    def test_unknown_composition_strength_does_not_crash_lookup(self):
        self.record["name"] = "Example Tablet"
        self.record["composition"] = [{"drug": "Ingredient", "strength": None}]
        self.loader.return_value = ((normalize(self.record["name"]), self.record),)
        result = handle_response(request(["side_effects"], [{"name": "Example", "strength": "650mg"}]))
        self.assertEqual(result["action"], "clarify")
        self.assertEqual(result["reason"], "medicine_not_found")

    def test_conflicting_records_do_not_create_endless_clarification(self):
        conflicting = {**self.record, "side_effects": ["Different effect"]}
        self.loader.return_value += ((normalize(conflicting["name"]), conflicting),)
        with patch("backend.services.response.call_service") as service:
            result = handle_response(request(["price_comparison"]))
        self.assertEqual(result["action"], "error")
        self.assertEqual(result["reason"], "conflicting_medicine_records")
        service.assert_not_called()

    def test_x_suppresses_even_after_an_unknown_product(self):
        self.record["regulatory"] = "Schedule X"
        with patch("backend.services.response.call_service") as service:
            result = handle_response(request(["side_effects"], [
                {"name": "Unknown", "strength": None},
                {"name": "Example", "strength": "650"},
            ]))
        self.assertEqual(result["action"], "block")
        self.assertEqual(result["reason"], "schedule_x")
        service.assert_not_called()

    def test_combined_price_and_alternative_intents_fetch_once(self):
        with patch("backend.services.response.call_service", return_value={"status": "ok", "data": []}) as service:
            result = handle_response(request(["price_comparison", "alternative_search"]))
        service.assert_called_once()
        self.assertEqual(result["results"][0]["data"], result["results"][1]["data"])


if __name__ == "__main__":
    unittest.main()
