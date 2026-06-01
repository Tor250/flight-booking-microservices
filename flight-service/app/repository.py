import uuid
import datetime
from app.database import get_connection


class FlightRepository:

    @staticmethod
    def get_flight(flight_id: int):
        conn = get_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, airline, flight_number, origin, destination, departure_time,
                           arrival_time, total_seats, available_seats, price, status
                    FROM flights
                    WHERE id = %s
                """, (flight_id,))
                row = cur.fetchone()
                return row

    @staticmethod
    def reserve_seats(flight_id: int, booking_id: str, seat_count: int):
        if seat_count <= 0:
            raise ValueError("seat_count must be positive")

        conn = get_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT flight_id, seat_count, status
                    FROM seat_reservations
                    WHERE booking_id = %s
                    FOR UPDATE
                    """,
                    (booking_id,),
                )
                existing = cur.fetchone()
                if existing:
                    existing_flight_id, existing_seat_count, existing_status = existing
                    if (
                        existing_status == "ACTIVE"
                        and existing_flight_id == flight_id
                        and existing_seat_count == seat_count
                    ):
                        return True
                    raise ValueError("booking_id already used with different reservation payload")

                cur.execute("""
                    SELECT available_seats
                    FROM flights
                    WHERE id = %s
                    FOR UPDATE
                """, (flight_id,))
                row = cur.fetchone()
                if not row:
                    raise LookupError("flight not found")
                if row[0] < seat_count:
                    return False

                new_available = row[0] - seat_count
                cur.execute("""
                    UPDATE flights SET available_seats = %s WHERE id = %s
                """, (new_available, flight_id))
                cur.execute("""
                    INSERT INTO seat_reservations (id, flight_id, booking_id, seat_count, status)
                    VALUES (%s, %s, %s, %s, %s)
                """, (str(uuid.uuid4()), flight_id, booking_id, seat_count, 'ACTIVE'))
                return True
            

    @staticmethod
    def release_reservation(booking_id: str) -> bool:
        conn = get_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT flight_id, seat_count, status
                    FROM seat_reservations
                    WHERE booking_id = %s
                    FOR UPDATE
                """, (booking_id,))
                row = cur.fetchone()
                if not row:
                    return False
                
                flight_id, seat_count, status = row

                if status != "ACTIVE":
                    return True

                cur.execute(
                    """
                    SELECT id
                    FROM flights
                    WHERE id = %s
                    FOR UPDATE
                    """,
                    (flight_id,),
                )
                flight = cur.fetchone()
                if not flight:
                    raise LookupError("flight not found for reservation")
                
                cur.execute("""
                    UPDATE flights 
                    SET available_seats = available_seats + %s 
                    WHERE id = %s
                """, (seat_count, flight_id))
                
                cur.execute("""
                    UPDATE seat_reservations 
                    SET status = 'RELEASED' 
                    WHERE booking_id = %s
                """, (booking_id,))
                
                return True
            
    @staticmethod
    def search_flights(origin: str, destination: str, date: datetime.datetime = None):
        conn = get_connection()
        with conn:
            with conn.cursor() as cur:
                query = """
                    SELECT id, airline, flight_number, origin, destination, departure_time,
                        arrival_time, total_seats, available_seats, price, status
                    FROM flights 
                    WHERE origin = %s AND destination = %s AND status = 'SCHEDULED'
                """
                params = [origin, destination]
                if date:
                    query += " AND DATE(departure_time) = DATE(%s)"
                    params.append(date)
                query += " ORDER BY departure_time"
                cur.execute(query, tuple(params))
                return cur.fetchall()

    @staticmethod
    def get_flight_id_by_booking(booking_id: str) -> int:
        conn = get_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT flight_id FROM seat_reservations WHERE booking_id = %s",
                    (booking_id,),
                )
                row = cur.fetchone()
                if row:
                    return row[0]
                return None
