import os
import grpc
import logging
from datetime import datetime
import flight.v1.flight_pb2 as pb2
import flight.v1.flight_pb2_grpc as pb2_grpc
from google.protobuf.timestamp_pb2 import Timestamp
from app.interceptors import RetryCircuitBreakerInterceptor

API_KEY = os.getenv("FLIGHT_SERVICE_API_KEY", "super-secret-key-123")
logger = logging.getLogger(__name__)

def _get_auth_metadata():
    return [("authorization", API_KEY)]

interceptor = RetryCircuitBreakerInterceptor()
channel = grpc.insecure_channel(
    "flight-service:50051",
    options=[
        ("grpc.enable_retries", 0),
    ]
)
client = pb2_grpc.FlightServiceStub(channel)


def _date_to_timestamp(date_str: str) -> Timestamp:
    ts = Timestamp()
    ts.FromDatetime(datetime.strptime(date_str, "%Y-%m-%d"))
    return ts


def get_flight(flight_id: int):
    try:
        return interceptor.execute(
            "/flight.v1.FlightService/GetFlight",
            lambda: client.GetFlight(
                pb2.GetFlightRequest(flight_id=flight_id),
                metadata=_get_auth_metadata(),
                timeout=3.0,
            ),
        )
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.NOT_FOUND:
            return None
        if e.code() == grpc.StatusCode.UNAUTHENTICATED:
            logger.error("[gRPC Auth Error] Check API key: %s", e.details())
        raise


def reserve_seats(flight_id: int, seat_count: int, booking_id: str):
    try:
        return interceptor.execute(
            "/flight.v1.FlightService/ReserveSeats",
            lambda: client.ReserveSeats(
                pb2.ReserveSeatsRequest(
                    flight_id=flight_id,
                    seat_count=seat_count,
                    booking_id=booking_id
                ),
                metadata=_get_auth_metadata(),
                timeout=3.0,
            ),
        )
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.RESOURCE_EXHAUSTED:
            return None
        if e.code() == grpc.StatusCode.UNAUTHENTICATED:
            logger.error("[gRPC Auth Error] Check API key: %s", e.details())
        raise


def release_reservation(booking_id: str):
    try:
        return interceptor.execute(
            "/flight.v1.FlightService/ReleaseReservation",
            lambda: client.ReleaseReservation(
                pb2.ReleaseReservationRequest(booking_id=booking_id),
                metadata=_get_auth_metadata(),
                timeout=3.0,
            ),
        )
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.UNAUTHENTICATED:
            logger.error("[gRPC Auth Error] Check API key: %s", e.details())
        raise


def search_flights(origin: str, destination: str, date: str | None = None):
    request = pb2.SearchFlightsRequest(origin=origin, destination=destination)
    if date:
        request.date.CopyFrom(_date_to_timestamp(date))

    return interceptor.execute(
        "/flight.v1.FlightService/SearchFlights",
        lambda: client.SearchFlights(
            request,
            metadata=_get_auth_metadata(),
            timeout=3.0,
        ),
    )
