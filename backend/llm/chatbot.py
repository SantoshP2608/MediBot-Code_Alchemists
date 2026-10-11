"""Answer general-health questions with Ollama after the safety stage."""

from backend.config.settings import CONSTANTS

import json
import os

from backend.llm.ollama_client import OLLAMA, create_ollama_client

SYSTEM_PROMPT = CONSTANTS["prompts"]["chatbot"]

client = create_ollama_client()


def get_response(message: str, *, previous_messages: list[str] | None = None) -> str:
    """Return answer text; model/connection failures propagate to the caller."""
    if not isinstance(message, str) or not message.strip():
        raise ValueError(CONSTANTS["messages"]["chatbot_message_required"])
    if previous_messages is not None and (
        not isinstance(previous_messages, list) or
        any(not isinstance(item, str) for item in previous_messages)
    ):
        raise ValueError(CONSTANTS["messages"]["invalid_chatbot_history"])
    response = client.chat(
        model=os.environ.get(OLLAMA["chat_model_env"], os.environ.get(OLLAMA["model_env"], OLLAMA["model"])),
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({
                "previous_user_messages": (previous_messages or [])[-OLLAMA["history_limit"]:],
                "latest_message": message.strip(),
            })},
        ],
        think=OLLAMA["think"],
        options=dict(OLLAMA["options"]),
        keep_alive=OLLAMA["keep_alive"],
    )
    answer = response.message.content
    if not isinstance(answer, str) or not answer.strip():
        raise ValueError(CONSTANTS["messages"]["empty_chatbot_answer"])
    return answer.strip()
