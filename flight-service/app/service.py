import flight.v1.flight_pb2 as pb2
import flight.v1.flight_pb2_grpc as pb2_grpc
from google.protobuf.timestamp_pb2 import Timestamp
import datetime
from app.repository import FlightRepository
from app.cache import cache_get, cache_set, cache_invalidate, flight_to_dict, dict_to_flight
import grpc
from app.auth import require_auth


def to_timestamp(dt: datetime.datetime):
    ts = Timestamp()
    ts.FromDatetime(dt)
    return ts


def to_datetime(ts: Timestamp) -> datetime.datetime:
    if ts is None:
        return None
    return ts.ToDatetime()


def _request_date_or_none(request) -> datetime.datetime:
    if request.HasField("date"):
        return to_datetime(request.date)
    return None


def _request_date_cache_suffix(request) -> str:
    if request.HasField("date"):
        return request.date.ToJsonString()
    return "any"


def _cached_flights_to_proto(cached_payload):
    flights = []
    for item in cached_payload:
        flights.append(dict_to_flight(item, pb2))
    return flights


def _proto_flights_to_cache_payload(flights):
    cached_items = []
    for item in flights:
        cached_items.append(flight_to_dict(item, pb2))
    return cached_items


class FlightService(pb2_grpc.FlightServiceServicer):

    @require_auth
    def SearchFlights(self, request, context):
        date_str = _request_date_cache_suffix(request)
        cache_key = f"search:{request.origin}:{request.destination}:{date_str}"
        cached = cache_get(cache_key)
        if cached and cached.get("flights"):
            flights = _cached_flights_to_proto(cached["flights"])
            return pb2.SearchFlightsResponse(flights=flights)

        flights = FlightRepository.search_flights(
            origin=request.origin,
            destination=request.destination,
            date=_request_date_or_none(request),
        )

        flights_pb = []
        for f in flights:
            flight_pb = pb2.Flight(
                id=f[0],
                airline=f[1],
                flight_number=f[2],
                origin=f[3],
                destination=f[4],
                departure_time=to_timestamp(f[5]),
                arrival_time=to_timestamp(f[6]),
                total_seats=f[7],
                available_seats=f[8],
                price=float(f[9]),
                status=getattr(pb2.FlightStatus, f[10], pb2.FlightStatus.SCHEDULED),
            )
            flights_pb.append(flight_pb)

        cache_payload = {
            "flights": _proto_flights_to_cache_payload(flights_pb),
        }
        cache_set(cache_key, cache_payload)

        return pb2.SearchFlightsResponse(flights=flights_pb)

    @require_auth
    def GetFlight(self, request, context):
        cache_key = f"flight:{request.flight_id}"

        cached = cache_get(cache_key)
        if cached:
            return dict_to_flight(cached, pb2)

        row = FlightRepository.get_flight(request.flight_id)
        if not row:
            context.abort(grpc.StatusCode.NOT_FOUND, "Flight not found")

        flight_pb = pb2.Flight(
            id=row[0],
            airline=row[1],
            flight_number=row[2],
            origin=row[3],
            destination=row[4],
            departure_time=to_timestamp(row[5]),
            arrival_time=to_timestamp(row[6]),
            total_seats=row[7],
            available_seats=row[8],
            price=float(row[9]),
            status=getattr(pb2.FlightStatus, row[10], pb2.FlightStatus.SCHEDULED),
        )

        cache_set(cache_key, flight_to_dict(flight_pb, pb2))

        return flight_pb

    @require_auth
    def ReserveSeats(self, request, context):
        try:
            success = FlightRepository.reserve_seats(
                flight_id=request.flight_id,
                booking_id=request.booking_id,
                seat_count=request.seat_count,
            )
        except LookupError:
            context.abort(grpc.StatusCode.NOT_FOUND, "Flight not found")
        except ValueError as exc:
            context.abort(grpc.StatusCode.ALREADY_EXISTS, str(exc))

        if not success:
            context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, "Not enough seats")

        cache_invalidate(f"flight:{request.flight_id}")
        cache_invalidate(f"search:*:*:*")

        return pb2.ReserveSeatsResponse(success=True, status=pb2.ReservationStatus.ACTIVE)

    @require_auth
    def ReleaseReservation(self, request, context):
        try:
            success = FlightRepository.release_reservation(request.booking_id)
        except LookupError:
            context.abort(grpc.StatusCode.NOT_FOUND, "Reservation flight not found")
        if not success:
            context.abort(grpc.StatusCode.NOT_FOUND, "Reservation not found")

        flight_id = FlightRepository.get_flight_id_by_booking(request.booking_id)
        if flight_id:
            cache_invalidate(f"flight:{flight_id}")
            cache_invalidate(f"search:*:*:*")

        return pb2.ReleaseReservationResponse(success=True)
