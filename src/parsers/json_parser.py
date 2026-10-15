"""
JSON configuration parser with resilient error handling.
"""

import json
from typing import Any, Dict
from src.parsers.base import BaseConfigParser
from src.domain.models import FileFormat
from src.domain.exceptions import ParserError


class JsonConfigParser(BaseConfigParser):
    @property
    def supported_format(self) -> FileFormat:
        return FileFormat.JSON

    def parse(self, content: str) -> Dict[str, Any]:
        cleaned = content.strip()
        if not cleaned:
            return {}

        try:
            parsed = json.loads(cleaned)
            if not isinstance(parsed, dict):
                # Wrap top-level array or scalar in root key
                return {"_root": parsed}
            return parsed
        except json.JSONDecodeError as err:
            raise ParserError(
                f"JSON parse error at line {err.lineno}, col {err.colno}: {err.msg}",
                raw_snippet=cleaned[:200]
            ) from err
        except Exception as ex:
            raise ParserError(f"Unexpected error parsing JSON: {str(ex)}") from ex
