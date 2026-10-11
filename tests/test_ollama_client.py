import json
import os
import unittest
from unittest.mock import patch

from backend.config.settings import CONSTANTS
from backend.llm.ollama_client import create_ollama_client


class OllamaClientTests(unittest.TestCase):
    def test_reads_optional_auth_headers_from_environment(self):
        headers = {
            'CF-Access-Client-Id': 'client-id',
            'CF-Access-Client-Secret': 'client-secret',
        }
        with patch.dict(os.environ, {'OLLAMA_HEADERS': json.dumps(headers)}, clear=True), \
                patch('backend.llm.ollama_client.Client') as client:
            create_ollama_client()
        client.assert_called_once_with(
            host=CONSTANTS['ollama']['host'],
            timeout=CONSTANTS['ollama']['timeout_seconds'],
            headers=headers,
        )

    def test_missing_headers_remain_optional_for_local_development(self):
        with patch.dict(os.environ, {}, clear=True), \
                patch('backend.llm.ollama_client.Client') as client:
            create_ollama_client()
        self.assertEqual(client.call_args.kwargs['headers'], {})

    def test_invalid_headers_fail_explicitly(self):
        for value in ('not-json', '[]', '{"Authorization": 12}'):
            with self.subTest(value=value), patch.dict(os.environ, {'OLLAMA_HEADERS': value}):
                with self.assertRaisesRegex(ValueError, 'OLLAMA_HEADERS'):
                    create_ollama_client()


if __name__ == '__main__':
    unittest.main()
