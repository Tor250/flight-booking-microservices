set -euo pipefail

pass() {
  printf "OK: %s\n" "$1"
}

fail() {
  printf "ERROR: %s\n" "$1" >&2
  exit 1
}

require_pattern() {
  local pattern="$1"
  local file="$2"
  local message="$3"
  if ! rg -n --pcre2 "$pattern" "$file" >/dev/null; then
    fail "$message ($file)"
  fi
  pass "$message"
}

printf "Проверка нерантаймных требований HW3\n"
printf "=====================================\n"

printf "\n[1/12] docker-compose структура\n"
require_pattern "^  flight-db:" docker-compose.yml "Есть отдельный Postgres для Flight Service"
require_pattern "^  booking-db:" docker-compose.yml "Есть отдельный Postgres для Booking Service"
require_pattern "^  flight-flyway:" docker-compose.yml "Есть миграции Flight через Flyway"
require_pattern "^  booking-flyway:" docker-compose.yml "Есть миграции Booking через Flyway"
require_pattern "^  flight-service:" docker-compose.yml "Есть Flight Service"
require_pattern "^  booking-service:" docker-compose.yml "Есть Booking Service"
require_pattern "^  redis-sentinel-1:" docker-compose.yml "Есть Sentinel-1"
require_pattern "^  redis-sentinel-2:" docker-compose.yml "Есть Sentinel-2"
require_pattern "^  redis-sentinel-3:" docker-compose.yml "Есть Sentinel-3"

printf "\n[2/12] gRPC методы в .proto\n"
require_pattern "rpc\\s+SearchFlights\\(" proto/flight/v1/flight.proto "Есть SearchFlights"
require_pattern "rpc\\s+GetFlight\\(" proto/flight/v1/flight.proto "Есть GetFlight"
require_pattern "rpc\\s+ReserveSeats\\(" proto/flight/v1/flight.proto "Есть ReserveSeats"
require_pattern "rpc\\s+ReleaseReservation\\(" proto/flight/v1/flight.proto "Есть ReleaseReservation"

printf "\n[3/12] Timestamp и enum в контракте\n"
require_pattern "google\\.protobuf\\.Timestamp" proto/flight/v1/flight.proto "Используется Timestamp"
require_pattern "enum\\s+FlightStatus" proto/flight/v1/flight.proto "Есть enum FlightStatus"
require_pattern "enum\\s+ReservationStatus" proto/flight/v1/flight.proto "Есть enum ReservationStatus"

printf "\n[4/12] Кодогенерация protoc\n"
require_pattern "grpc_tools\\.protoc" booking-service/Dockerfile "Booking Dockerfile запускает protoc"
require_pattern "grpc_tools\\.protoc" flight-service/Dockerfile "Flight Dockerfile запускает protoc"

printf "\n[5/12] gRPC бизнес-коды ошибок\n"
require_pattern "StatusCode\\.NOT_FOUND" flight-service/app/service.py "Есть NOT_FOUND"
require_pattern "StatusCode\\.RESOURCE_EXHAUSTED" flight-service/app/service.py "Есть RESOURCE_EXHAUSTED"
require_pattern "StatusCode\\.ALREADY_EXISTS" flight-service/app/service.py "Есть ALREADY_EXISTS"
require_pattern "StatusCode\\.UNAUTHENTICATED" flight-service/app/auth.py "Есть UNAUTHENTICATED"

printf "\n[6/12] ER и 3NF в README\n"
require_pattern "erDiagram" README.md "ER-диаграмма описана"
require_pattern "Обоснование 3NF" README.md "Есть обоснование 3NF"
require_pattern "flight_number, DATE\\(departure_time\\)" README.md "Описана уникальность рейса по дню"

printf "\n[7/12] Ограничения целостности в миграциях\n"
require_pattern "CHECK \\(total_seats > 0\\)" flight-service/db/migrations/V1__create_flights.sql "Есть CHECK total_seats > 0"
require_pattern "CHECK \\(available_seats >= 0\\)" flight-service/db/migrations/V1__create_flights.sql "Есть CHECK available_seats >= 0"
require_pattern "CHECK \\(available_seats <= total_seats\\)" flight-service/db/migrations/V1__create_flights.sql "Есть CHECK available_seats <= total_seats"
require_pattern "CHECK \\(price > 0\\)" flight-service/db/migrations/V1__create_flights.sql "Есть CHECK price > 0"
require_pattern "CHECK \\(arrival_time > departure_time\\)" flight-service/db/migrations/V1__create_flights.sql "Есть CHECK arrival > departure"
require_pattern "UNIQUE INDEX ux_flights_number_departure_date" flight-service/db/migrations/V1__create_flights.sql "Есть UNIQUE индекс по номеру и дню"
require_pattern "booking_id UUID NOT NULL UNIQUE" flight-service/db/migrations/V2__create_seat_reservations.sql "Одна резервация на один booking_id"
require_pattern "CHECK \\(seat_count > 0\\)" flight-service/db/migrations/V2__create_seat_reservations.sql "Есть CHECK seat_count > 0 в seat_reservations"
require_pattern "CHECK \\(seat_count > 0\\)" booking-service/db/migrations/V1__create_bookings.sql "Есть CHECK seat_count > 0 в bookings"
require_pattern "CHECK \\(total_price > 0\\)" booking-service/db/migrations/V1__create_bookings.sql "Есть CHECK total_price > 0"
require_pattern "CREATE TYPE flight_status AS ENUM" flight-service/db/migrations/V4__use_enum_status_types.sql "Статусы flight переведены в ENUM"
require_pattern "CREATE TYPE reservation_status AS ENUM" flight-service/db/migrations/V4__use_enum_status_types.sql "Статусы reservation переведены в ENUM"
require_pattern "CREATE TYPE booking_status AS ENUM" booking-service/db/migrations/V2__use_enum_status_type.sql "Статусы booking переведены в ENUM"

