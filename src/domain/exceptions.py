"""
Domain exceptions for error classification and recovery.
"""


class ConfigMonitorException(Exception):
    """Base exception for all configuration monitor errors."""
    pass


class ParserError(ConfigMonitorException):
    """Raised when parsing a configuration file fails due to invalid syntax."""
    def __init__(self, message: str, file_path: str = "", raw_snippet: str = ""):
        super().__init__(message)
        self.file_path = file_path
        self.raw_snippet = raw_snippet


class UnsupportedFormatError(ConfigMonitorException):
    """Raised when a file extension is not supported by any registered parser."""
    pass


class FileReadError(ConfigMonitorException):
    """Raised when an I/O error occurs while reading a monitored file."""
    pass


class CircuitBreakerOpenException(ConfigMonitorException):
    """Raised when an attempt to deliver via an open circuit breaker is rejected."""
    pass


class NotificationDispatchError(ConfigMonitorException):
    """Raised when sending an event to an external notification target fails."""
    pass
