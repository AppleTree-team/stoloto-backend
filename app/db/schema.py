import time
from typing import Iterable

from app.db.db import get_connection


_DDL: Iterable[str] = (
    """
    ALTER TABLE room_pattern
    ADD COLUMN IF NOT EXISTS boost_cost_per_point BIGINT NOT NULL DEFAULT 10 CHECK (boost_cost_per_point >= 0)
    """,
    """
    ALTER TABLE room_pattern
    ADD COLUMN IF NOT EXISTS winner_payout_percent INTEGER NOT NULL DEFAULT 80 CHECK (winner_payout_percent BETWEEN 0 AND 100)
    """,
    """
    CREATE TABLE IF NOT EXISTS room_escrow (
        room_id INTEGER PRIMARY KEY REFERENCES rooms(id) ON DELETE CASCADE,
        amount BIGINT NOT NULL DEFAULT 0 CHECK (amount >= 0),
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS ledger_entries (
        id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        room_id INTEGER REFERENCES rooms(id) ON DELETE SET NULL,
        user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
        account VARCHAR(32) NOT NULL,
        entry_type VARCHAR(64) NOT NULL,
        amount BIGINT NOT NULL,
        meta JSONB NOT NULL DEFAULT '{}'::jsonb
    )
    """,
    """
    INSERT INTO casino_balance (id, balance)
    VALUES (1, 0)
    ON CONFLICT (id) DO NOTHING
    """,
)


def ensure_schema(retries: int = 10, delay_seconds: float = 0.5) -> None:
    last_error: Exception | None = None
    for _ in range(max(1, retries)):
        try:
            conn = get_connection()
            try:
                with conn.cursor() as cursor:
                    for stmt in _DDL:
                        cursor.execute(stmt)
                conn.commit()
            finally:
                conn.close()
            return
        except Exception as exc:  # pragma: no cover
            last_error = exc
            time.sleep(delay_seconds)
    if last_error:
        raise last_error

