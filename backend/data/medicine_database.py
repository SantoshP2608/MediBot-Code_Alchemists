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
