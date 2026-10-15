"""
Exponential backoff with full jitter for resilient network retries.
"""

import asyncio
import random
from typing import Callable, Coroutine, TypeVar, Any
from loguru import logger

T = TypeVar("T")


def calculate_backoff_delay(
    attempt: int,
    base_delay: float = 1.0,
    multiplier: float = 2.0,
    max_delay: float = 30.0,
    jitter: bool = True
) -> float:
    """
    Calculate exponential delay: min(max_delay, base_delay * (multiplier ** (attempt - 1)))
    Applies full random jitter between 0 and calculated delay to prevent retry storms.
    """
    delay = min(max_delay, base_delay * (multiplier ** max(0, attempt - 1)))
    if jitter:
        delay = random.uniform(0.5 * delay, delay)
    return delay


async def retry_with_backoff(
    coro_func: Callable[[], Coroutine[Any, Any, T]],
    max_retries: int = 3,
    base_delay: float = 1.0,
    multiplier: float = 2.0,
    max_delay: float = 30.0,
    operation_name: str = "operation"
) -> T:
    """
    Execute async callable with exponential backoff retries.
    """
    last_error: Exception = RuntimeError("No attempts executed")

    for attempt in range(1, max_retries + 1):
        try:
            return await coro_func()
        except Exception as ex:
            last_error = ex
            if attempt == max_retries:
                logger.error(
                    f"[{operation_name}] Exceeded maximum retry attempts ({max_retries}). Last error: {ex}"
                )
                raise ex

            sleep_duration = calculate_backoff_delay(
                attempt,
                base_delay=base_delay,
                multiplier=multiplier,
                max_delay=max_delay
            )
            logger.warning(
                f"[{operation_name}] Attempt {attempt}/{max_retries} failed ({ex}). Retrying in {sleep_duration:.2f}s..."
            )
            await asyncio.sleep(sleep_duration)

    raise last_error
