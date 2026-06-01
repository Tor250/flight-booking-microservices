CREATE TABLE seat_reservations (
    id UUID PRIMARY KEY,
    flight_id INT NOT NULL REFERENCES flights(id),
    booking_id UUID NOT NULL UNIQUE,
    seat_count INT NOT NULL CHECK (seat_count > 0),
    status TEXT NOT NULL CHECK (status IN ('ACTIVE', 'RELEASED', 'EXPIRED')),
    reserved_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
