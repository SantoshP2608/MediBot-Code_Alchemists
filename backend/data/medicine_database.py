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


def product_name_aliases(key: str) -> set[str]:
    """Recognize a brand or brand/form while leaving product choice unresolved."""
    words = key.split()
    forms = set(CONSTANTS['matching']['forms']) | {'infusion', 'solution', 'ointment'}
    brand = []
    for word in words:
        if word.isdigit() or word in forms:
            break
        brand.append(word)
    aliases = set()
    if brand and len(' '.join(brand)) >= 3:
        aliases.add(' '.join(brand))
        # A formulation can be supplied without the intervening strength.
        without_strength = re.sub(r'\b\d+(?:\s+(?:mg|mcg|g|ml|iu))?\b', '', key)
        aliases.add(' '.join(without_strength.split()))
    return aliases


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
    if not matches:
        matches = [record for key, record in records
                   if name in product_name_aliases(key) and matches_strength(record)]
    unique = []
    comparable = []
    for record in matches:
        normalized_record = {**record, 'name': normalize(record['name'])}
        if normalized_record not in comparable:
            unique.append(record)
            comparable.append(normalized_record)
    return unique


def ingredient_query_parts(medicine: Medicine):
    """Recognize ingredient queries with an optional strength and dosage form."""
    name = normalize(medicine.name)
    if not name or any(key == name for key, _ in load_database()):
        return None
    form = None
    words = name.split()
    forms = set(CONSTANTS['matching']['forms'])
    if words and words[-1].rstrip('s') in forms:
        form = words.pop().rstrip('s')
    name = ' '.join(words)
    strength = normalize(medicine.strength or '')
    match = re.fullmatch(r'(.+?) (\d+) (mg|mcg|g|ml|iu)', name)
    if match:
        name = match[1]
        embedded = match[2] + ' ' + match[3]
        if strength and strength != embedded:
            return None
        strength = embedded
    if any(normalize(item.get('drug', '')) == name
           for _, row in load_database() for item in row.get('composition', [])):
        return name, strength, form
    return None


def is_ingredient_query(medicine: Medicine) -> bool:
    """An ingredient alone is not a choice of a particular branded product."""
    return ingredient_query_parts(medicine) is not None


def suggest_products(medicine: Medicine) -> list[dict]:
    """Find selectable products by product name or exact ingredient name."""
    name = normalize(medicine.name)
    if not name:
        return []
    strength = normalize(medicine.strength or '')
    ingredient = ingredient_query_parts(medicine)
    form = None
    if ingredient:
        name, strength, form = ingredient
    allowed = set(CONSTANTS['regulatory']['allowed_categories'])
    suggestions = []
    seen = set()
    for key, record in load_database():
        composition = record.get('composition', [])
        ingredient_match = any(normalize(item.get('drug', '')) == name for item in composition)
        if ingredient and not ingredient_match:
            continue
        if form and form not in {word.rstrip('s') for word in key.split()}:
            continue
        if not (key == name or key.startswith(name + ' ') or ingredient_match
                or name in product_name_aliases(key)):
            continue
        if normalize(record.get('regulatory', '')) not in allowed:
            continue
        if strength:
            values = [normalize(item.get('strength') or '') for item in composition
                      if not ingredient or normalize(item.get('drug', '')) == name]
            if not ((not ingredient and (' ' + strength + ' ') in (' ' + key + ' ')) or
                    any(value == strength or (strength.isdigit() and value.split()[:1] == [strength])
                        for value in values)):
                continue
        if key in seen:
            continue
        seen.add(key)
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


def explicit_medicine_mentions(message: str) -> list[Medicine]:
    """Recover literal database product/ingredient mentions, never infer from symptoms."""
    words = normalize(message).split()
    spans = {}
    for start in range(len(words)):
        # Bound phrase lengths so long user messages cannot allocate a quadratic
        # number of large strings. This is a literal-name fallback only.
        for end in range(start + 1, min(start + 32, len(words)) + 1):
            spans.setdefault(' '.join(words[start:end]), []).append((start, end))
    found = {}
    for key, record in load_database():
        for alias in product_name_aliases(key):
            if alias in spans:
                for start, end in spans[alias]:
                    found.setdefault((start, end), alias)
        if key in spans:
            for start, end in spans[key]:
                found[(start, end)] = record['name']
        for ingredient in record.get('composition', []):
            name = normalize(ingredient.get('drug', ''))
            if name in spans:
                for start, end in spans[name]:
                    found.setdefault((start, end), ingredient['drug'])
    # Prefer an exact product over an ingredient occurring inside that product.
    chosen = []
    for (start, end), name in sorted(found.items(), key=lambda row: (-(row[0][1] - row[0][0]), row[0][0])):
        if any(start < other_end and end > other_start for other_start, other_end, _ in chosen):
            continue
        strength = None
        if end < len(words) and words[end].isdigit():
            strength = words[end]
            if end + 1 < len(words) and words[end + 1] in {'mg', 'mcg', 'g', 'ml', 'iu'}:
                strength += words[end + 1]
        chosen.append((start, end, Medicine(name=name, strength=strength)))
    return [medicine for _, _, medicine in sorted(chosen, key=lambda row: row[0])]
