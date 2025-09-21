import os
import psycopg2
from contextlib import contextmanager

DATABASE_URL = os.getenv("DATABASE_URL")

@contextmanager
def get_conn():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
    finally:
        conn.close()

def find_best_product(name: str):
    """Return (product_id, product_name, default_unit) best matching given name."""
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id, name, default_unit FROM products")
            rows = cur.fetchall()
    # Fuzzy match in Python to keep SQL simple
    from fuzzywuzzy import process
    choices = {r[1]: (r[0], r[1], r[2]) for r in rows}
    best_name, score = process.extractOne(name, list(choices.keys()))
    return choices[best_name] if score >= 70 else None

def get_emission_factor(product_id: int, unit: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT co2_per_unit FROM emission_factors WHERE product_id=%s AND unit=%s",
                (product_id, unit)
            )
            row = cur.fetchone()
            return float(row[0]) if row else None

def insert_query(phone: str, raw_input: str, total: float, breakdown: dict):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO user_queries(phone, raw_input, total_kg_co2, breakdown) VALUES (%s,%s,%s,%s)",
                (phone, raw_input, total, breakdown)
            )
            conn.commit()