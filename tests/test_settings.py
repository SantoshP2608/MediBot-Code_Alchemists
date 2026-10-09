import importlib
import os
import unittest
from typing import get_args
from unittest.mock import patch

from backend.config.settings import CONSTANTS, CONSTANTS_FILE, PROJECT_ROOT
from backend.models.schemas import BLOCKED_INTENTS, Intent
from backend.services.price import get_prices


class SettingsTests(unittest.TestCase):
    def test_configuration_drives_schema_and_policy(self):
        self.assertEqual(set(get_args(Intent)), set(CONSTANTS["intents"]))
        self.assertEqual(BLOCKED_INTENTS, CONSTANTS["blocked_intents"])
        self.assertEqual(CONSTANTS_FILE, PROJECT_ROOT / "constants.txt")
        self.assertTrue(set(BLOCKED_INTENTS).issubset(get_args(Intent)))

    def test_data_and_service_paths_are_valid(self):
        for name in ("medicine_database", "pharmacy_catalogue"):
            path = (PROJECT_ROOT / CONSTANTS["paths"][name]).resolve()
            self.assertTrue(path.is_relative_to(PROJECT_ROOT))
            self.assertTrue(path.is_file())
        for name in ("price", "chatbot"):
            module = importlib.import_module(CONSTANTS["routing"][name + "_module"])
            self.assertTrue(callable(getattr(module, CONSTANTS["routing"][name + "_function"])))

    def test_price_catalogue_loads_from_another_working_directory(self):
        previous_directory = os.getcwd()
        try:
            os.chdir(PROJECT_ROOT / "backend")
            with patch("backend.services.price.pharmacy_quotes", return_value=[
                    {"status": "network_error", "price": None}]):
                result = get_prices(["Example Tablet"])
            self.assertEqual(result[0]["status"], "no_prices")
        finally:
            os.chdir(previous_directory)


if __name__ == "__main__":
    unittest.main()
