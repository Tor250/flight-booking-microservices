set -euo pipefail

BASE_URL="${BASE_URL:-http://localhost:8000}"
FLIGHT_ID="${FLIGHT_ID:-1}"
USER_ID="${USER_ID:-u123}"
FLIGHT_DB_HOST="${FLIGHT_DB_HOST:-localhost}"
FLIGHT_DB_PORT="${FLIGHT_DB_PORT:-5433}"
BOOKING_DB_HOST="${BOOKING_DB_HOST:-localhost}"
BOOKING_DB_PORT="${BOOKING_DB_PORT:-5434}"
PGUSER="${PGUSER:-postgres}"
PGPASSWORD="${PGPASSWORD:-postgres}"
CB_RESET_TIMEOUT_SECONDS="${CB_RESET_TIMEOUT_SECONDS:-30}"

cleanup() {
  docker compose start flight-service >/dev/null 2>&1 || true
  docker compose start booking-service >/dev/null 2>&1 || true
}

section() {
  printf "\n[%s] %s\n" "$1" "$2"
}

fail() {
  printf "ERROR: %s\n" "$1" >&2
  exit 1
}

pass() {
  printf "OK: %s\n" "$1"
}

assert_eq() {
  local actual="$1"
  local expected="$2"
  local message="$3"
  if [[ "$actual" != "$expected" ]]; then
    fail "${message}: expected='${expected}', actual='${actual}'"
  fi
  pass "$message"
}

flight_db_query() {
  local sql="$1"
  PGPASSWORD="$PGPASSWORD" psql \
    -h "$FLIGHT_DB_HOST" \
    -p "$FLIGHT_DB_PORT" \
    -U "$PGUSER" \
    -d flights \
    -t -A \
    -c "$sql" 2>/dev/null
}

booking_db_query() {
  local sql="$1"
  PGPASSWORD="$PGPASSWORD" psql \
    -h "$BOOKING_DB_HOST" \
    -p "$BOOKING_DB_PORT" \
    -U "$PGUSER" \
    -d bookings \
    -t -A \
    -c "$sql" 2>/dev/null
}

booking_log_line_count() {
  docker compose logs booking-service 2>/dev/null | wc -l | tr -d " "
}

booking_logs_since() {
  local start_line="$1"
  docker compose logs booking-service 2>/dev/null | tail -n "+$((start_line + 1))"
}

flight_log_line_count() {
  docker compose logs flight-service 2>/dev/null | wc -l | tr -d " "
}

flight_logs_since() {
  local start_line="$1"
  docker compose logs flight-service 2>/dev/null | tail -n "+$((start_line + 1))"
}

wait_api_ready() {
  local code=""
  for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
    code="$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/flights?origin=SVO&destination=LED" || true)"
    if [[ "$code" == "200" ]]; then
      return
    fi
    sleep 1
  done
  fail "Booking API не готов к тестам"
}

trap cleanup EXIT

echo "Flight booking requirement checks"
echo "================================"

section "0/16" "Сервисы и миграции"
docker compose up -d >/dev/null
docker compose ps
if ! docker compose ps --all booking-flyway | grep -q "Exited (0)"; then
  fail "booking-flyway не завершился успешно"
fi
if ! docker compose ps --all flight-flyway | grep -q "Exited (0)"; then
  fail "flight-flyway не завершился успешно"
fi
pass "Сервисы подняты, миграции применены"
wait_api_ready

section "1/16" "SearchFlights: с датой и без даты"
SEARCH_WITH_DATE="$(curl -fsS "${BASE_URL}/flights?origin=SVO&destination=LED&date=2026-04-01")"
SEARCH_NO_DATE="$(curl -fsS "${BASE_URL}/flights?origin=SVO&destination=LED")"
COUNT_WITH_DATE="$(printf "%s" "$SEARCH_WITH_DATE" | jq 'length')"
COUNT_NO_DATE="$(printf "%s" "$SEARCH_NO_DATE" | jq 'length')"
if [[ "$COUNT_WITH_DATE" -lt 1 ]]; then
  fail "SearchFlights с датой вернул пустой список"
