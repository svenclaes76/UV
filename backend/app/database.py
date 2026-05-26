import psycopg2
import os

db = psycopg2.connect(
    host=os.getenv("DB_HOST", "localhost"),
    database=os.getenv("DB_NAME", "stocks"),
    user=os.getenv("DB_USER", "postgres"),
    password=os.getenv("DB_PASS", "password")
)
