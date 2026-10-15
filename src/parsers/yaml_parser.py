"""
YAML configuration parser supporting both single and multi-document YAML.
"""

from typing import Any, Dict
import yaml
from src.parsers.base import BaseConfigParser
from src.domain.models import FileFormat
from src.domain.exceptions import ParserError


class YamlConfigParser(BaseConfigParser):
    @property
    def supported_format(self) -> FileFormat:
        return FileFormat.YAML

    def parse(self, content: str) -> Dict[str, Any]:
        cleaned = content.strip()
        if not cleaned:
            return {}

        try:
            # safe_load_all supports multiple YAML documents in one stream
            docs = list(yaml.safe_load_all(cleaned))
            if not docs:
                return {}

            # If single document
            if len(docs) == 1:
                doc = docs[0]
                if doc is None:
                    return {}
                if isinstance(doc, dict):
                    return doc
                return {"_root": doc}

            # If multi-document, merge or index
            merged: Dict[str, Any] = {}
            for idx, doc in enumerate(docs):
                if isinstance(doc, dict):
                    merged.update(doc)
                elif doc is not None:
                    merged[f"doc_{idx}"] = doc
            return merged
        except yaml.YAMLError as err:
            mark = getattr(err, "problem_mark", None)
            loc = f" at line {mark.line + 1}, col {mark.column + 1}" if mark else ""
            raise ParserError(
                f"YAML syntax error{loc}: {str(err)}",
                raw_snippet=cleaned[:200]
            ) from err
        except Exception as ex:
            raise ParserError(f"Unexpected error parsing YAML: {str(ex)}") from ex