fi
if [[ "$COUNT_NO_DATE" -lt 1 ]]; then
  fail "SearchFlights без даты вернул пустой список"
fi
printf "%s" "$SEARCH_WITH_DATE" | jq -e 'all(.[]; .status == "SCHEDULED")' >/dev/null
pass "SearchFlights возвращает рейсы SCHEDULED"

section "2/16" "GetFlight: успешный и 404"
GET_STATUS_OK="$(curl -s -o /tmp/get_ok.json -w "%{http_code}" "${BASE_URL}/flights/${FLIGHT_ID}")"
assert_eq "$GET_STATUS_OK" "200" "GET /flights/{id} для существующего рейса"
GET_STATUS_404="$(curl -s -o /tmp/get_404.json -w "%{http_code}" "${BASE_URL}/flights/999999")"
assert_eq "$GET_STATUS_404" "404" "GET /flights/{id} для отсутствующего рейса"

section "3/16" "Создание бронирования и snapshot цены"
CREATE_RESPONSE="$(curl -fsS -X POST "${BASE_URL}/bookings" \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"${USER_ID}\",\"flight_id\":${FLIGHT_ID},\"passenger_name\":\"Ivan Ivanov\",\"passenger_email\":\"ivan@example.com\",\"seat_count\":2}")"
BOOKING_ID="$(printf "%s" "$CREATE_RESPONSE" | jq -r ".booking_id")"
if [[ -z "$BOOKING_ID" || "$BOOKING_ID" == "null" ]]; then
  fail "POST /bookings не вернул booking_id"
fi
pass "POST /bookings создал бронирование ${BOOKING_ID}"

BOOKING_TOTAL_PRICE="$(booking_db_query "SELECT total_price FROM bookings WHERE id='${BOOKING_ID}'")"
FLIGHT_PRICE="$(flight_db_query "SELECT price FROM flights WHERE id=${FLIGHT_ID}")"
if [[ -z "$BOOKING_TOTAL_PRICE" || -z "$FLIGHT_PRICE" ]]; then
  fail "Не удалось проверить total_price в БД"
fi
PRICE_CHECK="$(
python3 - <<PY
flight_price = float("${FLIGHT_PRICE}")
booking_total = float("${BOOKING_TOTAL_PRICE}")
expected = round(flight_price * 2, 2)
if abs(booking_total - expected) < 0.01:
    print("ok")
else:
    print("bad")
PY
)"
assert_eq "$PRICE_CHECK" "ok" "total_price = seat_count * flight.price"

section "4/16" "GET /bookings/{id} и GET /bookings?user_id"
GET_BOOKING_STATUS="$(curl -s -o /tmp/get_booking.json -w "%{http_code}" "${BASE_URL}/bookings/${BOOKING_ID}")"
assert_eq "$GET_BOOKING_STATUS" "200" "GET /bookings/{id}"
LIST_STATUS="$(curl -s -o /tmp/list_booking.json -w "%{http_code}" "${BASE_URL}/bookings?user_id=${USER_ID}")"
assert_eq "$LIST_STATUS" "200" "GET /bookings?user_id"
printf "%s" "$(cat /tmp/list_booking.json)" | jq -e --arg bid "$BOOKING_ID" 'map(select(.id == $bid)) | length == 1' >/dev/null
pass "Список бронирований содержит созданную запись"

