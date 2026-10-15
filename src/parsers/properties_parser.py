"""
Java / Spring .properties configuration parser.
Supports '=', ':', multi-line continuation with backslash, comments ('#', '!'),
and value type coercion.
"""

import re
from typing import Any, Dict
from src.parsers.base import BaseConfigParser
from src.domain.models import FileFormat
from src.domain.exceptions import ParserError


class PropertiesConfigParser(BaseConfigParser):
    @property
    def supported_format(self) -> FileFormat:
        return FileFormat.PROPERTIES

    @staticmethod
    def _coerce_type(value: str) -> Any:
        val = value.strip()
        lower = val.lower()
        if lower == "true":
            return True
        if lower == "false":
            return False
        if lower in ("null", "none"):
            return None

        # Integer
        if (val.startswith('-') and val[1:].isdigit()) or val.isdigit():
            try:
                return int(val)
            except ValueError:
                pass

        # Float
        if "." in val:
            try:
                return float(val)
            except ValueError:
                pass

        return val

    def parse(self, content: str) -> Dict[str, Any]:
        result: Dict[str, Any] = {}
        raw_lines = content.splitlines()

        # Handle backslash line continuations
        combined_lines = []
        buffer = ""
        for raw_line in raw_lines:
            line = raw_line.rstrip()
            if buffer:
                buffer += line.lstrip()
            else:
                buffer = line

            if buffer.endswith("\\") and not buffer.endswith("\\\\"):
                buffer = buffer[:-1]
            else:
                combined_lines.append(buffer)
                buffer = ""

        if buffer:
            combined_lines.append(buffer)

        # Parse key-values
        for line_num, line in enumerate(combined_lines, start=1):
            stripped = line.strip()
            if not stripped or stripped.startswith("#") or stripped.startswith("!"):
                continue

            # Find first unescaped '=' or ':'
            delimiter_match = re.search(r"(?<!\\)[=:]", stripped)
            if delimiter_match:
                split_idx = delimiter_match.start()
                key = stripped[:split_idx].strip()
                val = stripped[split_idx + 1:].strip()
            else:
                # Delimiter might be whitespace if neither '=' nor ':' is present
                parts = stripped.split(None, 1)
                key = parts[0].strip()
                val = parts[1].strip() if len(parts) > 1 else ""

            if not key:
                raise ParserError(
                    f"Invalid .properties format at line {line_num}: empty key",
                    raw_snippet=line
                )

            # Unescape colons and equals in keys
            key = key.replace(r"\=", "=").replace(r"\:", ":")
            val = val.replace(r"\=", "=").replace(r"\:", ":")

            result[key] = self._coerce_type(val)

        return result
