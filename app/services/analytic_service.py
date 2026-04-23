from typing import List, Dict, Any, Optional, Literal

from app.db.db import fetch_one, fetch_all

def get_game_popularity_with_dynamics() -> List[Dict[str, Any]]:
    """
    Возвращает для каждой игры: название, процент от всех игроков за неделю,
    динамику к предыдущей неделе (%).
    """
    query = """
    WITH current AS (
        SELECT 
            rp.game,
            COUNT(DISTINCT rm.user_id) AS players_current
        FROM room_members rm
        JOIN rooms r ON rm.room_id = r.id
        JOIN room_pattern rp ON rp.id = r.room_pattern_id
        WHERE r.created_at > NOW() - INTERVAL '7 days'
          AND NOT EXISTS (SELECT 1 FROM users u WHERE u.id = rm.user_id AND u.is_bot = true)
        GROUP BY rp.game
    ),
    previous AS (
        SELECT 
            rp.game,
            COUNT(DISTINCT rm.user_id) AS players_prev
        FROM room_members rm
        JOIN rooms r ON rm.room_id = r.id
        JOIN room_pattern rp ON rp.id = r.room_pattern_id
        WHERE r.created_at BETWEEN NOW() - INTERVAL '14 days' AND NOW() - INTERVAL '7 days'
          AND NOT EXISTS (SELECT 1 FROM users u WHERE u.id = rm.user_id AND u.is_bot = true)
        GROUP BY rp.game
    ),
    all_games AS (
        SELECT DISTINCT game FROM room_pattern WHERE deleted_at IS NULL
    )
    SELECT 
        ag.game,
        ROUND(100.0 * COALESCE(c.players_current, 0) / NULLIF(SUM(COALESCE(c.players_current, 0)) OVER (), 0), 1) AS percent,
        CASE 
            WHEN COALESCE(p.players_prev, 0) = 0 THEN NULL
            ELSE ROUND(100.0 * (COALESCE(c.players_current, 0) - COALESCE(p.players_prev, 0)) / COALESCE(p.players_prev, 0), 1)
        END AS dynamics_percent
    FROM all_games ag
    LEFT JOIN current c ON ag.game = c.game
    LEFT JOIN previous p ON ag.game = p.game
    ORDER BY percent DESC NULLS LAST;
    """
    return fetch_all(query)

def get_bots_status() -> Dict[str, Any]:
    """Возвращает количество активных ботов и общее количество ботов."""
    total = fetch_one("SELECT COUNT(*) AS total FROM users WHERE is_bot = TRUE")
    active = fetch_one("""
        SELECT COUNT(DISTINCT u.id) AS active
        FROM users u
        JOIN room_members rm ON rm.user_id = u.id
        JOIN rooms r ON r.id = rm.room_id
        WHERE u.is_bot = TRUE AND r.status IN ('waiting', 'lobby', 'shop', 'running')
    """)
    return {
        "active_bots": active["active"] if active else 0,
        "total_bots": total["total"] if total else 0
    }


def get_top_patterns(limit: int = 10) -> List[Dict[str, Any]]:
    """
    Топ паттернов по количеству реальных игроков + прибыль казино.

    real_players: количество DISTINCT human user_id по всем комнатам паттерна.
    profit: сумма ledger_entries(casino_income) по комнатам паттерна (finished/running тоже ок).
    """
    return fetch_all(
        """
        WITH human_members AS (
            SELECT
                r.room_pattern_id AS pattern_id,
                rm.user_id
            FROM room_members rm
            JOIN rooms r ON r.id = rm.room_id
            JOIN users u ON u.id = rm.user_id
            WHERE u.is_bot = FALSE
        ),
        profits AS (
            SELECT
                r.room_pattern_id AS pattern_id,
                COALESCE(SUM(
                    CASE
                        WHEN le.account = 'casino' AND le.entry_type = 'casino_income'
                        THEN le.amount
                        ELSE 0
                    END
                ), 0)::bigint AS profit
            FROM rooms r
            LEFT JOIN ledger_entries le ON le.room_id = r.id
            GROUP BY r.room_pattern_id
        )
        SELECT
            rp.id,
            rp.game,
            COUNT(DISTINCT hm.user_id)::int AS real_players,
            rp.join_cost,
            COALESCE(p.profit, 0)::bigint AS profit
        FROM room_pattern rp
        LEFT JOIN human_members hm ON hm.pattern_id = rp.id
        LEFT JOIN profits p ON p.pattern_id = rp.id
        WHERE rp.is_active = TRUE
        GROUP BY rp.id, rp.game, rp.join_cost, p.profit
        ORDER BY real_players DESC, profit DESC, rp.id DESC
        LIMIT %s
        """,
        (int(limit),),
    )


