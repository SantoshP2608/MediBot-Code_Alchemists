from backend.config.settings import CONSTANTS
import json
import os

from ollama import Client
from backend.models.schemas import Extraction, Medicine


OLLAMA = CONSTANTS["ollama"]

SYSTEM_PROMPT = CONSTANTS["prompts"]["extractor"]

client = Client(
    host=os.environ.get(OLLAMA["host_env"], OLLAMA["host"]),
    timeout=OLLAMA["timeout_seconds"],
)


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

    response = client.chat(
        model=os.environ.get(OLLAMA["model_env"], OLLAMA["model"]),
        messages=[
            {
                "role": "system",
                "content": SYSTEM_PROMPT
                + OLLAMA["schema_suffix"]
                + json.dumps(Extraction.model_json_schema()),
            },
            {
                "role": "user",
                "content": json.dumps(payload),
            },
        ],
        format=Extraction.model_json_schema(),
        options=dict(OLLAMA["options"]),
        keep_alive=OLLAMA["keep_alive"],
    )

    return Extraction.model_validate_json(response.message.content)


if __name__ == "__main__":
    result = extract_query(CONSTANTS["display"]["demo_query"])
    print(result.model_dump_json(indent=CONSTANTS["display"]["json_indent"]))
