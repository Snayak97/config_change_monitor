"""
.env configuration parser supporting comments, quoted values, and type inference.
"""

from typing import Any, Dict
from src.parsers.base import BaseConfigParser
from src.domain.models import FileFormat
from src.domain.exceptions import ParserError


class EnvConfigParser(BaseConfigParser):
    @property
    def supported_format(self) -> FileFormat:
        return FileFormat.ENV

    @staticmethod
    def _coerce_type(value: str) -> Any:
        val = value.strip()
        # Preserve explicitly quoted strings without changing type
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            return val[1:-1]

        lower = val.lower()
        if lower == "true":
            return True
        if lower == "false":
            return False
        if lower in ("null", "none"):
            return None

        # Check integer
        if (val.startswith('-') and val[1:].isdigit()) or val.isdigit():
            try:
                return int(val)
            except ValueError:
                pass

        # Check float
        if "." in val:
            try:
                return float(val)
            except ValueError:
                pass

        return val

    def parse(self, content: str) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        lines = content.splitlines()

        for line_num, line in enumerate(lines, start=1):
            stripped = line.strip()
            # Ignore empty lines and full comment lines
            if not stripped or stripped.startswith("#"):
                continue

            # Strip export prefix if present: export KEY=VAL
            if stripped.startswith("export "):
                stripped = stripped[7:].strip()

            if "=" not in stripped:
                # Key with no value is treated as empty string
                key = stripped
                result[key] = ""
                continue

            parts = stripped.split("=", 1)
            key = parts[0].strip()
            raw_value = parts[1].strip()

            if not key:
                raise ParserError(
                    f"Invalid .env line {line_num}: missing key before '='",
                    raw_snippet=line
                )

            # Strip inline comment if value is not quoted
            if not ((raw_value.startswith('"') and raw_value.endswith('"')) or
                    (raw_value.startswith("'") and raw_value.endswith("'"))):
                if "#" in raw_value:
                    raw_value = raw_value.split("#", 1)[0].strip()

            result[key] = self._coerce_type(raw_value)

        return result
