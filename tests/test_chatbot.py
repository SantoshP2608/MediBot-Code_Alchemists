import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from backend.llm.chatbot import get_response
from backend.models.schemas import Extraction
from backend.services.response import handle_response


class ChatbotTests(unittest.TestCase):
    def test_answer_context_and_model_configuration(self):
        answer = SimpleNamespace(message=SimpleNamespace(content="  Example health information.  "))
        with patch("backend.llm.chatbot.client.chat", return_value=answer) as chat, \
                patch.dict("os.environ", {"OLLAMA_CHAT_MODEL": "test-model"}):
            actual = get_response("General health question", previous_messages=[str(n) for n in range(8)])
        self.assertEqual(actual, "Example health information.")
        self.assertEqual(chat.call_args.kwargs["model"], "test-model")
        payload = json.loads(chat.call_args.kwargs["messages"][1]["content"])
        self.assertEqual(payload["previous_user_messages"], [str(n) for n in range(2, 8)])
        self.assertEqual(payload["latest_message"], "General health question")
        self.assertIn("Do not diagnose", chat.call_args.kwargs["messages"][0]["content"])

    def test_empty_input_or_answer_is_an_error(self):
        with patch("backend.llm.chatbot.client.chat") as chat:
            with self.assertRaises(ValueError):
                get_response(" ")
            with self.assertRaises(ValueError):
                get_response("Question", previous_messages=[None])
            chat.assert_not_called()
        with patch("backend.llm.chatbot.client.chat", return_value=SimpleNamespace(
                message=SimpleNamespace(content=" "))):
            with self.assertRaises(ValueError):
                get_response("Question")

    def test_model_failure_is_not_presented_as_a_successful_answer(self):
        with patch("backend.llm.chatbot.client.chat", side_effect=ConnectionError("Unavailable")):
            with self.assertRaises(ConnectionError):
                get_response("Question")

    def test_general_health_routes_to_real_chatbot_without_medicine(self):
        extraction = Extraction(medicines=[], intents=["general_health"],
                                needs_clarification=False, clarification_question=None)
        with patch("backend.llm.chatbot.client.chat", return_value=SimpleNamespace(
                message=SimpleNamespace(content="Example answer."))) as chat, \
                patch("backend.data.medicine_database.load_database") as database:
            result = handle_response(extraction, "General health question")
        chat.assert_called_once()
        database.assert_not_called()
        self.assertEqual(result["results"][0]["data"], "Example answer.")


if __name__ == "__main__":
    unittest.main()