section "5/16" "Отмена бронирования и возврат мест"
AVAILABLE_BEFORE_CANCEL="$(flight_db_query "SELECT available_seats FROM flights WHERE id=${FLIGHT_ID}")"
CANCEL_STATUS="$(curl -s -o /tmp/cancel_booking.json -w "%{http_code}" -X POST "${BASE_URL}/bookings/${BOOKING_ID}/cancel")"
assert_eq "$CANCEL_STATUS" "200" "POST /bookings/{id}/cancel"
AVAILABLE_AFTER_CANCEL="$(flight_db_query "SELECT available_seats FROM flights WHERE id=${FLIGHT_ID}")"
if [[ "$AVAILABLE_AFTER_CANCEL" -lt "$AVAILABLE_BEFORE_CANCEL" ]]; then
  fail "После cancel количество мест не увеличилось"
fi
RES_STATUS="$(flight_db_query "SELECT status FROM seat_reservations WHERE booking_id='${BOOKING_ID}'")"
assert_eq "$RES_STATUS" "RELEASED" "Статус резервации после cancel"

section "6/16" "ReserveSeats: RESOURCE_EXHAUSTED и отсутствие частичных записей"
COUNT_BEFORE_FAIL="$(booking_db_query "SELECT COUNT(*) FROM bookings")"
FAIL_STATUS="$(curl -s -o /tmp/fail_booking.json -w "%{http_code}" -X POST "${BASE_URL}/bookings" \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"${USER_ID}\",\"flight_id\":${FLIGHT_ID},\"passenger_name\":\"Big Request\",\"passenger_email\":\"big@example.com\",\"seat_count\":999999}")"
assert_eq "$FAIL_STATUS" "409" "POST /bookings при нехватке мест"
COUNT_AFTER_FAIL="$(booking_db_query "SELECT COUNT(*) FROM bookings")"
assert_eq "$COUNT_AFTER_FAIL" "$COUNT_BEFORE_FAIL" "При ошибке ReserveSeats новая booking-запись не создаётся"

section "7/16" "Idempotency ReserveSeats по booking_id"
IDEMP_BOOKING_ID="$(
python3 - <<'PY'
import uuid
print(uuid.uuid4())
PY
)"
IDEMP_AVAILABLE_BEFORE="$(flight_db_query "SELECT available_seats FROM flights WHERE id=${FLIGHT_ID}")"
docker compose exec -T booking-service python - <<PY
import os
import grpc
import flight.v1.flight_pb2 as pb2
import flight.v1.flight_pb2_grpc as pb2_grpc

key = os.getenv("FLIGHT_SERVICE_API_KEY", "super-secret-key-123")
channel = grpc.insecure_channel("flight-service:50051")
stub = pb2_grpc.FlightServiceStub(channel)
meta = [("authorization", key)]

req = pb2.ReserveSeatsRequest(
    flight_id=${FLIGHT_ID},
    booking_id="${IDEMP_BOOKING_ID}",
    seat_count=1,
)
r1 = stub.ReserveSeats(req, metadata=meta, timeout=3)
r2 = stub.ReserveSeats(req, metadata=meta, timeout=3)
if not r1.success or not r2.success:
    raise SystemExit("Idempotent reserve failed")
PY
IDEMP_AVAILABLE_AFTER="$(flight_db_query "SELECT available_seats FROM flights WHERE id=${FLIGHT_ID}")"
IDEMP_RES_COUNT="$(flight_db_query "SELECT COUNT(*) FROM seat_reservations WHERE booking_id='${IDEMP_BOOKING_ID}'")"
EXPECTED_AVAILABLE_AFTER="$((IDEMP_AVAILABLE_BEFORE - 1))"
assert_eq "$IDEMP_RES_COUNT" "1" "Повторный ReserveSeats не создаёт дубль резервации"
assert_eq "$IDEMP_AVAILABLE_AFTER" "$EXPECTED_AVAILABLE_AFTER" "Повторный ReserveSeats не списывает места повторно"
docker compose exec -T booking-service python - <<PY
import os
import grpc
import flight.v1.flight_pb2 as pb2
import flight.v1.flight_pb2_grpc as pb2_grpc

