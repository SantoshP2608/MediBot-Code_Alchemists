import io
import json
import unittest
from contextlib import redirect_stdout
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError
from backend.llm.extractor import extract_query
from backend.models.schemas import Extraction
from backend.cli.safety_cli import main


def extraction(**overrides):
    data = {"medicines": [{"name": "Example", "strength": "650"}],
            "intents": ["side_effects"], "needs_clarification": False,
            "clarification_question": None}
    return Extraction(**(data | overrides))


class BackendFlowTests(unittest.TestCase):
    def test_extractor_passes_pending_context_and_validates_output(self):
        answer = extraction()
        with patch("backend.llm.extractor.client.chat", return_value=SimpleNamespace(
                message=SimpleNamespace(content=answer.model_dump_json()))) as chat:
            actual = extract_query("Example 650", ["Side effects?"], "Side effects?", "Which medicine?")
        self.assertEqual(actual, answer)
        payload = json.loads(chat.call_args.kwargs["messages"][1]["content"])
        self.assertEqual(payload["pending_request"], "Side effects?")
        self.assertEqual(payload["clarification_question"], "Which medicine?")
        self.assertEqual(payload["latest_message"], "Example 650")

    def test_invalid_llm_output_never_reaches_response_handler(self):
        with patch("backend.llm.extractor.client.chat", return_value=SimpleNamespace(
                message=SimpleNamespace(content='{"intents": ["invalid"]}'))):
            with self.assertRaises(ValidationError):
                extract_query("Example")

    def test_cli_clarifies_then_answers_and_clears_pending_request(self):
        answers = [extraction(medicines=[], needs_clarification=True, clarification_question="Which medicine?"),
                   extraction(), extraction(intents=["prescribing_request"])]
        database = (("example 650 tablet", {"name": "Example 650 Tablet",
                     "regulatory": "OTC", "side_effects": ["Example effect"]}),)
        output = io.StringIO()
        with patch("builtins.input", side_effect=["Side effects?", "Example 650", "Prescribe Example", "exit"]), \
                patch("backend.cli.safety_cli.extract_query", side_effect=answers) as extract, \
                patch("backend.data.medicine_database.load_database", return_value=database), redirect_stdout(output):
            main()
        calls = extract.call_args_list
        self.assertEqual(calls[1].kwargs["pending_request"], "Side effects?")
        self.assertEqual(calls[1].kwargs["clarification_question"], "Which medicine?")
        self.assertIsNone(calls[2].kwargs["pending_request"])
        self.assertIn('"action": "clarify"', output.getvalue())
        self.assertIn("Example effect", output.getvalue())
        self.assertIn('"action": "block"', output.getvalue())

    def test_cli_prints_no_extraction_or_response_for_x(self):
        database = (("example 650 tablet", {"name": "Example 650 Tablet", "regulatory": "Schedule X"}),)
        output = io.StringIO()
        with patch("builtins.input", side_effect=["Example side effects", "exit"]), \
                patch("backend.cli.safety_cli.extract_query", return_value=extraction()), \
                patch("backend.data.medicine_database.load_database", return_value=database), redirect_stdout(output):
            main()
        self.assertNotIn("EXTRACTION:", output.getvalue())
        self.assertNotIn("RESULT:", output.getvalue())

    def test_cli_returns_error_when_extraction_fails(self):
        output = io.StringIO()
        with patch("builtins.input", side_effect=["Question", "exit"]), \
                patch("backend.cli.safety_cli.extract_query", side_effect=RuntimeError("Service unavailable")), \
                patch("backend.cli.safety_cli.logger.exception"), redirect_stdout(output):
            main()
        self.assertIn('"action": "error"', output.getvalue())
        self.assertNotIn('"action": "continue"', output.getvalue())


if __name__ == "__main__":
    unittest.main()
