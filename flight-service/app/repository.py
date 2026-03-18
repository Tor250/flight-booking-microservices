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
                    SELECT id, airline, origin, destination, departure_time,
                           arrival_time, total_seats, available_seats, price, status
                    FROM flights
                    WHERE id = %s
                """, (flight_id,))
                row = cur.fetchone()
                return row

    @staticmethod
    def reserve_seats(flight_id: int, booking_id: str, seat_count: int):
        conn = get_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT available_seats
                    FROM flights
                    WHERE id = %s
                    FOR UPDATE
                """, (flight_id,))
                row = cur.fetchone()
                if not row or row[0] < seat_count:
                    return False
                new_available = row[0] - seat_count
                cur.execute("""
                    UPDATE flights SET available_seats = %s WHERE id = %s
                """, (new_available, flight_id))
                cur.execute("""
                    INSERT INTO seat_reservations (id, flight_id, booking_id, seat_count, status)
                    VALUES (%s, %s, %s, %s, %s)
                """, (str(uuid.uuid4()), flight_id, booking_id, seat_count, 'CONFIRMED'))
                return True
            

    @staticmethod
    def release_reservation(booking_id: str) -> bool:
        conn = get_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT sr.flight_id, sr.seat_count
                    FROM seat_reservations sr
                    JOIN flights f ON f.id = sr.flight_id
                    WHERE sr.booking_id = %s AND sr.status = 'ACTIVE'
                    FOR UPDATE OF f
                """, (booking_id,))
                row = cur.fetchone()
                if not row:
                    return False
                
                flight_id, seat_count = row
                
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
                    SELECT id, airline, origin, destination, departure_time,
                        arrival_time, total_seats, available_seats, price, status
                    FROM flights 
                    WHERE origin = %s AND destination = %s AND status = 'SCHEDULED'
                """
                params = [origin, destination]
                if date:
                    query += " AND DATE(departure_time) = %s"
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
                    (booking_id,)
                )
                row = cur.fetchone()
                return row[0] if row else None