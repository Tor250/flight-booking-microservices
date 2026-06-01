DO $$
BEGIN
    CREATE TYPE flight_status AS ENUM ('SCHEDULED', 'DEPARTED', 'CANCELLED', 'COMPLETED');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END$$;

DO $$
BEGIN
    CREATE TYPE reservation_status AS ENUM ('ACTIVE', 'RELEASED', 'EXPIRED');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END$$;

ALTER TABLE flights
    DROP CONSTRAINT IF EXISTS flights_status_check;

ALTER TABLE flights
    ALTER COLUMN status TYPE flight_status
    USING status::flight_status;

ALTER TABLE flights
    ALTER COLUMN status SET DEFAULT 'SCHEDULED';

ALTER TABLE seat_reservations
    DROP CONSTRAINT IF EXISTS seat_reservations_status_check;

ALTER TABLE seat_reservations
    ALTER COLUMN status TYPE reservation_status
    USING status::reservation_status;

ALTER TABLE seat_reservations
    ALTER COLUMN status SET DEFAULT 'ACTIVE';
