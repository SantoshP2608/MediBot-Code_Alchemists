import unittest
from typing import get_args
from unittest.mock import patch

from backend.models.schemas import BLOCKED_INTENTS, Extraction, Intent
from backend.safety.safety_guard import check_safety


def request(intent, clarify=False):
    return Extraction(medicines=[{"name": "Example Tablet", "strength": None}],
                      intents=[intent], needs_clarification=clarify,
                      clarification_question="Which product?" if clarify else None)


class SafetyTests(unittest.TestCase):
    def test_every_blocked_intent_is_in_the_schema(self):
        self.assertFalse(set(BLOCKED_INTENTS) - set(get_args(Intent)))
        self.assertIn("prescription_status", BLOCKED_INTENTS)

    def test_x_blocks_at_safety_stage_before_intents_or_clarification(self):
        row = {"name": "Example Tablet", "regulatory": "Schedule X"}
        for intent in get_args(Intent):
            with self.subTest(intent=intent), patch("backend.safety.safety_guard.find_medicine", return_value=[row]):
                result = check_safety(request(intent, clarify=True))
                self.assertEqual(result["action"], "block")
                self.assertEqual(result["reason"], "schedule_x")
                self.assertIsNone(result["message"])
                self.assertNotIn("resolved_medicines", result)
                self.assertFalse(result["continue_to_response"])

    def test_h_and_g_disclaimer_on_blocked_and_allowed_responses(self):
        for schedule in ("Schedule H", "Schedule G"):
            row = {"name": "Example Tablet", "regulatory": schedule}
            for intent in ("side_effects", "general_health", "availability", "prescription_status"):
                with self.subTest(schedule=schedule, intent=intent), \
                        patch("backend.safety.safety_guard.find_medicine", return_value=[row]):
                    result = check_safety(request(intent))
                self.assertEqual(result["disclaimer"], "Please consult a doctor.")
                self.assertEqual(result["action"], "block" if intent in BLOCKED_INTENTS else "continue")

    def test_availability_and_prescription_status_block_without_medicine(self):
        for intent in ("availability", "prescription_status"):
            result = check_safety(Extraction(medicines=[], intents=[intent],
                                            needs_clarification=False, clarification_question=None))
            self.assertEqual(result["action"], "block")
            self.assertEqual(result["reason"], intent)


if __name__ == "__main__":
    unittest.main()
