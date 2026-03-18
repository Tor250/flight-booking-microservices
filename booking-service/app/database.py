import psycopg2

def get_connection():
    return psycopg2.connect(
        host="booking-db",
        database="bookings",
        user="postgres",
        password="postgres"
    )