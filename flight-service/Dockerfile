FROM python:3.11

WORKDIR /app

ENV PYTHONPATH=/app

COPY flight-service/requirements.txt .
RUN pip install -r requirements.txt

COPY proto /proto
COPY flight-service /app

RUN python -m grpc_tools.protoc -I/proto \
 --python_out=. --grpc_python_out=. /proto/flight/v1/flight.proto \
 && touch flight/__init__.py \
 && touch flight/v1/__init__.py

CMD ["python", "app/main.py"]