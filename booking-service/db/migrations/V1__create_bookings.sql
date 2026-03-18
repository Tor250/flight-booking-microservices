CREATE TABLE bookings (
    id UUID PRIMARY KEY,
    user_id TEXT NOT NULL,
    flight_id INT NOT NULL,
    passenger_name TEXT NOT NULL,
    passenger_email TEXT NOT NULL,
    seat_count INT NOT NULL CHECK (seat_count > 0),
    total_price NUMERIC(10,2) NOT NULL CHECK (total_price > 0),
    status TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);