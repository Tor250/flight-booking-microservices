import grpc
import logging
import os
import threading
import time
from enum import Enum
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)
T = TypeVar("T")


class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerOpenError(grpc.RpcError):
    def __init__(self, message: str):
        super().__init__()
        self._message = message

    def code(self):
        return grpc.StatusCode.UNAVAILABLE

    def details(self):
        return self._message

    def __str__(self) -> str:
        return self._message


class RetryCircuitBreakerInterceptor:
    def __init__(self):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.window_start = time.time()
        self._lock = threading.Lock()

        self.failure_threshold = int(os.getenv("CB_FAILURE_THRESHOLD", "5"))
        self.reset_timeout = int(os.getenv("CB_RESET_TIMEOUT", "30"))
        self.window_seconds = int(os.getenv("CB_WINDOW_SECONDS", "60"))
        self.max_retries = int(os.getenv("RETRY_MAX_ATTEMPTS", "3"))
        self.backoff_base_ms = int(os.getenv("RETRY_BACKOFF_BASE", "100"))

        self.retry_codes = {
            grpc.StatusCode.UNAVAILABLE,
            grpc.StatusCode.DEADLINE_EXCEEDED,
        }
        self.no_retry_codes = {
            grpc.StatusCode.INVALID_ARGUMENT,
            grpc.StatusCode.NOT_FOUND,
            grpc.StatusCode.RESOURCE_EXHAUSTED,
            grpc.StatusCode.PERMISSION_DENIED,
            grpc.StatusCode.UNAUTHENTICATED,
            grpc.StatusCode.ALREADY_EXISTS,
        }

    def _should_retry(self, code: grpc.StatusCode) -> bool:
        if code in self.no_retry_codes:
            return False
        return code in self.retry_codes

    def _exponential_backoff(self, attempt: int) -> float:
        delay_ms = self.backoff_base_ms * (2 ** (attempt - 1))
        return min(delay_ms / 1000, 2.0)

    def _record_success(self):
        with self._lock:
            if self.state != CircuitState.CLOSED:
                logger.info("[CircuitBreaker] %s -> CLOSED (success)", self.state.value)
                self.state = CircuitState.CLOSED
            self.failure_count = 0
            self.window_start = time.time()

    def _record_failure(self):
        with self._lock:
            now = time.time()
            if now - self.window_start > self.window_seconds:
                self.failure_count = 0
                self.window_start = now

            self.failure_count += 1
            self.last_failure_time = now

            if self.state == CircuitState.CLOSED and self.failure_count >= self.failure_threshold:
                logger.warning("[CircuitBreaker] CLOSED -> OPEN (failures: %s)", self.failure_count)
                self.state = CircuitState.OPEN
            elif self.state == CircuitState.HALF_OPEN:
                logger.warning("[CircuitBreaker] HALF_OPEN -> OPEN (probe failed)")
                self.state = CircuitState.OPEN

    def _can_execute(self) -> bool:
        with self._lock:
            now = time.time()

            if self.state == CircuitState.CLOSED:
                return True
            if self.state == CircuitState.OPEN:
                if self.last_failure_time and now - self.last_failure_time >= self.reset_timeout:
                    logger.info("[CircuitBreaker] OPEN -> HALF_OPEN (timeout elapsed)")
                    self.state = CircuitState.HALF_OPEN
                    return True
                return False
            if self.state == CircuitState.HALF_OPEN:
                return True
            return False

    def execute(self, method_name: str, rpc_call: Callable[[], T]) -> T:
        if not self._can_execute():
            logger.error("[CircuitBreaker] Request blocked: circuit is OPEN")
            raise CircuitBreakerOpenError("Service temporarily unavailable (circuit breaker OPEN)")

        last_error = None

        for attempt in range(1, self.max_retries + 1):
            try:
                result = rpc_call()
                self._record_success()
                return result
            except grpc.RpcError as exc:
                code = exc.code()
                last_error = exc

                if not self._should_retry(code):
                    logger.debug("[Retry] Not retrying %s: %s", method_name, code)
                    self._record_failure()
                    raise

                if attempt == self.max_retries:
                    logger.warning("[Retry] Max attempts reached for %s", method_name)
                    self._record_failure()
                    raise

                delay = self._exponential_backoff(attempt)
                logger.info(
                    "[Retry] %s attempt %s/%s failed (%s), retrying in %ss",
                    method_name,
                    attempt,
                    self.max_retries,
                    code,
                    delay,
                )
                time.sleep(delay)

        self._record_failure()
        raise last_error
