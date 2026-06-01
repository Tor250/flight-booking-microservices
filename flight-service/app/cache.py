import json
import os
import logging
from redis.sentinel import Sentinel
import redis

logger = logging.getLogger(__name__)

SENTINEL_HOSTS = [
    ("redis-sentinel-1", 26379),
    ("redis-sentinel-2", 26379),
    ("redis-sentinel-3", 26379),
]
SENTINEL_MASTER = os.getenv("REDIS_SENTINEL_MASTER", "mymaster")

DEFAULT_TTL = int(os.getenv("CACHE_TTL", "300"))

try:
    sentinel = Sentinel(SENTINEL_HOSTS, socket_timeout=0.5)
    redis_client = sentinel.master_for(SENTINEL_MASTER, socket_timeout=0.5, decode_responses=True)
    redis_slave = sentinel.slave_for(SENTINEL_MASTER, socket_timeout=0.5, decode_responses=True)
    redis_client.ping()
    redis_slave.ping()
    logger.info("[CACHE] Using Redis Sentinel")
except Exception as e:
    logger.warning(f"[CACHE] Sentinel failed, fallback to Redis master: {e}")
    redis_client = redis.Redis(host="redis-master", port=6379, decode_responses=True)
    redis_slave = redis_client


def cache_get(key: str):
    try:
        data = redis_slave.get(key)
        if data:
            logger.info(f"[CACHE HIT] {key}")
            return json.loads(data)
        logger.info(f"[CACHE MISS] {key}")
        return None
    except Exception as e:
        logger.warning(f"[CACHE ERROR] get {key}: {e}")
        return None


def cache_set(key: str, value: dict, ttl: int = None):
    if ttl is None:
        ttl = DEFAULT_TTL
    try:
        redis_client.setex(key, ttl, json.dumps(value, default=str))
        logger.debug(f"[CACHE SET] {key} TTL={ttl}s")
    except Exception as e:
        logger.warning(f"[CACHE ERROR] set {key}: {e}")


def cache_invalidate(pattern: str):
    try:
        count = 0
        for key in redis_client.scan_iter(match=pattern, count=100):
            redis_client.delete(key)
            count += 1
            logger.info(f"[CACHE INVALIDATE] {key}")
        if count > 0:
            logger.info(f"[CACHE INVALIDATE] Removed {count} keys matching '{pattern}'")
    except Exception as e:
        logger.warning(f"[CACHE ERROR] invalidate {pattern}: {e}")


def flight_to_dict(flight_pb, pb2_module) -> dict:
    status_name = pb2_module.FlightStatus.Name(flight_pb.status)

    departure_time = None
    if flight_pb.HasField("departure_time"):
        departure_time = flight_pb.departure_time.ToJsonString()

    arrival_time = None
    if flight_pb.HasField("arrival_time"):
        arrival_time = flight_pb.arrival_time.ToJsonString()

    return {
        "id": flight_pb.id,
        "airline": flight_pb.airline,
        "flight_number": flight_pb.flight_number,
        "origin": flight_pb.origin,
        "destination": flight_pb.destination,
        "departure_time": departure_time,
        "arrival_time": arrival_time,
        "total_seats": flight_pb.total_seats,
        "available_seats": flight_pb.available_seats,
        "price": flight_pb.price,
        "status": status_name,
    }


def dict_to_flight(data: dict, pb2_module) -> 'pb2.Flight':
    from google.protobuf.timestamp_pb2 import Timestamp

    status_enum = data["status"]
    if isinstance(data["status"], str):
        status_enum = pb2_module.FlightStatus.Value(data["status"])

    dep_time = Timestamp()
    if data.get("departure_time"):
        dep_time.FromJsonString(data["departure_time"])

    arr_time = Timestamp()
    if data.get("arrival_time"):
        arr_time.FromJsonString(data["arrival_time"])

    departure_field = Timestamp()
    if data.get("departure_time"):
        departure_field = dep_time

    arrival_field = Timestamp()
    if data.get("arrival_time"):
        arrival_field = arr_time

    return pb2_module.Flight(
        id=data["id"],
        airline=data["airline"],
        flight_number=data.get("flight_number", ""),
        origin=data["origin"],
        destination=data["destination"],
        departure_time=departure_field,
        arrival_time=arrival_field,
        total_seats=data["total_seats"],
        available_seats=data["available_seats"],
        price=data["price"],
        status=status_enum,
    )
