import time
from typing import Iterable

from app.db.db import get_connection


_DDL: Iterable[str] = (
    """
    DO $$
    BEGIN
      ALTER TYPE games ADD VALUE IF NOT EXISTS 'minesweeper';
    EXCEPTION
      WHEN undefined_object THEN NULL;
    END $$;
    """,
    """
    ALTER TABLE system_config
    ADD COLUMN IF NOT EXISTS casino_balance BIGINT NOT NULL DEFAULT 0 CHECK (casino_balance >= 0)
    """,
    """
    ALTER TABLE system_config
    ADD COLUMN IF NOT EXISTS bots_enabled BOOLEAN NOT NULL DEFAULT TRUE
    """,
    """
    ALTER TABLE system_config
    ADD COLUMN IF NOT EXISTS min_join_cost BIGINT NOT NULL DEFAULT 1 CHECK (min_join_cost >= 0)
    """,
    """
    ALTER TABLE system_config
    ADD COLUMN IF NOT EXISTS max_join_cost BIGINT NOT NULL DEFAULT 1000000000 CHECK (max_join_cost >= 0)
    """,
    """
    ALTER TABLE room_pattern
    ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP
    """,
    """
    ALTER TABLE room_pattern
    DROP COLUMN IF EXISTS min_bots_count
    """,
    """
    ALTER TABLE room_pattern
    DROP COLUMN IF EXISTS max_bots_count
    """,
    """
    UPDATE room_pattern
    SET weight = 1
    WHERE weight IS NULL OR weight <= 0
    """,
    """
    DO $$
    BEGIN
      IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'room_pattern_weight_positive'
      ) THEN
        ALTER TABLE room_pattern
        ADD CONSTRAINT room_pattern_weight_positive CHECK (weight > 0);
      END IF;
    END $$;
    """,
    """
    ALTER TABLE room_pattern
    ADD COLUMN IF NOT EXISTS boost_cost_per_point BIGINT NOT NULL DEFAULT 10 CHECK (boost_cost_per_point >= 0)
    """,
    """
    ALTER TABLE room_pattern
    ADD COLUMN IF NOT EXISTS winner_payout_percent INTEGER NOT NULL DEFAULT 100 CHECK (winner_payout_percent BETWEEN 0 AND 100)
    """,
    """
    ALTER TABLE room_pattern
    ALTER COLUMN winner_payout_percent SET DEFAULT 100
    """,
    """
    UPDATE room_pattern
    SET winner_payout_percent = 100
    WHERE winner_payout_percent = 80
    """,
    """
    CREATE TABLE IF NOT EXISTS room_escrow (
        room_id INTEGER PRIMARY KEY REFERENCES rooms(id) ON DELETE CASCADE,
        amount BIGINT NOT NULL DEFAULT 0 CHECK (amount >= 0),
        stake_amount BIGINT NOT NULL DEFAULT 0 CHECK (stake_amount >= 0),
        boost_amount BIGINT NOT NULL DEFAULT 0 CHECK (boost_amount >= 0),
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """,
    """
    ALTER TABLE room_escrow
    ADD COLUMN IF NOT EXISTS stake_amount BIGINT NOT NULL DEFAULT 0 CHECK (stake_amount >= 0)
    """,
    """
    ALTER TABLE room_escrow
    ADD COLUMN IF NOT EXISTS boost_amount BIGINT NOT NULL DEFAULT 0 CHECK (boost_amount >= 0)
    """,
    """
    UPDATE room_escrow
    SET stake_amount = amount
    WHERE stake_amount = 0 AND boost_amount = 0 AND amount > 0
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
    INSERT INTO system_config (id, max_active_rooms, casino_balance, bots_enabled, min_join_cost, max_join_cost)
    VALUES (1, 50, 0, TRUE, 1, 1000000000)
    ON CONFLICT (id) DO NOTHING
    """,
    """
    DO $$
    BEGIN
      IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'casino_balance'
      ) THEN
        UPDATE system_config
        SET casino_balance = GREATEST(
          casino_balance,
          COALESCE((SELECT balance FROM casino_balance WHERE id = 1), 0)
        )
        WHERE id = 1;
      END IF;
    END $$;
    """,
    """
    INSERT INTO room_pattern (
        game,
        join_cost,
        max_members_count,
        rank,
        waiting_lobby_stage,
        waiting_shop_stage,
        max_rooms_count,
        is_active,
        weight,
        boost_cost_per_point,
        winner_payout_percent
    )
    SELECT
        'minesweeper',
        50,
        6,
        20.0,
        30,
        15,
        50,
        TRUE,
        1,
        10,
        100
    WHERE EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'room_pattern'
    )
      AND NOT EXISTS (
        SELECT 1
        FROM room_pattern
        WHERE game = 'minesweeper' AND is_active = TRUE
      )
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