def get_kpi(days: int = 7) -> Dict[str, Any]:
    row = fetch_one(
        """
        WITH period AS (
            SELECT NOW() - (%s * INTERVAL '1 day') AS since
        ),
        rooms_period AS (
            SELECT r.*
            FROM rooms r, period p
            WHERE r.created_at >= p.since
        ),
        members_period AS (
            SELECT rm.room_id, rm.user_id, u.is_bot
            FROM room_members rm
            JOIN users u ON u.id = rm.user_id
            JOIN rooms_period r ON r.id = rm.room_id
        ),
        pattern_costs AS (
            SELECT r.id AS room_id, rp.join_cost, rp.boost_cost_per_point, rp.game
            FROM rooms_period r
            JOIN room_pattern rp ON rp.id = r.room_pattern_id
        ),
        funds AS (
            SELECT
                COUNT(rm.id)::bigint * pc.join_cost::bigint AS stake_fund,
                COALESCE(SUM(COALESCE(rm.boost, 0)), 0)::bigint * pc.boost_cost_per_point::bigint AS boost_fund
            FROM rooms_period r
            JOIN pattern_costs pc ON pc.room_id = r.id
            LEFT JOIN room_members rm ON rm.room_id = r.id
            GROUP BY pc.join_cost, pc.boost_cost_per_point, r.id
        ),
        ledger_period AS (
            SELECT le.*
            FROM ledger_entries le, period p
            WHERE le.created_at >= p.since
        ),
        casino_income AS (
            SELECT COALESCE(SUM(amount), 0)::bigint AS amount
            FROM ledger_period
            WHERE account = 'casino' AND entry_type = 'casino_income'
        ),
        bot_spend AS (
            SELECT COALESCE(SUM(-amount), 0)::bigint AS amount
            FROM ledger_period
            WHERE account = 'casino' AND entry_type = 'bot_slots' AND amount < 0
        ),
        payouts AS (
            SELECT COALESCE(SUM(amount), 0)::bigint AS amount
            FROM ledger_period
            WHERE entry_type = 'payout'
        ),
        active_rooms AS (
            SELECT COUNT(*)::int AS cnt
            FROM rooms
            WHERE status IN ('waiting', 'lobby', 'shop', 'running')
        )
        SELECT
            %s::int AS days,
            (SELECT cnt FROM active_rooms) AS active_rooms,
            (SELECT COUNT(*)::int FROM rooms_period) AS rooms_created,
            (SELECT COUNT(*)::int FROM rooms_period WHERE status = 'finished') AS rooms_finished,
            (SELECT COUNT(*)::int FROM rooms_period WHERE status IN ('waiting','lobby','shop','running')) AS rooms_active_in_period,
            (SELECT COUNT(DISTINCT user_id)::int FROM members_period WHERE is_bot = FALSE) AS uniq_players,
            (SELECT COUNT(*)::int FROM members_period WHERE is_bot = FALSE) AS human_slots,
            (SELECT COUNT(*)::int FROM members_period WHERE is_bot = TRUE) AS bot_slots,
            (SELECT COALESCE(SUM(stake_fund), 0)::bigint FROM funds) AS stake_volume,
            (SELECT COALESCE(SUM(boost_fund), 0)::bigint FROM funds) AS boost_volume,
            (SELECT amount FROM casino_income) AS casino_income,
            (SELECT amount FROM bot_spend) AS bot_spend,
            (SELECT amount FROM payouts) AS payouts,
            ((SELECT amount FROM casino_income) - (SELECT amount FROM bot_spend))::bigint AS casino_profit_net
        """,
        (int(days), int(days)),
    )
    return row or {"days": int(days)}


def get_funnel(days: int = 7) -> Dict[str, Any]:
    row = fetch_one(
        """
        WITH period AS (
            SELECT NOW() - (%s * INTERVAL '1 day') AS since
        ),
        rooms_period AS (
            SELECT r.*
            FROM rooms r, period p
            WHERE r.created_at >= p.since
        )
        SELECT
            %s::int AS days,
            COUNT(*)::int AS rooms_total,
            COUNT(*) FILTER (WHERE status = 'waiting')::int AS waiting,
            COUNT(*) FILTER (WHERE status = 'lobby')::int AS lobby,
            COUNT(*) FILTER (WHERE status = 'shop')::int AS shop,
            COUNT(*) FILTER (WHERE status = 'running')::int AS running,
            COUNT(*) FILTER (WHERE status = 'finished')::int AS finished
        FROM rooms_period
        """,
        (int(days), int(days)),
    )
    return row or {"days": int(days)}


