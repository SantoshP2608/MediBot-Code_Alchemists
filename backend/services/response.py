"""Route validated requests to medicine data and service modules.

Service interfaces:
    backend.services.price.get_prices(medicine_names, *, intent)
    backend.llm.chatbot.get_response(message, *, previous_messages)

Both functions must return JSON-serializable data. Prices are requested for
the listed substitutes; this module does not recommend a substitute.
"""

from backend.config.settings import CONSTANTS

import importlib
from decimal import Decimal

from backend.models.schemas import Extraction, Medicine
from backend.data.medicine_database import find_medicine, normalize
from backend.safety.safety_guard import ALLOWED_REGULATORY, DOCTOR_DISCLAIMER, check_safety, make_result


def call_service(module_name: str, function_name: str, *args, **kwargs) -> dict:
    try:
        module = importlib.import_module(module_name)
    except ModuleNotFoundError as error:
        # Missing dependencies inside an existing module are real errors.
        if error.name != module_name:
            raise
        return {
            "status": "not_implemented",
            "message": CONSTANTS["messages"]["module_missing"].format(module=module_name.rsplit(".", 1)[-1]),
        }
    return {"status": "ok", "data": getattr(module, function_name)(*args, **kwargs)}


def composition_signature(medicine):
    composition = medicine.get("composition", [])
    if not composition or any(not row.get("drug") or not row.get("strength") for row in composition):
        return None
    return sorted((normalize(row["drug"]), normalize(row["strength"])) for row in composition)


def dosage_form(medicine):
    tokens = normalize(medicine["name"]).split()
    forms = set(CONSTANTS["matching"]["forms"])
    release = set(CONSTANTS["matching"]["release_markers"])
    return sorted(token for token in tokens if token in forms | release)


def compare_unit_prices(original, alternative):
    """Compare only non-conditional prices at the same pharmacy and dosage unit."""
    savings = []
    for pharmacy in {row.get("pharmacy") for row in original.get("quotes", [])}:
        for unit in CONSTANTS["pricing"]["comparable_units"]:
            def eligible(data):
                return [row for row in data.get("quotes", [])
                        if row.get("pharmacy") == pharmacy and row.get("status") == "ok"
                        and not row.get("conditional") and row.get("unit") == unit
                        and row.get("unit_price") and row.get("unit_price") > 0]
            base_quotes, alternative_quotes = eligible(original), eligible(alternative)
            if not base_quotes or not alternative_quotes:
                continue
            base = min(base_quotes, key=lambda row: row["unit_price"])
            substitute = min(alternative_quotes, key=lambda row: row["unit_price"])
            base_price = Decimal(str(base["unit_price"]))
            difference = max(Decimal(0), base_price - Decimal(str(substitute["unit_price"])))
            savings.append({
                "pharmacy": pharmacy, "unit": unit,
                "amount_per_unit": float(round(difference, CONSTANTS["pricing"]["unit_precision"])),
                "percent": float(round(difference / base_price * 100, CONSTANTS["pricing"]["percent_precision"])),
                "original_product_url": base.get("product_url"),
                "alternative_product_url": substitute.get("product_url"),
            })
    return savings


def build_price_comparison(medicine, substitutes, prices):
    def product(record):
        return {
            "medicine": record["name"], "composition": record.get("composition", []),
            "regulatory": record.get("regulatory"),
            "prices": prices.get(record["name"], {"medicine": record["name"], "status": "no_prices", "quotes": []}),
        }
    original = product(medicine)
    alternatives = []
    for substitute in substitutes:
        alternative = product(substitute)
        signature = composition_signature(medicine)
        matches = signature is not None and signature == composition_signature(substitute)
        alternative["composition_match"] = matches
        comparable = matches and bool(dosage_form(medicine)) and dosage_form(medicine) == dosage_form(substitute)
        alternative["savings"] = compare_unit_prices(original["prices"], alternative["prices"]) if comparable else []
        alternatives.append(alternative)
    percentages = [saving["percent"] for row in alternatives for saving in row["savings"]]
    return {
        "original": original, "alternatives": alternatives,
        "max_potential_savings_percent": max(percentages) if percentages else None,
        "verified_composition_matches": sum(row["composition_match"] for row in alternatives),
        "note": CONSTANTS["messages"]["composition_match_note"],
    }


def handle_response(
    extraction: Extraction,
    message: str = "",
    previous_messages: list[str] | None = None,
) -> dict:
    """Return block/clarify immediately, otherwise dispatch every requested intent.

    All mentioned medicines are checked against the database before dispatch.
    The safety stage blocks Schedule X without a message. Schedule H/G adds a disclaimer.
    The regulatory label is read from the dataset, not inferred by the model.
    """
    safety_result = check_safety(extraction)
    if safety_result["action"] != "continue":
        return safety_result

    intents = list(dict.fromkeys(extraction.intents))
    medicines = safety_result["resolved_medicines"]
    needs_disclaimer = bool(safety_result.get("disclaimer"))

    # Check alternatives before any service call too. Unverified or Schedule X
    # substitutes are omitted from both the output and downstream price calls.
    substitute_records = {}
    price_intents = set(CONSTANTS["routing"]["price_intents"])
    if price_intents.intersection(intents):
        for medicine in medicines:
            records = []
            for name in medicine.get("substitutes", []):
                matches = find_medicine(Medicine(name=name, strength=None))
                if len(matches) != 1:
                    continue
                regulatory = normalize(matches[0].get("regulatory", ""))
                if regulatory not in ALLOWED_REGULATORY:
                    continue
                needs_disclaimer |= regulatory in set(CONSTANTS["regulatory"]["disclaimer_categories"])
                records.append(matches[0])
            substitute_records[medicine["name"]] = records

    requested_names = [medicine["name"] for medicine in medicines]
    comparisons = []
    if price_intents.intersection(intents):
        all_names = list(dict.fromkeys(requested_names + [
            row["name"] for records in substitute_records.values() for row in records
        ]))
        service_result = call_service(CONSTANTS["routing"]["price_module"], CONSTANTS["routing"]["price_function"], all_names,
                                      intent="price_comparison" if "price_comparison" in intents else "alternative_search")
        if service_result["status"] == "ok":
            prices = {row["medicine"]: row for row in service_result["data"] if "medicine" in row}
            comparisons = [build_price_comparison(medicine, substitute_records[medicine["name"]], prices)
                           for medicine in medicines]
    results = []
    for intent in intents:
        if intent in price_intents:
            result = {"status": "ok", "data": comparisons} if service_result["status"] == "ok" else service_result
        elif intent in {"side_effects", "uses_of_medicine"}:
            field = "side_effects" if intent == "side_effects" else "uses"
            result = {
                "status": "ok",
                "data": [
                    {"medicine": medicine["name"], field: medicine.get(field, []),
                     "status": "ok" if medicine.get(field) else "no_data"}
                    for medicine in medicines
                ],
            }
        elif intent == "general_health":
            result = call_service(
                CONSTANTS["routing"]["chatbot_module"], CONSTANTS["routing"]["chatbot_function"], message,
                previous_messages=previous_messages or [],
            )
        else:
            result = {"status": "not_implemented", "message": CONSTANTS["messages"]["handler_missing"].format(intent=intent)}
        results.append({"intent": intent, **result})

    result = make_result("response", "requests_routed", features=intents)
    result["results"] = results
    if needs_disclaimer:
        result["disclaimer"] = DOCTOR_DISCLAIMER
    return result
