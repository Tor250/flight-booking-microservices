DO $$
BEGIN
    CREATE TYPE booking_status AS ENUM ('CONFIRMED', 'CANCELLED');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END$$;

ALTER TABLE bookings
    DROP CONSTRAINT IF EXISTS bookings_status_check;

ALTER TABLE bookings
    ALTER COLUMN status TYPE booking_status
    USING status::booking_status;

ALTER TABLE bookings
    ALTER COLUMN status SET DEFAULT 'CONFIRMED';