printf "\n[8/12] Транзакции и блокировки\n"
require_pattern "FOR UPDATE" flight-service/app/repository.py "Используется SELECT FOR UPDATE"
require_pattern "UPDATE flights SET available_seats" flight-service/app/repository.py "В reserve изменяется доступный остаток мест"
require_pattern "INSERT INTO seat_reservations" flight-service/app/repository.py "В reserve создаётся резервация"
require_pattern "SET status = 'RELEASED'" flight-service/app/repository.py "В release меняется статус резервации"

printf "\n[9/12] gRPC auth и metadata\n"
require_pattern "FLIGHT_SERVICE_API_KEY" docker-compose.yml "API ключ задается через env"
require_pattern "\\(\"authorization\", API_KEY\\)" booking-service/app/grpc_client.py "Booking формирует authorization metadata"
require_pattern "metadata=_get_auth_metadata\\(\\)" booking-service/app/grpc_client.py "Booking передает metadata во все gRPC вызовы"
AUTH_DECORATOR_COUNT="$(rg -c "@require_auth" flight-service/app/service.py)"
if [[ "$AUTH_DECORATOR_COUNT" -lt 4 ]]; then
  fail "Не все методы FlightService защищены require_auth"
fi
pass "Все 4 gRPC метода защищены require_auth"

printf "\n[10/12] Cache-Aside и TTL\n"
require_pattern "cache_get\\(" flight-service/app/service.py "Есть чтение из кэша до БД"
require_pattern "cache_set\\(" flight-service/app/service.py "Есть запись в кэш после БД"
require_pattern "setex\\(" flight-service/app/cache.py "TTL выставляется через setex"
require_pattern "search:\\{request\\.origin\\}:\\{request\\.destination\\}:\\{date_str\\}" flight-service/app/service.py "Используется шаблон search-ключа"
require_pattern "cache_invalidate\\(" flight-service/app/service.py "Есть инвалидация кэша после мутаций"

printf "\n[11/12] Retry и Circuit Breaker\n"
require_pattern "max_retries = int\\(os.getenv\\(\"RETRY_MAX_ATTEMPTS\", \"3\"\\)\\)" booking-service/app/interceptors.py "Лимит retry = 3 (env)"
require_pattern "grpc\\.StatusCode\\.UNAVAILABLE" booking-service/app/interceptors.py "Retry включает UNAVAILABLE"
require_pattern "grpc\\.StatusCode\\.DEADLINE_EXCEEDED" booking-service/app/interceptors.py "Retry включает DEADLINE_EXCEEDED"
require_pattern "grpc\\.StatusCode\\.RESOURCE_EXHAUSTED" booking-service/app/interceptors.py "No-retry включает RESOURCE_EXHAUSTED"
require_pattern "CircuitState\\.CLOSED" booking-service/app/interceptors.py "Есть состояние CLOSED"
require_pattern "CircuitState\\.OPEN" booking-service/app/interceptors.py "Есть состояние OPEN"
require_pattern "CircuitState\\.HALF_OPEN" booking-service/app/interceptors.py "Есть состояние HALF_OPEN"
require_pattern "CB_FAILURE_THRESHOLD" docker-compose.yml "Конфигурируется порог CB"
require_pattern "CB_RESET_TIMEOUT" docker-compose.yml "Конфигурируется timeout CB"
require_pattern "CB_WINDOW_SECONDS" docker-compose.yml "Конфигурируется окно CB"

printf "\n[12/12] Sentinel-клиент в коде\n"
require_pattern "from redis\\.sentinel import Sentinel" flight-service/app/cache.py "Используется Sentinel-клиент"
require_pattern "sentinel = Sentinel\\(" flight-service/app/cache.py "Создается Sentinel-клиент"
require_pattern "master_for\\(" flight-service/app/cache.py "Используется master_for"
require_pattern "slave_for\\(" flight-service/app/cache.py "Используется slave_for"

printf "\nИтог: нерантаймные требования проверены успешно.\n"
