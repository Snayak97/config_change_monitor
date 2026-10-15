"""
Circuit Breaker Pattern implementation (Closed, Open, Half-Open).
Protects downstream services from cascade failure and avoids network resource exhaustion.
"""

import time
from enum import Enum
from typing import Dict, Any
from loguru import logger
from src.domain.exceptions import CircuitBreakerOpenException


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """
    Manages failure tracking and states for an external target.
    Transitions:
      CLOSED -> failure_count >= threshold -> OPEN
      OPEN -> recovery_timeout elapsed -> HALF_OPEN
      HALF_OPEN -> success -> CLOSED
      HALF_OPEN -> failure -> OPEN
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 20.0
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout_seconds

        self.state: CircuitState = CircuitState.CLOSED
        self.failure_count: int = 0
        self.success_count: int = 0
        self.last_failure_time: float = 0.0
        self.last_state_change: float = time.time()

    def can_execute(self) -> bool:
        """Evaluate if calls are allowed through the breaker."""
        now = time.time()

        if self.state == CircuitState.CLOSED:
            return True

        if self.state == CircuitState.OPEN:
            if now - self.last_failure_time >= self.recovery_timeout:
                logger.info(f"CircuitBreaker [{self.name}] transitioning from OPEN -> HALF_OPEN (probing target)")
                self.state = CircuitState.HALF_OPEN
                self.last_state_change = now
                return True
            return False

        if self.state == CircuitState.HALF_OPEN:
            # Allow trial request
            return True

        return False

    def record_success(self) -> None:
        """Record successful execution."""
        if self.state == CircuitState.HALF_OPEN:
            logger.info(f"CircuitBreaker [{self.name}] probe succeeded. Transitioning HALF_OPEN -> CLOSED")
            self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.last_state_change = time.time()
        elif self.state == CircuitState.CLOSED:
            self.failure_count = 0

        self.success_count += 1

    def record_failure(self, error: Exception) -> None:
        """Record failed execution and evaluate state transition."""
        now = time.time()
        self.last_failure_time = now
        self.failure_count += 1

        if self.state == CircuitState.HALF_OPEN:
            logger.warning(
                f"CircuitBreaker [{self.name}] probe failed ({error}). Transitioning HALF_OPEN -> OPEN"
            )
            self.state = CircuitState.OPEN
            self.last_state_change = now
        elif self.state == CircuitState.CLOSED and self.failure_count >= self.failure_threshold:
            logger.error(
                f"CircuitBreaker [{self.name}] failure threshold reached ({self.failure_count}/{self.failure_threshold}). "
                f"Opening circuit for {self.recovery_timeout}s"
            )
            self.state = CircuitState.OPEN
            self.last_state_change = now

    def reset(self) -> None:
        """Manual reset to CLOSED state."""
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_state_change = time.time()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "state": self.state.value,
            "failure_count": self.failure_count,
            "failure_threshold": self.failure_threshold,
            "recovery_timeout_seconds": self.recovery_timeout,
            "last_failure_time": self.last_failure_time
        }
