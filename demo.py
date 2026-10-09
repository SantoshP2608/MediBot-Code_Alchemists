"""Compatibility entry point; implementation lives in backend.extractor."""

from backend.extractor import Extraction, Medicine, SYSTEM_PROMPT, client, extract_query

__all__ = ["Extraction", "Medicine", "SYSTEM_PROMPT", "client", "extract_query"]


if __name__ == "__main__":
    print(extract_query("What are the side effects of Dolo 650?").model_dump_json(indent=2))
