from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import uuid
import grpc

import flight.v1.flight_pb2 as pb2

from app.grpc_client import get_flight, reserve_seats, release_reservation
from app.repository import BookingRepository
from app.database import get_connection

router = APIRouter()


class BookingCreateRequest(BaseModel):
    user_id: str
    flight_id: int
    passenger_name: str
    passenger_email: str
    seat_count: int


@router.get("/flights/{flight_id}")
def get_flight_api(flight_id: int):
    try:
        flight = get_flight(flight_id)
        if flight is None:
            raise HTTPException(404, "Flight not found")
        
        status_name = pb2.FlightStatus.Name(flight.status)
        
        return {
            "id": flight.id,
            "airline": flight.airline,
            "origin": flight.origin,
            "destination": flight.destination,
            "departure_time": flight.departure_time.ToJsonString() if flight.HasField('departure_time') else None,
            "arrival_time": flight.arrival_time.ToJsonString() if flight.HasField('arrival_time') else None,
            "total_seats": flight.total_seats,
            "available_seats": flight.available_seats,
            "price": flight.price,
            "status": status_name
        }
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.NOT_FOUND:
            raise HTTPException(404, "Flight not found")
        raise HTTPException(500, f"Flight service error: {e.details()}")
    except Exception as e:
        print(f"[ERROR] get_flight_api: {type(e).__name__}: {e}")
        raise HTTPException(500, f"Internal server error: {str(e)}")


@router.post("/bookings")
def create_booking(request: BookingCreateRequest):
    booking_id = str(uuid.uuid4())

    flight = get_flight(request.flight_id)
    if flight is None:
        raise HTTPException(404, "Flight not found")

    reserve_response = reserve_seats(
        flight_id=request.flight_id,
        seat_count=request.seat_count,
        booking_id=booking_id
    )
    
    if reserve_response is None or not reserve_response.success:
        raise HTTPException(400, "Not enough seats")

    total_price = request.seat_count * flight.price
    
    BookingRepository.create_booking(
        booking_id=booking_id,
        user_id=request.user_id,
        flight_id=request.flight_id,
        passenger_name=request.passenger_name,
        passenger_email=request.passenger_email,
        seat_count=request.seat_count,
        total_price=total_price
    )

    return {"booking_id": booking_id, "status": "CONFIRMED"}


@router.get("/bookings/{booking_id}")
def get_booking(booking_id: str):
    booking = BookingRepository.get_booking_by_id(booking_id)
    if booking is None:
        raise HTTPException(404, "Booking not found")
    return booking


@router.post("/bookings/{booking_id}/cancel")
def cancel_booking(booking_id: str):
    booking = BookingRepository.get_booking_by_id(booking_id)
    if booking is None:
        raise HTTPException(404, "Booking not found")
    if booking["status"] != "CONFIRMED":
        raise HTTPException(400, f"Cannot cancel booking with status: {booking['status']}")

    try:
        release_reservation(booking_id)
    except grpc.RpcError as e:
        print(f"Warning: ReleaseReservation failed: {e}")

    conn = get_connection()
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE bookings SET status = 'CANCELLED' WHERE id = %s",
                (booking_id,)
            )

    return {"booking_id": booking_id, "status": "CANCELLED"}


@router.get("/bookings")
def list_bookings(user_id: str):
    conn = get_connection()
    bookings = []
    with conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id, user_id, flight_id, passenger_name, passenger_email,
                       seat_count, total_price, status, created_at
                FROM bookings
                WHERE user_id = %s
                ORDER BY created_at DESC
            """, (user_id,))
            rows = cur.fetchall()
            for row in rows:
                bookings.append({
                    "id": str(row[0]),
                    "user_id": row[1],
                    "flight_id": row[2],
                    "passenger_name": row[3],
                    "passenger_email": row[4],
                    "seat_count": row[5],
                    "total_price": float(row[6]),
                    "status": row[7],
                    "created_at": row[8].isoformat() if row[8] else None
                })
    return bookings