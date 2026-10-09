from backend.config.settings import CONSTANTS
import json
import logging

from backend.llm.extractor import extract_query
from backend.services.response import handle_response
from backend.safety.safety_guard import make_result


logger = logging.getLogger(__name__)


def main():
    previous_messages = []
    pending_request = None
    clarification_question = None

    print(CONSTANTS["cli"]["title"])
    print(CONSTANTS["cli"]["exit_hint"])

    while True:
        try:
            message = input(CONSTANTS["cli"]["input_prompt"]).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if message.lower() == CONSTANTS["cli"]["exit_command"]:
            break

        if not message:
            continue

        try:
            # Step 1: Extract medicine mentions and intents.
            extraction = extract_query(
                message,
                previous_messages=previous_messages,
                pending_request=pending_request,
                clarification_question=clarification_question,
            )

            # Step 2: Your code checks the extracted intents.
            result = handle_response(extraction, message, previous_messages)

            if result["action"] == "clarify":
                pending_request = pending_request or message
                clarification_question = result["message"]
            else:
                pending_request = None
                clarification_question = None

            previous_messages.append(message)
            previous_messages = previous_messages[-CONSTANTS["ollama"]["history_limit"]:]

            if result["action"] == "block" and result["reason"] == "schedule_x":
                continue

            print(CONSTANTS["cli"]["extraction_heading"])
            print(json.dumps(extraction.model_dump(), indent=CONSTANTS["display"]["json_indent"]))

        except Exception:
            logger.exception(CONSTANTS["messages"]["request_failure_log"])
            # Never continue if extraction or validation fails.
            result = make_result(
                action="error",
                reason="request_processing_failed",
                message=(
                    CONSTANTS["messages"]["request_failed"]
                ),
            )

        print(CONSTANTS["cli"]["result_heading"])
        print(json.dumps(result, indent=CONSTANTS["display"]["json_indent"]))

        if result["message"]:
            print(CONSTANTS["cli"]["frontend_heading"], result["message"])
        elif result.get("results"):
            print(CONSTANTS["cli"]["data_hint"])

        if result.get("disclaimer"):
            print("\n", result["disclaimer"])

        print()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    main()
