from backend.models import BLOCKED_INTENTS, Extraction


def make_result(action, reason, message=None, features=None):
    """Create a consistent result for the API/frontend."""
    return {
        "action": action,
        "reason": reason,
        "message": message,
        "continue_to_classification": action == "continue",
        "requested_features": features or [],
    }


def check_safety(extraction: Extraction) -> dict:
    """Check intents before medicine database classification."""

    intents = set(extraction.intents)

    # 1. Block unsafe requests first.
    # This also catches a mixed price + prescribing request.
    for intent, message in BLOCKED_INTENTS.items():
        if intent in intents:
            return make_result(
                action="block",
                reason=intent,
                message=message,
            )

    # 2. Resolve ambiguity for any non-blocked request.
    if extraction.needs_clarification:
        return make_result(
            action="clarify",
            reason="ambiguous_request",
            message=extraction.clarification_question.strip(),
        )

    # 3. Medicine classification needs at least one medicine.
    if not extraction.medicines:
        return make_result(
            action="clarify",
            reason="missing_medicine",
            message="Which medicine is your request about?",
        )

    # 4. Reject empty medicine names.
    if any(
        not medicine.name.strip()
        for medicine in extraction.medicines
    ):
        return make_result(
            action="clarify",
            reason="missing_medicine_name",
            message="Please provide the medicine name.",
        )

    # 5. Continue to the NEXT safety step.
    # This does not mean the medicines are verified or OTC.
    return make_result(
        action="continue",
        reason="requires_medicine_classification",
        features=sorted(intents),
    )