def get_revenue_series(days: int = 30, bucket: Literal["day", "hour"] = "day") -> List[Dict[str, Any]]:
    if bucket not in ("day", "hour"):
        bucket = "day"
    return fetch_all(
        f"""
        WITH period AS (
            SELECT NOW() - (%s * INTERVAL '1 day') AS since
        ),
        ledger_period AS (
            SELECT le.*
            FROM ledger_entries le, period p
            WHERE le.created_at >= p.since
        )
        SELECT
            date_trunc('{bucket}', created_at) AS ts,
            COALESCE(SUM(amount) FILTER (WHERE account = 'casino' AND entry_type = 'casino_income'), 0)::bigint AS casino_income,
            COALESCE(SUM(-amount) FILTER (WHERE account = 'casino' AND entry_type = 'bot_slots' AND amount < 0), 0)::bigint AS bot_spend,
            COALESCE(SUM(amount) FILTER (WHERE entry_type = 'payout'), 0)::bigint AS payouts
        FROM ledger_period
        GROUP BY 1
        ORDER BY 1
        """,
        (int(days),),
    )


def get_top_players(days: int = 30, limit: int = 20) -> List[Dict[str, Any]]:
    return fetch_all(
        """
        WITH period AS (
            SELECT NOW() - (%s * INTERVAL '1 day') AS since
        ),
        user_ledger AS (
            SELECT
                u.id AS user_id,
                u.username,
                COALESCE(SUM(
                    CASE WHEN le.account = 'user' AND le.amount < 0 THEN -le.amount ELSE 0 END
                ), 0)::bigint AS spent_amount,
                COALESCE(SUM(
                    CASE WHEN le.entry_type = 'payout' THEN le.amount ELSE 0 END
                ), 0)::bigint AS payout_amount
            FROM users u
            LEFT JOIN ledger_entries le ON le.user_id = u.id
            JOIN period p ON TRUE
            WHERE u.is_bot = FALSE
              AND (le.created_at IS NULL OR le.created_at >= p.since)
            GROUP BY u.id, u.username
        )
        SELECT
            user_id,
            username,
            spent_amount,
            payout_amount,
            (payout_amount - spent_amount)::bigint AS net_amount
        FROM user_ledger
        ORDER BY net_amount DESC, payout_amount DESC, spent_amount DESC
        LIMIT %s
        """,
        (int(days), int(limit)),
    )


def get_top_rooms(days: int = 30, limit: int = 20) -> List[Dict[str, Any]]:
    return fetch_all(
        """
        WITH period AS (
            SELECT NOW() - (%s * INTERVAL '1 day') AS since
        ),
        rooms_period AS (
            SELECT r.id, r.access_token, r.status, r.created_at, r.ended_at, r.winner_id, rp.game, rp.join_cost, rp.rank, rp.boost_cost_per_point
            FROM rooms r
            JOIN room_pattern rp ON rp.id = r.room_pattern_id
            JOIN period p ON TRUE
            WHERE r.created_at >= p.since
        ),
        funds AS (
            SELECT
                rp.id AS room_id,
                (COUNT(rm.id)::bigint * rp.join_cost::bigint) AS stake_fund,
                (COALESCE(SUM(COALESCE(rm.boost, 0)), 0)::bigint * rp.boost_cost_per_point::bigint) AS boost_fund
            FROM rooms_period rp
            LEFT JOIN room_members rm ON rm.room_id = rp.id
            GROUP BY rp.id, rp.join_cost, rp.boost_cost_per_point
        ),
        casino_income AS (
            SELECT le.room_id, COALESCE(SUM(le.amount), 0)::bigint AS casino_income
            FROM ledger_entries le
            JOIN period p ON TRUE
            WHERE le.created_at >= p.since
              AND le.account = 'casino'
              AND le.entry_type = 'casino_income'
            GROUP BY le.room_id
        )
        SELECT
            r.id AS room_id,
            r.access_token,
            r.status,
            r.game,
            r.join_cost,
            r.rank,
            r.created_at,
            r.ended_at,
            r.winner_id,
            (f.stake_fund + f.boost_fund)::bigint AS total_fund,
            f.stake_fund,
            f.boost_fund,
            COALESCE(ci.casino_income, 0)::bigint AS casino_income
        FROM rooms_period r
        LEFT JOIN funds f ON f.room_id = r.id
        LEFT JOIN casino_income ci ON ci.room_id = r.id
        ORDER BY total_fund DESC, casino_income DESC, r.id DESC
        LIMIT %s
        """,
        (int(days), int(limit)),
    )
