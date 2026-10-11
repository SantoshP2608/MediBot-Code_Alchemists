from backend.config.settings import CONSTANTS
import json
import os

from backend.models.schemas import Extraction, Medicine, TurnUpdate
from backend.llm.ollama_client import OLLAMA, create_ollama_client


SYSTEM_PROMPT = CONSTANTS["prompts"]["extractor"]

client = create_ollama_client()


def extract_query(
    message: str,
    previous_messages: list[str] | None = None,
    pending_request: str | None = None,
    clarification_question: str | None = None,
) -> Extraction:
    payload = {
        "previous_user_messages": (previous_messages or [])[-OLLAMA["history_limit"]:],
        "latest_message": message,
        "pending_request": pending_request,
        "clarification_question": clarification_question,
    }

    return _extract(payload, Extraction, SYSTEM_PROMPT)


def extract_turn(message, previous_messages=None, pending_request=None,
                 clarification_question=None, pending_state=None) -> TurnUpdate:
    """Extract explicit task updates without asking the model to merge intents."""
    payload = {
        "previous_user_messages": (previous_messages or [])[-OLLAMA["history_limit"]:],
        "latest_message": message,
        "pending_request": pending_request,
        "clarification_question": clarification_question,
        "pending_state": pending_state,
    }
    return _extract(payload, TurnUpdate, CONSTANTS["prompts"]["conversation_turn"])


def _extract(payload, schema, prompt):
    json_schema = schema.model_json_schema()
    response = client.chat(
        model=os.environ.get(OLLAMA["model_env"], OLLAMA["model"]),
        messages=[
            {
                "role": "system",
                # Structured output already supplies the turn schema. Avoid
                # duplicating it in the small local-model context window.
                "content": prompt if schema is TurnUpdate else (
                    prompt + OLLAMA["schema_suffix"] + json.dumps(json_schema)),
            },
            {
                "role": "user",
                "content": json.dumps(payload),
            },
        ],
        format=json_schema,
        think=OLLAMA["think"],
        options=dict(OLLAMA["options"]),
        keep_alive=OLLAMA["keep_alive"],
    )

    return schema.model_validate_json(response.message.content)


if __name__ == "__main__":
    result = extract_query(CONSTANTS["display"]["demo_query"])
    print(result.model_dump_json(indent=CONSTANTS["display"]["json_indent"]))
