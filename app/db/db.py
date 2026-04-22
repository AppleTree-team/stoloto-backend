from typing import List, Dict, Any, Optional
import psycopg2
from psycopg2.extras import RealDictCursor
from app.db.db_config import DB_CONFIG


def get_connection():
    timezone = DB_CONFIG.get("timezone") or "Europe/Moscow"
    return psycopg2.connect(
        host=DB_CONFIG["host"],
        database=DB_CONFIG["database"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        port=DB_CONFIG["port"],
        options=f"-c timezone={timezone}"
    )


# -------------------------
# READ (SELECT)
# -------------------------
# def fetch(query, params=None):
#     conn = None
#     try:
#         conn = get_connection()
#         with conn.cursor(cursor_factory=RealDictCursor) as cursor:
#             cursor.execute(query, params)
#
#             if query.strip().lower().startswith("select"):
#                 return cursor.fetchall()
#
#             return None
#     finally:
#         if conn:
#             conn.close()

def fetch_one(query, params=None):
    """Выполняет SELECT запрос и возвращает одну строку (или None)"""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, params)
            result = cursor.fetchone()
            return result
    finally:
        if conn:
            conn.close()


def fetch_all(query, params=None):
    """Выполняет SELECT запрос и возвращает все строки (список)"""
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, params)
            result = cursor.fetchall()
            return result if result else []
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


def execute_with_returning(query: str, params=None) -> Dict[str, Any]:
    """
    Выполняет INSERT/UPDATE с RETURNING и возвращает результат
    """
    conn = None
    try:
        conn = get_connection()
        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute(query, params)
            conn.commit()  # ← ВАЖНО: коммитим!
            result = cursor.fetchone()
            return result
    except Exception as e:
        if conn:
            conn.rollback()
        raise e
    finally:
        if conn:
            conn.close()
