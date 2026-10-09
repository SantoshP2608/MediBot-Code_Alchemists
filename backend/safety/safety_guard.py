from backend.config.settings import CONSTANTS
from backend.models.schemas import BLOCKED_INTENTS, Extraction
from backend.data.medicine_database import find_medicine, normalize


DOCTOR_DISCLAIMER = CONSTANTS["regulatory"]["doctor_disclaimer"]
ALLOWED_REGULATORY = set(CONSTANTS["regulatory"]["allowed_categories"])


def make_result(action, reason, message=None, features=None):
    """Create a consistent result for the API/frontend."""
    return {
        "action": action,
        "reason": reason,
        "message": message,
        "continue_to_response": action == "continue",
        "requested_features": features or [],
    }


def check_safety(extraction: Extraction) -> dict:
    """Check Schedule X, intents, clarification, and medicine validity in order."""
    intents = set(extraction.intents)
    resolved = [(medicine, find_medicine(medicine)) for medicine in extraction.medicines]

    # Schedule X takes precedence even over blocked intents or clarification.
    # The action is block, but no message/content is sent for this category.
    if any(normalize(row.get("regulatory", "")) == CONSTANTS["regulatory"]["restricted_category"]
           for _, matches in resolved for row in matches):
        return make_result("block", "schedule_x")

    needs_disclaimer = any(
        normalize(row.get("regulatory", "")) in set(CONSTANTS["regulatory"]["disclaimer_categories"])
        for _, matches in resolved for row in matches
    )

    def result(action, reason, message=None, features=None):
        output = make_result(action, reason, message, features)
        if needs_disclaimer:
            output["disclaimer"] = DOCTOR_DISCLAIMER
        return output

    # After the Schedule X check, block prohibited intents.
    # This also catches a mixed price + prescribing request.
    for intent, message in BLOCKED_INTENTS.items():
        if intent in intents:
            return result(
                action="block",
                reason=intent,
                message=message,
            )

    # 2. Resolve ambiguity for any non-blocked request.
    if extraction.needs_clarification:
        return result(
            action="clarify",
            reason="ambiguous_request",
            message=extraction.clarification_question.strip(),
        )

    # 3. Medicine classification needs at least one medicine.
    if not extraction.medicines and intents != {"general_health"}:
        return result(
            action="clarify",
            reason="missing_medicine",
            message=CONSTANTS["messages"]["missing_medicine"],
        )

    # 4. Reject empty medicine names.
    if any(
        not medicine.name.strip()
        for medicine in extraction.medicines
    ):
        return result(
            action="clarify",
            reason="missing_medicine_name",
            message=CONSTANTS["messages"]["missing_medicine_name"],
        )

    medicines = []
    for medicine, matches in resolved:
        if not matches:
            return result("clarify", "medicine_not_found",
                          CONSTANTS["messages"]["medicine_not_found"].format(medicine_name=medicine.name))
        if len(matches) > 1:
            if len({normalize(row["name"]) for row in matches}) == 1:
                return result("error", "conflicting_medicine_records",
                              CONSTANTS["messages"]["medicine_conflict"].format(medicine_name=medicine.name))
            output = result("clarify", "ambiguous_medicine",
                            CONSTANTS["messages"]["medicine_ambiguous"].format(medicine_name=medicine.name))
            output["candidates"] = list(dict.fromkeys(row["name"] for row in matches))[:CONSTANTS["routing"]["candidate_limit"]]
            return output
        if normalize(matches[0].get("regulatory", "")) not in ALLOWED_REGULATORY:
            return result("clarify", "unknown_regulatory_status",
                          CONSTANTS["messages"]["unknown_regulatory_status"])
        medicines.append(matches[0])

    # Only this internal continue result carries resolved data for dispatch.
    output = result(
        action="continue",
        reason="safety_checks_passed",
        features=sorted(intents),
    )
    output["resolved_medicines"] = medicines
    return output
