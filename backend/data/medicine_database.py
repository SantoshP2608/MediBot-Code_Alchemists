"""Shared medicine lookup used by safety checks and response routing."""

from backend.config.settings import CONSTANTS, PROJECT_ROOT

import json
import re
from functools import lru_cache

from backend.models.schemas import Medicine


MEDICINE_DATABASE = PROJECT_ROOT / CONSTANTS["paths"]["medicine_database"]


def normalize(value: str) -> str:
    value = re.sub(CONSTANTS["patterns"]["split_letter_numbers"], CONSTANTS["patterns"]["single_space"], value)
    return " ".join(re.findall(CONSTANTS["patterns"]["word_or_number"], value.casefold()))


@lru_cache(maxsize=CONSTANTS["routing"]["database_cache_size"])
def load_database() -> tuple[tuple[str, dict], ...]:
    with MEDICINE_DATABASE.open(encoding="utf-8") as database_file:
        records = json.load(database_file)
    return tuple((normalize(record["name"]), record) for record in records)


def find_medicine(medicine: Medicine) -> list[dict]:
    name = normalize(medicine.name)
    if not name:
        return []
    strength = normalize(medicine.strength or "")
    records = load_database()

    def matches_strength(record):
        if not strength:
            return True
        if " " + strength + " " in " " + normalize(record["name"]) + " ":
            return True
        # A single-ingredient composition can verify units omitted in the name.
        composition = record.get("composition", [])
        return (len(composition) == 1 and
                normalize(composition[0].get("strength") or "") == strength)

    matches = [record for key, record in records if key == name and matches_strength(record)]
    if not matches:
        matches = [record for key, record in records
                   if key.startswith(name + " ") and matches_strength(record)]
    unique = []
    for record in matches:
        if record not in unique:
            unique.append(record)
    return unique


def suggest_products(medicine: Medicine) -> list[dict]:
    """Find selectable products by product name or exact ingredient name."""
    name = normalize(medicine.name)
    if not name:
        return []
    strength = normalize(medicine.strength or '')
    allowed = set(CONSTANTS['regulatory']['allowed_categories'])
    suggestions = []
    seen = set()
    for key, record in load_database():
        composition = record.get('composition', [])
        ingredient_match = any(normalize(item.get('drug', '')) == name for item in composition)
        if not ((' ' + name + ' ') in (' ' + key + ' ') or ingredient_match):
            continue
        if normalize(record.get('regulatory', '')) not in allowed:
            continue
        if strength:
            values = [normalize(item.get('strength') or '') for item in composition]
            if not ((' ' + strength + ' ') in (' ' + key + ' ') or
                    any(value == strength or (strength.isdigit() and value.split()[:1] == [strength])
                        for value in values)):
                continue
        if record['name'] in seen:
            continue
        seen.add(record['name'])
        suggestions.append(record)
    # Single-ingredient products precede combinations; stable alphabetical order.
    suggestions.sort(key=lambda row: (
        len(row.get('composition', [])) != 1,
        (' ' + name + ' ') not in (' ' + normalize(row['name']) + ' '),
        normalize(row['name']),
    ))
    # Exact selections must not resolve to conflicting database records.
    verified = []
    for row in suggestions:
        if len(find_medicine(Medicine(name=row['name'], strength=None))) == 1:
            verified.append(row)
            if len(verified) >= CONSTANTS['routing']['candidate_limit']:
                break
    return verified
