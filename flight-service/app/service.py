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


class FlightService(pb2_grpc.FlightServiceServicer):
    
    @require_auth
    def SearchFlights(self, request, context):
        date_str = request.date.ToJsonString() if request.HasField('date') else 'any'
        cache_key = f"search:{request.origin}:{request.destination}:{date_str}"
        cached = cache_get(cache_key)
        if cached and cached.get('flights'):
            flights = [dict_to_flight(f, pb2) for f in cached['flights']]
            return pb2.SearchFlightsResponse(flights=flights)
        
        flights = FlightRepository.search_flights(
            origin=request.origin,
            destination=request.destination,
            date=request.date if request.HasField('date') else None
        )
        
        flights_pb = []
        for f in flights:
            flight_pb = pb2.Flight(
                id=f[0], airline=f[1], origin=f[2], destination=f[3],
                departure_time=to_timestamp(f[4]), arrival_time=to_timestamp(f[5]),
                total_seats=f[6], available_seats=f[7], price=float(f[8]),
                status=getattr(pb2.FlightStatus, f[9], pb2.FlightStatus.SCHEDULED)
            )
            flights_pb.append(flight_pb)
        
        cache_set(cache_key, {
            'flights': [flight_to_dict(f, pb2) for f in flights_pb]
        })
        
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
            id=row[0], airline=row[1], origin=row[2], destination=row[3],
            departure_time=to_timestamp(row[4]), arrival_time=to_timestamp(row[5]),
            total_seats=row[6], available_seats=row[7], price=float(row[8]),
            status=getattr(pb2.FlightStatus, row[9], pb2.FlightStatus.SCHEDULED)
        )
        
        cache_set(cache_key, flight_to_dict(flight_pb, pb2))
        
        return flight_pb
    
    @require_auth
    def ReserveSeats(self, request, context):
        success = FlightRepository.reserve_seats(
            flight_id=request.flight_id,
            booking_id=request.booking_id,
            seat_count=request.seat_count
        )
        if not success:
            context.abort(grpc.StatusCode.RESOURCE_EXHAUSTED, "Not enough seats")
        
        cache_invalidate(f"flight:{request.flight_id}")
        cache_invalidate(f"search:*:*:*")
        
        return pb2.ReserveSeatsResponse(success=True)
    
    @require_auth
    def ReleaseReservation(self, request, context):
        success = FlightRepository.release_reservation(request.booking_id)
        if not success:
            print(f"Warning: ReleaseReservation for {request.booking_id} not found")
        
        flight_id = FlightRepository.get_flight_id_by_booking(request.booking_id)
        if flight_id:
            cache_invalidate(f"flight:{flight_id}")
        
        return pb2.ReleaseReservationResponse(success=True)