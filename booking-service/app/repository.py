import logging
from app.database import get_connection

logger = logging.getLogger(__name__)


class BookingRepository:

    @staticmethod
    def create_booking(booking_id, user_id, flight_id, passenger_name, passenger_email, seat_count, total_price):
        conn = get_connection()
        try:
            with conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO bookings (id, user_id, flight_id, passenger_name, passenger_email,
                                            seat_count, total_price, status)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    """, (booking_id, user_id, flight_id, passenger_name, passenger_email,
                        seat_count, total_price, 'CONFIRMED'))
            return booking_id
        except Exception:
            conn.rollback()
            logger.exception("Error creating booking")
            raise

    @staticmethod
    def get_booking_by_id(booking_id: str):
        conn = get_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT id, user_id, flight_id, passenger_name, passenger_email,
                        seat_count, total_price, status, created_at
                    FROM bookings
                    WHERE id = %s
                """, (booking_id,))
                row = cur.fetchone()
                if not row:
                    return None

                created_at = None
                if row[8]:
                    created_at = row[8].isoformat()

                return {
                    "id": str(row[0]),
                    "user_id": row[1],
                    "flight_id": row[2],
                    "passenger_name": row[3],
                    "passenger_email": row[4],
                    "seat_count": row[5],
                    "total_price": float(row[6]),
                    "status": row[7],
                    "created_at": created_at,
                }

    @staticmethod
    def list_bookings_by_user(user_id: str):
        conn = get_connection()
        with conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id, user_id, flight_id, passenger_name, passenger_email,
                           seat_count, total_price, status, created_at
                    FROM bookings
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    """,
                    (user_id,),
                )
                rows = cur.fetchall()
                result = []
                for row in rows:
                    created_at = None
                    if row[8]:
                        created_at = row[8].isoformat()

                    result.append(
                        {
                            "id": str(row[0]),
                            "user_id": row[1],
                            "flight_id": row[2],
                            "passenger_name": row[3],
                            "passenger_email": row[4],
                            "seat_count": row[5],
                            "total_price": float(row[6]),
                            "status": row[7],
                            "created_at": created_at,
                        }
                    )
                return result
