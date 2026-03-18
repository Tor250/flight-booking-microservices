import os
import grpc
import flight.v1.flight_pb2 as pb2
import flight.v1.flight_pb2_grpc as pb2_grpc
from app.interceptors import RetryCircuitBreakerInterceptor

API_KEY = os.getenv("FLIGHT_SERVICE_API_KEY", "super-secret-key-123")

def _get_auth_metadata():
    return [("authorization", API_KEY)]

interceptor = RetryCircuitBreakerInterceptor()
channel = grpc.insecure_channel(
    "flight-service:50051",
    options=[
        ("grpc.enable_retries", 0),
    ]
)
channel = grpc.intercept_channel(channel, interceptor)
client = pb2_grpc.FlightServiceStub(channel)


def get_flight(flight_id: int):
    try:
        return client.GetFlight(
            pb2.GetFlightRequest(flight_id=flight_id),
            metadata=_get_auth_metadata()
        )
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.NOT_FOUND:
            return None
        if e.code() == grpc.StatusCode.UNAUTHENTICATED:
            print(f"[gRPC Auth Error] Check API key: {e.details()}")
        raise


def reserve_seats(flight_id: int, seat_count: int, booking_id: str):
    try:
        return client.ReserveSeats(
            pb2.ReserveSeatsRequest(
                flight_id=flight_id,
                seat_count=seat_count,
                booking_id=booking_id
            ),
            metadata=_get_auth_metadata()
        )
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.RESOURCE_EXHAUSTED:
            return None
        if e.code() == grpc.StatusCode.UNAUTHENTICATED:
            print(f"[gRPC Auth Error] Check API key: {e.details()}")
        raise


def release_reservation(booking_id: str):
    try:
        return client.ReleaseReservation(
            pb2.ReleaseReservationRequest(booking_id=booking_id),
            metadata=_get_auth_metadata()
        )
    except grpc.RpcError as e:
        if e.code() == grpc.StatusCode.UNAUTHENTICATED:
            print(f"[gRPC Auth Error] Check API key: {e.details()}")
        print(f"Warning: ReleaseReservation failed: {e}")
        return None