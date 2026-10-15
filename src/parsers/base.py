"""
Base configuration parser interface.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict
from src.domain.models import FileFormat


class BaseConfigParser(ABC):
    """Abstract base class for all configuration format parsers."""

    @abstractmethod
    def parse(self, content: str) -> Dict[str, Any]:
        """
        Parse raw configuration text into a Python dictionary.

        Raises:
            ParserError: If the content is malformed or invalid syntax.
        """
        pass

    @property
    @abstractmethod
    def supported_format(self) -> FileFormat:
        """Return the FileFormat enum value this parser handles."""
        pass
