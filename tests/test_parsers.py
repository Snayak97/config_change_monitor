"""
Unit tests for configuration parsers: JSON, YAML, .ENV, and .Properties.
"""

import textwrap
import pytest
from src.parsers.json_parser import JsonConfigParser
from src.parsers.yaml_parser import YamlConfigParser
from src.parsers.env_parser import EnvConfigParser
from src.parsers.properties_parser import PropertiesConfigParser
from src.parsers.factory import ParserFactory
from src.domain.models import FileFormat
from src.domain.exceptions import ParserError, UnsupportedFormatError


class TestJsonConfigParser:
    def setup_method(self):
        self.parser = JsonConfigParser()

    def test_parse_valid_json(self):
        raw = '{"service": "auth", "port": 8080, "active": true, "nested": {"key": "val"}}'
        result = self.parser.parse(raw)
        assert result["service"] == "auth"
        assert result["port"] == 8080
        assert result["active"] is True
        assert result["nested"]["key"] == "val"

    def test_parse_empty_json(self):
        assert self.parser.parse("") == {}
        assert self.parser.parse("   ") == {}

    def test_parse_invalid_json_raises_parser_error(self):
        malformed = '{"service": "auth", port: 8080}'
        with pytest.raises(ParserError) as exc_info:
            self.parser.parse(malformed)
        assert "JSON parse error" in str(exc_info.value)


class TestYamlConfigParser:
    def setup_method(self):
        self.parser = YamlConfigParser()

    def test_parse_valid_yaml(self):
        raw = textwrap.dedent("""
        logging:
          level: debug
        db:
          host: localhost
          port: 5432
        flags:
          - featureA
          - featureB
        """)
        result = self.parser.parse(raw)
        assert result["logging"]["level"] == "debug"
        assert result["db"]["host"] == "localhost"
        assert result["flags"] == ["featureA", "featureB"]


    def test_parse_empty_yaml(self):
        assert self.parser.parse("") == {}
        assert self.parser.parse("# Only comments\n") == {}

    def test_parse_invalid_yaml_raises_parser_error(self):
        malformed = """
        logging:
          level: [unclosed list
        """
        with pytest.raises(ParserError):
            self.parser.parse(malformed)


class TestEnvConfigParser:
    def setup_method(self):
        self.parser = EnvConfigParser()

    def test_parse_valid_env(self):
        raw = """
        # Application Settings
        APP_ENV=production
        PORT=9000
        DEBUG=false
        RATELIMIT_FACTOR=1.75
        API_KEY="secret-123="
        EXPORTED_VAR=test
        EMPTY_VAR=
        """
        result = self.parser.parse(raw)
        assert result["APP_ENV"] == "production"
        assert result["PORT"] == 9000
        assert result["DEBUG"] is False
        assert result["RATELIMIT_FACTOR"] == 1.75
        assert result["API_KEY"] == "secret-123="
        assert result["EXPORTED_VAR"] == "test"
        assert result["EMPTY_VAR"] == ""

    def test_parse_env_with_comments_and_spaces(self):
        raw = """
        KEY1=val1 # inline comment
        KEY2 = val2
        export KEY3=val3
        """
        result = self.parser.parse(raw)
        assert result["KEY1"] == "val1"
        assert result["KEY2"] == "val2"
        assert result["KEY3"] == "val3"


class TestPropertiesConfigParser:
    def setup_method(self):
        self.parser = PropertiesConfigParser()

    def test_parse_valid_properties(self):
        raw = """
        # Comments
        ! Also comments
        server.port = 8080
        spring.datasource.url: jdbc:postgresql://localhost:5432/db
        app.enabled = true
        app.timeout = 30.5
        """
        result = self.parser.parse(raw)
        assert result["server.port"] == 8080
        assert result["spring.datasource.url"] == "jdbc:postgresql://localhost:5432/db"
        assert result["app.enabled"] is True
        assert result["app.timeout"] == 30.5

    def test_parse_multiline_properties(self):
        raw = """
        message = Hello \\
                  World!
        """
        result = self.parser.parse(raw)
        assert result["message"] == "Hello World!"


class TestParserFactory:
    def setup_method(self):
        self.factory = ParserFactory()

    def test_detect_formats(self):
        assert self.factory.get_format_for_path("config.json") == FileFormat.JSON
        assert self.factory.get_format_for_path("app.yaml") == FileFormat.YAML
        assert self.factory.get_format_for_path("service.yml") == FileFormat.YAML
        assert self.factory.get_format_for_path(".env") == FileFormat.ENV
        assert self.factory.get_format_for_path(".env.production") == FileFormat.ENV
        assert self.factory.get_format_for_path("application.properties") == FileFormat.PROPERTIES
        assert self.factory.get_format_for_path("README.md") == FileFormat.UNKNOWN

    def test_unsupported_format_raises_error(self):
        with pytest.raises(UnsupportedFormatError):
            self.factory.get_parser_for_path("image.png")
