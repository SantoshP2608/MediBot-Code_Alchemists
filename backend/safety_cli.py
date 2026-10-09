import json
import logging

from backend.extractor import extract_query
from backend.safety.safety_guard import check_safety, make_result


logger = logging.getLogger(__name__)


def main():
    previous_messages = []

    print("MediBot safety tester")
    print("Type 'exit' to stop.\n")

    while True:
        try:
            message = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if message.lower() == "exit":
            break

        if not message:
            continue

        try:
            # Step 1: Extract medicine mentions and intents.
            extraction = extract_query(
                message,
                previous_messages=previous_messages,
            )

            print("\nEXTRACTION:")
            print(json.dumps(
                extraction.model_dump(),
                indent=2,
            ))

            # Step 2: Your code checks the extracted intents.
            result = check_safety(extraction)

            previous_messages.append(message)
            previous_messages = previous_messages[-6:]

        except Exception:
            logger.exception("Request processing failed")
            # Never continue if extraction or validation fails.
            result = make_result(
                action="error",
                reason="extraction_failed",
                message=(
                    "I couldn't process your request. "
                    "Please try again."
                ),
            )

        print("\nSAFETY RESULT:")
        print(json.dumps(result, indent=2))

        if result["message"]:
            print("\nMessage for frontend:", result["message"])
        else:
            print("\nNext step: medicine database classification.")

        print()


if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING)
    main()
