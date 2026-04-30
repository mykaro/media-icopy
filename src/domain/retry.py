"""Logic for retrying failed operations with exponential backoff."""

import time
import logging
from typing import Callable, TypeVar, Any

from .exceptions import TransientError, FatalError

logger = logging.getLogger(__name__)

T = TypeVar("T")


def execute_with_retry(
    func: Callable[..., T],
    max_attempts: int,
    backoff_seconds: list[int],
    *args: Any,
    **kwargs: Any,
) -> T:
    """
    Executes a function and retries on TransientError.

    Args:
        func: The function to execute.
        max_attempts: Maximum number of attempts (including the first one).
        backoff_seconds: List of wait times between attempts.
        *args: Positional arguments for the function.
        **kwargs: Keyword arguments for the function.

    Returns:
        The return value of the executed function.

    Raises:
        FatalError: If a non-retryable error occurs.
        TransientError: If max attempts are reached without success.
    """
    last_error: Exception | None = None

    on_transient_error = kwargs.pop("on_transient_error", None)

    for attempt in range(max_attempts):
        try:
            return func(*args, **kwargs)
        except TransientError as e:
            last_error = e
            if attempt == max_attempts - 1:
                logger.error(f"Max retries reached. Last error: {e}")
                raise

            if on_transient_error:
                on_transient_error(e)

            wait_time = (
                backoff_seconds[attempt]
                if attempt < len(backoff_seconds)
                else backoff_seconds[-1]
            )
            logger.warning(
                f"Attempt {attempt + 1}/{max_attempts} failed: {e}. Retrying in {wait_time}s..."
            )
            time.sleep(wait_time)

        except FatalError as e:
            logger.error(f"Fatal error encountered: {e}")
            raise

    # Should not be reached due to re-raise in loop, but for safety:
    if last_error:
        raise last_error
    raise TransientError("Unknown error in retry loop")