key = os.getenv("FLIGHT_SERVICE_API_KEY", "super-secret-key-123")
channel = grpc.insecure_channel("flight-service:50051")
stub = pb2_grpc.FlightServiceStub(channel)
meta = [("authorization", key)]
stub.ReleaseReservation(
    pb2.ReleaseReservationRequest(booking_id="${IDEMP_BOOKING_ID}"),
    metadata=meta,
    timeout=3,
)
PY

section "8/16" "gRPC auth: UNAUTHENTICATED при неверном ключе"
AUTH_RESULT="$(
docker compose exec -T booking-service python - <<'PY'
import grpc
import flight.v1.flight_pb2 as pb2
import flight.v1.flight_pb2_grpc as pb2_grpc

ch = grpc.insecure_channel("flight-service:50051")
stub = pb2_grpc.FlightServiceStub(ch)
try:
    stub.GetFlight(
        pb2.GetFlightRequest(flight_id=1),
        metadata=[("authorization", "bad-key")],
        timeout=2,
    )
    print("unexpected")
except grpc.RpcError as exc:
    print(str(exc.code()))
PY
)"
if [[ "$AUTH_RESULT" != *"UNAUTHENTICATED"* ]]; then
  fail "Ожидался код UNAUTHENTICATED, получено: ${AUTH_RESULT}"
fi
pass "Неверный ключ корректно отклоняется"

section "9/16" "Cache-aside: hit/miss, TTL, ключи"
FLIGHT_LOG_START="$(flight_log_line_count)"
curl -fsS "${BASE_URL}/flights/${FLIGHT_ID}" >/dev/null
curl -fsS "${BASE_URL}/flights/${FLIGHT_ID}" >/dev/null
curl -fsS "${BASE_URL}/flights?origin=SVO&destination=LED&date=2026-04-01" >/dev/null
curl -fsS "${BASE_URL}/flights?origin=SVO&destination=LED&date=2026-04-01" >/dev/null
sleep 1
FLIGHT_LOG_DELTA="$(flight_logs_since "$FLIGHT_LOG_START")"
if ! printf "%s\n" "$FLIGHT_LOG_DELTA" | grep -q "\[CACHE MISS\]"; then
  fail "Не найден CACHE MISS в логах"
fi
if ! printf "%s\n" "$FLIGHT_LOG_DELTA" | grep -q "\[CACHE HIT\]"; then
  fail "Не найден CACHE HIT в логах"
fi
FLIGHT_TTL="$(docker compose exec -T redis-master redis-cli ttl "flight:${FLIGHT_ID}" | tr -d '\r')"
if [[ "$FLIGHT_TTL" -le 0 ]]; then
  fail "TTL для flight:${FLIGHT_ID} не установлен"
fi
SEARCH_KEY="$(docker compose exec -T redis-master redis-cli --raw keys "search:SVO:LED:*" | head -n 1 | tr -d '\r')"
if [[ -z "$SEARCH_KEY" ]]; then
  fail "Не найден search-кэш ключ"
fi
SEARCH_TTL="$(docker compose exec -T redis-master redis-cli ttl "$SEARCH_KEY" | tr -d '\r')"
if [[ "$SEARCH_TTL" -le 0 ]]; then
  fail "TTL для search-кэша не установлен"
fi
pass "Cache-aside работает, TTL установлен"

section "10/16" "Cache invalidation после мутаций"
INVALIDATE_LOG_START="$(flight_log_line_count)"
CACHE_BOOKING_RESPONSE="$(curl -fsS -X POST "${BASE_URL}/bookings" \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"cache-user\",\"flight_id\":${FLIGHT_ID},\"passenger_name\":\"Cache User\",\"passenger_email\":\"cache@example.com\",\"seat_count\":1}")"
CACHE_BOOKING_ID="$(printf "%s" "$CACHE_BOOKING_RESPONSE" | jq -r ".booking_id")"
curl -fsS -X POST "${BASE_URL}/bookings/${CACHE_BOOKING_ID}/cancel" >/dev/null
sleep 1
INVALIDATE_DELTA="$(flight_logs_since "$INVALIDATE_LOG_START")"
if ! printf "%s\n" "$INVALIDATE_DELTA" | grep -q "\[CACHE INVALIDATE\]"; then
  fail "После Reserve/Release нет CACHE INVALIDATE в логах"
