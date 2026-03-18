import grpc
import time
import os
import logging
from grpc_interceptor import ClientInterceptor
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class RetryCircuitBreakerInterceptor(ClientInterceptor):
    
    def __init__(self):
        self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.last_failure_time = None
        self.window_start = time.time()

        self.failure_threshold = int(os.getenv("CB_FAILURE_THRESHOLD", "5"))
        self.reset_timeout = int(os.getenv("CB_RESET_TIMEOUT", "30"))
        self.window_seconds = int(os.getenv("CB_WINDOW_SECONDS", "60"))
        self.max_retries = int(os.getenv("RETRY_MAX_ATTEMPTS", "3"))
        self.backoff_base_ms = int(os.getenv("RETRY_BACKOFF_BASE", "100"))
        
        self.retry_codes = {
            grpc.StatusCode.UNAVAILABLE,
            grpc.StatusCode.DEADLINE_EXCEEDED,
            grpc.StatusCode.RESOURCE_EXHAUSTED,
        }
        
        self.no_retry_codes = {
            grpc.StatusCode.INVALID_ARGUMENT,
            grpc.StatusCode.NOT_FOUND,
            grpc.StatusCode.PERMISSION_DENIED,
            grpc.StatusCode.UNAUTHENTICATED,
        }

    def _should_retry(self, code: grpc.StatusCode, method_name: str) -> bool:
        if code in self.no_retry_codes:
            return False
        if code in self.retry_codes:
            return True
        if "Reserve" in method_name or "Release" in method_name:
            return code in self.retry_codes
        return False

    def _exponential_backoff(self, attempt: int) -> float:
        delay_ms = self.backoff_base_ms * (2 ** (attempt - 1))
        return min(delay_ms / 1000, 2.0)

    def _record_success(self):
        if self.state != CircuitState.CLOSED:
            logger.info(f"[CircuitBreaker] {self.state} → CLOSED (success)")
            self.state = CircuitState.CLOSED
        self.failure_count = 0
        self.window_start = time.time()

    def _record_failure(self):
        now = time.time()
        
        if now - self.window_start > self.window_seconds:
            self.failure_count = 0
            self.window_start = now
        
        self.failure_count += 1
        self.last_failure_time = now
        
        if self.state == CircuitState.CLOSED and self.failure_count >= self.failure_threshold:
            logger.warning(f"[CircuitBreaker] CLOSED → OPEN (failures: {self.failure_count})")
            self.state = CircuitState.OPEN
        elif self.state == CircuitState.HALF_OPEN:
            logger.warning(f"[CircuitBreaker] HALF_OPEN → OPEN (probe failed)")
            self.state = CircuitState.OPEN

    def _can_execute(self) -> bool:
        now = time.time()
        
        if self.state == CircuitState.CLOSED:
            return True
        elif self.state == CircuitState.OPEN:
            if now - self.last_failure_time >= self.reset_timeout:
                logger.info(f"[CircuitBreaker] OPEN → HALF_OPEN (timeout elapsed)")
                self.state = CircuitState.HALF_OPEN
                return True
            return False
        elif self.state == CircuitState.HALF_OPEN:
            return True
        return False

    def intercept(self, method, request_or_iterator, call_details):
        method_name = call_details.method
        
        if not self._can_execute():
            logger.error(f"[CircuitBreaker] Request blocked: circuit is OPEN")
            raise grpc.RpcError(
                grpc.StatusCode.UNAVAILABLE,
                "Service temporarily unavailable (circuit breaker OPEN)"
            )
        
        last_exception = None
        
        for attempt in range(1, self.max_retries + 1):
            try:
                result = method(request_or_iterator, call_details)
                self._record_success()
                return result
                
            except grpc.RpcError as e:
                code = e.code()
                last_exception = e
                
                if not self._should_retry(code, method_name):
                    logger.debug(f"[Retry] Not retrying {method_name}: {code}")
                    self._record_failure()
                    raise
                
                if attempt == self.max_retries:
                    logger.warning(f"[Retry] Max attempts reached for {method_name}")
                    self._record_failure()
                    raise
                
                delay = self._exponential_backoff(attempt)
                logger.info(f"[Retry] {method_name} attempt {attempt}/{self.max_retries} failed ({code}), retrying in {delay}s")
                time.sleep(delay)
        
        self._record_failure()
        raise last_exception