"""Load shared settings from the project-root constants.txt JSON file."""

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONSTANTS_FILE = PROJECT_ROOT / "constants.txt"
CONSTANTS = json.loads(CONSTANTS_FILE.read_text(encoding="utf-8"))
if not isinstance(CONSTANTS, dict):
    raise ValueError("constants.txt must contain a JSON object.")
