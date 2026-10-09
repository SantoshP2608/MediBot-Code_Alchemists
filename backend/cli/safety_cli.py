from backend.config.settings import CONSTANTS
import json
import logging

from backend.services.conversation import Conversation, process_message


def main():
    state = Conversation()

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

        extraction, result = process_message(state, message)
        if result["action"] == "block" and result["reason"] == "schedule_x":
            continue
        if extraction is not None:
            print(CONSTANTS["cli"]["extraction_heading"])
            print(json.dumps(extraction.model_dump(), indent=CONSTANTS["display"]["json_indent"]))

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
