import os
import grpc

API_KEY = os.getenv("FLIGHT_SERVICE_API_KEY", "secret-key-change-me")

def authenticate(context: grpc.ServicerContext) -> bool:
    metadata = dict(context.invocation_metadata())
    provided_key = metadata.get("authorization") or metadata.get("x-api-key")
    
    if not provided_key or provided_key != API_KEY:
        return False
    return True

def require_auth(func):
    def wrapper(self, request, context):
        if not authenticate(context):
            context.abort(grpc.StatusCode.UNAUTHENTICATED, "Invalid or missing API key")
        return func(self, request, context)
    return wrapper