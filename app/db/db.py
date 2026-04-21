import psycopg2
from psycopg2.extras import RealDictCursor
from app.db.db_config import DB_CONFIG


def get_connection():
    return psycopg2.connect(
        host=DB_CONFIG["host"],
        database=DB_CONFIG["database"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        port=DB_CONFIG["port"]
    )


# -------------------------
# READ (SELECT)
# -------------------------
def fetch(query, params=None):
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, params)

            # если одна строка
            if query.strip().lower().startswith("select"):
                result = cursor.fetchall()

                if len(result) == 1:
                    return result[0]
                return result

            return None

    finally:
        if conn:
            conn.close()


# -------------------------
# WRITE (INSERT / UPDATE / DELETE)
# -------------------------
def execute(query, params=None):
    conn = None
    try:
        conn = get_connection()
        with conn.cursor() as cursor:
            cursor.execute(query, params)
            conn.commit()

            return cursor.rowcount

    except Exception as e:
        if conn:
            conn.rollback()
        raise e

    finally:
        if conn:
            conn.close()