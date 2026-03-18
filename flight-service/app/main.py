import grpc
from concurrent import futures
import time
import logging

import flight.v1.flight_pb2_grpc as pb2_grpc
from app.service import FlightService


from grpc_reflection.v1alpha import reflection

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    
    pb2_grpc.add_FlightServiceServicer_to_server(FlightService(), server)
    

    SERVICE_NAMES = (
        "flight.v1.FlightService",
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(SERVICE_NAMES, server)
    

    server.add_insecure_port('[::]:50051')
    server.start()
    
    logger.info("Flight Service started on [::]:50051 with reflection enabled")
    

    try:
        while True:
            time.sleep(86400)
    except KeyboardInterrupt:
        logger.info("Shutting down Flight Service...")
        server.stop(0)


if __name__ == "__main__":
    serve()