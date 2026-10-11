"""Shared Ollama client configuration for model calls."""

import json
import os

from ollama import Client

from backend.config.settings import CONSTANTS

OLLAMA = CONSTANTS["ollama"]


def create_ollama_client() -> Client:
    raw_headers = os.environ.get("OLLAMA_HEADERS")
    headers = {}
    if raw_headers is not None:
        try:
            headers = json.loads(raw_headers)
        except json.JSONDecodeError as error:
            raise ValueError("OLLAMA_HEADERS must be a JSON object of string headers.") from error
        if not isinstance(headers, dict) or any(
            not isinstance(name, str) or not name or not isinstance(value, str)
            for name, value in headers.items()
        ):
            raise ValueError("OLLAMA_HEADERS must be a JSON object of string headers.")

    return Client(
        host=os.environ.get(OLLAMA["host_env"], OLLAMA["host"]),
        timeout=OLLAMA["timeout_seconds"],
        headers=headers,
    )
