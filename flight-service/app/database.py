import psycopg2
import os

def get_connection():
    return psycopg2.connect(
        host="flight-db",
        database="flights",
        user="postgres",
        password="postgres"
    )