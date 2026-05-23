# Flight Booking: gRPC + Redis

Проект состоит из двух микросервисов:

- `booking-service` — REST API + PostgreSQL
- `flight-service` — gRPC API + PostgreSQL + Redis Sentinel

Межсервисное взаимодействие выполняется по gRPC.

## Архитектура

```text
Client (REST)
   |
   v
Booking Service  ---------------------->  Flight Service (gRPC)
  PostgreSQL                                  PostgreSQL
                                              Redis master/replicas
                                              Redis Sentinel x3
```

## Быстрый старт

```bash
docker compose up -d --build
docker compose ps
```

Порты:

- Booking REST API: `http://localhost:8000`
- Flight gRPC: `localhost:50051`
- Flight DB: `localhost:5433`
- Booking DB: `localhost:5434`
- Redis Sentinel: `localhost:26379`, `26380`, `26381`

## gRPC контракт

Файл контракта: `proto/flight/v1/flight.proto`

Сервис `FlightService`:

- `SearchFlights`
- `GetFlight`
- `ReserveSeats`
- `ReleaseReservation`

В контракте используются:

- `google.protobuf.Timestamp`
- `enum FlightStatus`
- `enum ReservationStatus`

Коды бизнес-ошибок:

- `NOT_FOUND` — рейс или резервация не найдены
- `RESOURCE_EXHAUSTED` — недостаточно мест
- `ALREADY_EXISTS` — повторный `booking_id` с другим payload
- `UNAUTHENTICATED` — неверный или отсутствующий API key

## REST API (Booking Service)

- `GET /flights?origin=SVO&destination=LED&date=2026-04-01`
- `GET /flights/{id}`
- `POST /bookings`
- `GET /bookings/{id}`
- `POST /bookings/{id}/cancel`
- `GET /bookings?user_id=X`

## Модель данных

```mermaid
erDiagram
    FLIGHT {
        int id PK "NOT NULL"
        string airline "NOT NULL"
        string flight_number "NOT NULL, UNIQUE WITH DATE(departure_time)"
        string origin "NOT NULL"
        string destination "NOT NULL"
        timestamp departure_time "NOT NULL"
        timestamp arrival_time "NOT NULL"
        int total_seats "NOT NULL, CHECK > 0"
        int available_seats "NOT NULL, CHECK >= 0 and <= total_seats"
        numeric price "NOT NULL, CHECK > 0"
        flight_status status "NOT NULL: SCHEDULED|DEPARTED|CANCELLED|COMPLETED"
    }

    SEAT_RESERVATION {
        uuid id PK "NOT NULL"
        int flight_id FK "NOT NULL"
        uuid booking_id FK_UNIQUE "NOT NULL, логическая FK в Booking Service"
        int seat_count "NOT NULL, CHECK > 0"
        reservation_status status "NOT NULL: ACTIVE|RELEASED|EXPIRED"
        timestamp reserved_at
    }

    BOOKING {
        uuid id PK "NOT NULL"
        string user_id "NOT NULL"
        int flight_id "NOT NULL, логическая ссылка на Flight Service"
        string passenger_name "NOT NULL"
        string passenger_email "NOT NULL"
        int seat_count "NOT NULL, CHECK > 0"
        numeric total_price "NOT NULL, CHECK > 0"
        booking_status status "NOT NULL: CONFIRMED|CANCELLED"
        timestamp created_at
    }

    FLIGHT ||--o{ SEAT_RESERVATION : allocates
    BOOKING ||--|| SEAT_RESERVATION : maps_by_booking_id
```

Ограничения в миграциях:

- `total_seats > 0`
- `available_seats >= 0`
- `available_seats <= total_seats`
- `price > 0`
- `arrival_time > departure_time`
- `seat_count > 0`
- `status` через PostgreSQL `ENUM` (flight/reservation/booking)
- уникальность `(flight_number, DATE(departure_time))`

Обоснование 3NF:

- Каждый неключевой атрибут зависит от ключа своей сущности, без частичных зависимостей.
- Транзитивные зависимости не хранятся в таблицах.
- `SeatReservation` вынесена отдельно и не дублирует атрибуты рейса/бронирования.
- `Booking.total_price` хранится как бизнес-снимок цены на момент подтверждения брони.

## Ключевые технические решения

- Миграции БД: `Flyway`
- Транзакции и блокировки: `SELECT ... FOR UPDATE`
- Auth между сервисами: API key в gRPC metadata
- Кеширование: Cache-Aside в Redis
- Отказоустойчивость Redis: Sentinel (1 master, 2 replicas, 3 sentinel)
- Retry: до 3 попыток, backoff `100/200/400ms`, только для `UNAVAILABLE/DEADLINE_EXCEEDED`
- Circuit Breaker: `CLOSED -> OPEN -> HALF_OPEN`

## Проверка проекта

Основной скрипт проверки:

```bash
bash test_requests.sh
bash check_static_requirements.sh
# или одной командой:
make verify-all
```

Скрипт проверяет:

- базовые REST/gRPC сценарии
- создание/отмену бронирования
- транзакционный rollback на ошибках
- idempotency `ReserveSeats` по `booking_id`
- auth (`UNAUTHENTICATED` при неверном ключе)
- cache hit/miss + TTL + invalidation
- retry + отсутствие retry для `RESOURCE_EXHAUSTED`
- Redis Sentinel quorum
- Circuit Breaker переходы состояний