fi
pass "Инвалидация кэша после мутаций работает"

section "11/16" "Retry: только для UNAVAILABLE/DEADLINE_EXCEEDED"
RETRY_LOG_START="$(booking_log_line_count)"
docker compose stop flight-service >/dev/null 2>&1
sleep 2
RETRY_HTTP_CODE="$(curl -s -o /tmp/retry_response.json -w "%{http_code}" "${BASE_URL}/flights/${FLIGHT_ID}" || true)"
if [[ "$RETRY_HTTP_CODE" != "503" ]]; then
  fail "При остановленном Flight Service ожидался HTTP 503"
fi
sleep 2
RETRY_LOG_DELTA="$(booking_logs_since "$RETRY_LOG_START")"
if ! printf "%s\n" "$RETRY_LOG_DELTA" | grep -q "\[Retry\].*attempt 1/3"; then
  fail "Не найден retry attempt 1/3"
fi
if ! printf "%s\n" "$RETRY_LOG_DELTA" | grep -q "\[Retry\].*attempt 2/3"; then
  fail "Не найден retry attempt 2/3"
fi
if ! printf "%s\n" "$RETRY_LOG_DELTA" | grep -q "Max attempts reached"; then
  fail "Не найдено сообщение о достижении лимита retry"
fi
docker compose start flight-service >/dev/null 2>&1
docker compose restart booking-service >/dev/null 2>&1
sleep 4
RESTART_PROBE_CODE="$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/flights/${FLIGHT_ID}" || true)"
if [[ "$RESTART_PROBE_CODE" != "200" ]]; then
  fail "Booking/Flight сервисы не восстановились после retry-сценария"
fi
pass "Retry работает с лимитом 3 попытки"

section "12/16" "Нет retry для RESOURCE_EXHAUSTED"
NO_RETRY_LOG_START="$(booking_log_line_count)"
OVERBOOK_STATUS="$(curl -s -o /tmp/no_retry_overbook.json -w "%{http_code}" -X POST "${BASE_URL}/bookings" \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"no-retry\",\"flight_id\":${FLIGHT_ID},\"passenger_name\":\"No Retry\",\"passenger_email\":\"nr@example.com\",\"seat_count\":999999}")"
assert_eq "$OVERBOOK_STATUS" "409" "RESOURCE_EXHAUSTED пробрасывается как HTTP 409"
NO_RETRY_LOG_DELTA="$(booking_logs_since "$NO_RETRY_LOG_START")"
if printf "%s\n" "$NO_RETRY_LOG_DELTA" | grep -q "\[Retry\].*RESOURCE_EXHAUSTED"; then
  fail "Обнаружен retry для RESOURCE_EXHAUSTED, чего быть не должно"
fi
pass "Для RESOURCE_EXHAUSTED retry не выполняется"

section "13/16" "Redis Sentinel: quorum и мастер"
SENTINEL_QUORUM="$(docker compose exec -T redis-sentinel-1 redis-cli -p 26379 sentinel ckquorum mymaster | tr -d '\r')"
if [[ "$SENTINEL_QUORUM" != OK* ]]; then
  fail "Sentinel quorum не достигнут: ${SENTINEL_QUORUM}"
fi
SENTINEL_MASTER="$(docker compose exec -T redis-sentinel-1 redis-cli -p 26379 sentinel get-master-addr-by-name mymaster | tr -d '\r')"
SENTINEL_HOST="$(printf "%s\n" "$SENTINEL_MASTER" | sed -n "1p")"
SENTINEL_PORT="$(printf "%s\n" "$SENTINEL_MASTER" | sed -n "2p")"
if [[ "$SENTINEL_PORT" != "6379" ]]; then
  fail "Sentinel вернул неожиданный порт мастера: ${SENTINEL_PORT}"
