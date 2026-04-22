from app.db.db import fetch_one, fetch_all


def get_user_profile(user_id: int):
    user = fetch_one(
        """
        SELECT id, username, balance, created_at, is_bot, is_admin
        FROM users
        WHERE id = %s
        """,
        (user_id,)
    )
    return user


def get_user_game_history(user_id: int, limit: int = 20):
    """Получить историю игр пользователя по одной записи на комнату."""
    history = fetch_all(
        """
        WITH member_rooms AS (
            SELECT
                rm.room_id,
                COUNT(*)::int AS slots_count,
                COALESCE(SUM(rm.boost), 0)::int AS total_boost,
                COALESCE(SUM(1 + COALESCE(rm.boost, 0)), 0)::int AS total_weight,
                MAX(rm.joined_at) AS last_joined_at
            FROM room_members rm
            WHERE rm.user_id = %s
            GROUP BY rm.room_id
        ),
        user_ledger AS (
            SELECT
                le.room_id,
                COALESCE(SUM(
                    CASE
                        WHEN le.user_id = %s AND le.account = 'user' AND le.amount < 0
                        THEN -le.amount
                        ELSE 0
                    END
                ), 0)::bigint AS spent_amount,
                COALESCE(SUM(
                    CASE
                        WHEN le.user_id = %s AND le.entry_type = 'payout'
                        THEN le.amount
                        ELSE 0
                    END
                ), 0)::bigint AS payout_amount
            FROM ledger_entries le
            WHERE le.room_id IN (SELECT room_id FROM member_rooms)
              AND le.user_id = %s
            GROUP BY le.room_id
        )
        SELECT
            r.id AS room_id,
            r.access_token AS room_access_token,
            r.status,
            r.created_at,
            r.started_at,
            r.ended_at,
            r.winner_id,
            rp.game,
            rp.join_cost,
            rp.rank,
            rp.max_members_count,
            mr.slots_count,
            mr.total_boost,
            mr.total_weight,
            COALESCE(ul.spent_amount, 0)::bigint AS spent_amount,
            COALESCE(ul.payout_amount, 0)::bigint AS payout_amount,
            (COALESCE(ul.payout_amount, 0) - COALESCE(ul.spent_amount, 0))::bigint AS net_amount,
            CASE
                WHEN r.status <> 'finished' THEN 'pending'
                WHEN r.winner_id = %s THEN 'win'
                ELSE 'lose'
            END AS result,
            (r.winner_id = %s) AS is_winner
        FROM member_rooms mr
        JOIN rooms r ON r.id = mr.room_id
        JOIN room_pattern rp ON rp.id = r.room_pattern_id
        LEFT JOIN user_ledger ul ON ul.room_id = mr.room_id
        ORDER BY COALESCE(r.ended_at, r.started_at, mr.last_joined_at, r.created_at) DESC, r.id DESC
        LIMIT %s
        """,
        (user_id, user_id, user_id, user_id, user_id, user_id, limit)
    )

    if not isinstance(history, list):
        history = [history] if history else []

    return history
