"""
Parser factory for dynamic selection of parser based on file extension or format.
"""

import os
from typing import Dict
from src.domain.models import FileFormat
from src.domain.exceptions import UnsupportedFormatError
from src.parsers.base import BaseConfigParser
from src.parsers.json_parser import JsonConfigParser
from src.parsers.yaml_parser import YamlConfigParser
from src.parsers.env_parser import EnvConfigParser
from src.parsers.properties_parser import PropertiesConfigParser


class ParserFactory:
    """Factory to instantiate and retrieve configuration parsers."""

    def __init__(self):
        self._parsers: Dict[FileFormat, BaseConfigParser] = {
            FileFormat.JSON: JsonConfigParser(),
            FileFormat.YAML: YamlConfigParser(),
            FileFormat.ENV: EnvConfigParser(),
            FileFormat.PROPERTIES: PropertiesConfigParser(),
        }

    def get_format_for_path(self, file_path: str) -> FileFormat:
        base_name = os.path.basename(file_path).lower()
        ext = os.path.splitext(file_path)[1].lower()

        if base_name in (".env", "env") or base_name.startswith(".env.") or ext == ".env":
            return FileFormat.ENV
        if ext in (".json",):
            return FileFormat.JSON
        if ext in (".yaml", ".yml"):
            return FileFormat.YAML
        if ext in (".properties", ".prop"):
            return FileFormat.PROPERTIES

        return FileFormat.UNKNOWN

    def get_parser_for_path(self, file_path: str) -> BaseConfigParser:
        fmt = self.get_format_for_path(file_path)
        if fmt == FileFormat.UNKNOWN or fmt not in self._parsers:
            raise UnsupportedFormatError(
                f"Unsupported configuration file format for path '{file_path}'. "
                f"Supported extensions: .json, .yaml, .yml, .env, .properties"
            )
        return self._parsers[fmt]

    def register_parser(self, file_format: FileFormat, parser: BaseConfigParser) -> None:
        """Allow runtime extension of custom parsers (extensible design)."""
        self._parsers[file_format] = parser


# Global factory instance
default_parser_factory = ParserFactory()
