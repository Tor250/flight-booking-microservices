from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
import uuid
import grpc

import flight.v1.flight_pb2 as pb2

from app.grpc_client import get_flight, reserve_seats, release_reservation, search_flights
from app.repository import BookingRepository
from app.database import get_connection

router = APIRouter()


class BookingCreateRequest(BaseModel):
    user_id: str
    flight_id: int
    passenger_name: str
    passenger_email: str
    seat_count: int = Field(gt=0)


def _flight_to_response(flight):
    departure_time = None
    if flight.HasField("departure_time"):
        departure_time = flight.departure_time.ToJsonString()

    arrival_time = None
    if flight.HasField("arrival_time"):
        arrival_time = flight.arrival_time.ToJsonString()

    return {
        "id": flight.id,
        "airline": flight.airline,
        "flight_number": flight.flight_number,
        "origin": flight.origin,
        "destination": flight.destination,
        "departure_time": departure_time,
        "arrival_time": arrival_time,
        "total_seats": flight.total_seats,
        "available_seats": flight.available_seats,
        "price": flight.price,
        "status": pb2.FlightStatus.Name(flight.status),
    }


def _map_grpc_error(exc: grpc.RpcError) -> HTTPException:
    code = exc.code()
    if code == grpc.StatusCode.NOT_FOUND:
        return HTTPException(404, exc.details() or "Not found")
    if code == grpc.StatusCode.RESOURCE_EXHAUSTED:
        return HTTPException(409, exc.details() or "Not enough seats")
    if code == grpc.StatusCode.ALREADY_EXISTS:
        return HTTPException(409, exc.details() or "Reservation already exists")
    if code == grpc.StatusCode.INVALID_ARGUMENT:
        return HTTPException(400, exc.details() or "Invalid argument")
    if code == grpc.StatusCode.UNAUTHENTICATED:
        return HTTPException(401, exc.details() or "Unauthenticated")
    if code in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED):
        return HTTPException(503, exc.details() or "Flight service unavailable")
    return HTTPException(500, f"Flight service error: {exc.details()}")


@router.get("/flights")
def search_flights_api(
    origin: str = Query(..., min_length=3, max_length=3),
    destination: str = Query(..., min_length=3, max_length=3),
    date: str | None = None,
):
    try:
        response = search_flights(
            origin=origin.upper(),
            destination=destination.upper(),
            date=date,
        )
    except grpc.RpcError as exc:
        raise _map_grpc_error(exc)

    flights = []
    for flight in response.flights:
        flights.append(_flight_to_response(flight))
    return flights


@router.get("/flights/{flight_id}")
def get_flight_api(flight_id: int):
    try:
        flight = get_flight(flight_id)
        if flight is None:
            raise HTTPException(404, "Flight not found")

        return _flight_to_response(flight)
    except grpc.RpcError as exc:
        if exc.code() == grpc.StatusCode.NOT_FOUND:
            raise HTTPException(404, "Flight not found")
        raise _map_grpc_error(exc)


@router.post("/bookings")
def create_booking(request: BookingCreateRequest):
    booking_id = str(uuid.uuid4())
    reservation_created = False

    try:
        flight = get_flight(request.flight_id)
        if flight is None:
            raise HTTPException(404, "Flight not found")

        reserve_response = reserve_seats(
            flight_id=request.flight_id,
            seat_count=request.seat_count,
            booking_id=booking_id,
        )

        if reserve_response is None or not reserve_response.success:
            raise HTTPException(409, "Not enough seats")
        reservation_created = True

        total_price = request.seat_count * flight.price

        BookingRepository.create_booking(
            booking_id=booking_id,
            user_id=request.user_id,
            flight_id=request.flight_id,
            passenger_name=request.passenger_name,
            passenger_email=request.passenger_email,
            seat_count=request.seat_count,
            total_price=total_price,
        )
        return {"booking_id": booking_id, "status": "CONFIRMED"}
    except HTTPException:
        raise
    except grpc.RpcError as exc:
        raise _map_grpc_error(exc)
    except Exception:
        if reservation_created:
            try:
                release_reservation(booking_id)
            except Exception:
                pass
        raise HTTPException(500, "Failed to create booking")


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
        raise _map_grpc_error(e)

    conn = get_connection()
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE bookings SET status = 'CANCELLED' WHERE id = %s",
                (booking_id,),
            )

    return {"booking_id": booking_id, "status": "CANCELLED"}


@router.get("/bookings")
def list_bookings(user_id: str):
    return BookingRepository.list_bookings_by_user(user_id)
