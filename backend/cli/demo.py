"""Compatibility entry point; implementation lives in backend.llm.extractor."""

from backend.config.settings import CONSTANTS
from backend.llm.extractor import Extraction, Medicine, SYSTEM_PROMPT, client, extract_query

__all__ = ["Extraction", "Medicine", "SYSTEM_PROMPT", "client", "extract_query"]


if __name__ == "__main__":
    print(extract_query(CONSTANTS["display"]["demo_query"]).model_dump_json(indent=CONSTANTS["display"]["json_indent"]))