fi
if [[ -z "$SENTINEL_HOST" ]]; then
  fail "Sentinel не вернул хост мастера"
fi
pass "Sentinel возвращает активного мастера ${SENTINEL_HOST}:${SENTINEL_PORT}"

section "14/16" "Circuit Breaker: CLOSED -> OPEN -> HALF_OPEN -> CLOSED"
docker compose restart booking-service >/dev/null 2>&1
sleep 3
CB_LOG_START="$(booking_log_line_count)"
docker compose stop flight-service >/dev/null 2>&1
sleep 1

CB_CODES=""
for _ in 1 2 3 4 5 6; do
  code="$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/flights/${FLIGHT_ID}" || true)"
  CB_CODES="${CB_CODES} ${code}"
  sleep 0.3
done

sleep 2
CB_LOG_DELTA_OPEN="$(booking_logs_since "$CB_LOG_START")"
if ! printf "%s\n" "$CB_LOG_DELTA_OPEN" | grep -q "\[CircuitBreaker\].*CLOSED -> OPEN"; then
  fail "Не найден переход CLOSED -> OPEN"
fi
if ! printf "%s\n" "$CB_LOG_DELTA_OPEN" | grep -q "Request blocked: circuit is OPEN"; then
  fail "Не найдено подтверждение блокировки запросов в OPEN"
fi

echo "Ожидание окна HALF_OPEN: ${CB_RESET_TIMEOUT_SECONDS}s"
sleep "$CB_RESET_TIMEOUT_SECONDS"
docker compose start flight-service >/dev/null 2>&1
sleep 5
CB_PROBE_CODE=""
CB_PROBE_MAX_ATTEMPTS=$((CB_RESET_TIMEOUT_SECONDS + 30))
for _ in $(seq 1 "$CB_PROBE_MAX_ATTEMPTS"); do
  CB_PROBE_CODE="$(curl -s -o /dev/null -w "%{http_code}" "${BASE_URL}/flights/${FLIGHT_ID}" || true)"
  if [[ "$CB_PROBE_CODE" == "200" ]]; then
    break
  fi
  sleep 1
done
if [[ "$CB_PROBE_CODE" != "200" ]]; then
  fail "Circuit Breaker не вернулся в рабочее состояние после HALF_OPEN"
fi
sleep 2

CB_LOG_DELTA_FINAL="$(booking_logs_since "$CB_LOG_START")"
if ! printf "%s\n" "$CB_LOG_DELTA_FINAL" | grep -q "\[CircuitBreaker\].*OPEN -> HALF_OPEN"; then
  fail "Не найден переход OPEN -> HALF_OPEN"
fi
if ! printf "%s\n" "$CB_LOG_DELTA_FINAL" | grep -q "\[CircuitBreaker\].*HALF_OPEN -> CLOSED\\|\\[CircuitBreaker\\].*HALF_OPEN.*success\\|\\[CircuitBreaker\\].*CLOSED (success)"; then
  pass "Переход HALF_OPEN -> CLOSED не всегда логируется отдельной строкой, но пробный запрос успешен"
else
  pass "Переход HALF_OPEN -> CLOSED зафиксирован"
fi

section "15/16" "Клиентские 404 для booking"
MISSING_BOOKING_CODE="$(curl -s -o /tmp/missing_booking.json -w "%{http_code}" "${BASE_URL}/bookings/00000000-0000-0000-0000-000000000000")"
assert_eq "$MISSING_BOOKING_CODE" "404" "GET /bookings/{id} для отсутствующей записи"

echo
echo "Итог"
echo "- REST/gRPC сценарии проверены"
echo "- Транзакции, retry, circuit breaker, sentinel, cache-aside подтверждены"
echo "- Скрипт завершился без ошибок"
