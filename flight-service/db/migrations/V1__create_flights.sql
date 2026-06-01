CREATE TABLE flights (
    id SERIAL PRIMARY KEY,
    airline TEXT NOT NULL,
    flight_number TEXT NOT NULL,
    origin TEXT NOT NULL,
    destination TEXT NOT NULL,
    departure_time TIMESTAMP NOT NULL,
    arrival_time TIMESTAMP NOT NULL,
    total_seats INT NOT NULL CHECK (total_seats > 0),
    available_seats INT NOT NULL CHECK (available_seats >= 0),
    price NUMERIC(10,2) NOT NULL CHECK (price > 0),
    status TEXT NOT NULL CHECK (status IN ('SCHEDULED', 'DEPARTED', 'CANCELLED', 'COMPLETED')),
    CHECK (available_seats <= total_seats),
    CHECK (arrival_time > departure_time)
);

CREATE UNIQUE INDEX ux_flights_number_departure_date
    ON flights (flight_number, (DATE(departure_time)));
