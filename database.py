# database.py
import os
from datetime import datetime
import pymysql
from dotenv import load_dotenv

load_dotenv()

def get_connection():
    """Establishes connection to the local MySQL server."""
    return pymysql.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", 3306)),
        user=os.getenv("DB_USER", "root"),
        password=os.getenv("DB_PASSWORD", ""),
        database=os.getenv("DB_NAME", "fashion_agent_db"),
        cursorclass=pymysql.cursors.Cursor,
        autocommit=True
    )

def init_db():
    """Ensures search_history table exists in MySQL."""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS search_history (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    timestamp VARCHAR(50),
                    query TEXT,
                    category VARCHAR(100),
                    color VARCHAR(100),
                    budget DECIMAL(10, 2),
                    best_product TEXT,
                    lowest_price DECIMAL(10, 2),
                    cheapest_store VARCHAR(100)
                ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
            """)
    finally:
        conn.close()

def save_search_result(query: str, specs, matched_groups: list):
    """Inserts a search record and its top deal into MySQL."""
    conn = get_connection()
    try:
        best_prod = "None"
        lowest_price = 0.0
        cheapest_store = "None"

        if matched_groups:
            top_group = min(matched_groups, key=lambda g: g.lowest_price)
            best_prod = top_group.product_name
            lowest_price = float(top_group.lowest_price)
            cheapest_store = top_group.cheapest_store

        category = specs.category if specs else ""
        color = specs.color if specs else ""
        budget = float(specs.max_budget) if specs and specs.max_budget else 0.0
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        sql = """
            INSERT INTO search_history 
            (timestamp, query, category, color, budget, best_product, lowest_price, cheapest_store)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        """
        with conn.cursor() as cursor:
            cursor.execute(sql, (
                timestamp,
                query,
                category,
                color,
                budget,
                best_prod,
                lowest_price,
                cheapest_store
            ))
    finally:
        conn.close()

def get_recent_searches(limit: int = 10):
    """Retrieves previous searches to display in the Streamlit UI."""
    conn = get_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT timestamp, query, best_product, lowest_price, cheapest_store 
                FROM search_history 
                ORDER BY id DESC 
                LIMIT %s
            """, (limit,))
            return cursor.fetchall()
    finally:
        conn.close()