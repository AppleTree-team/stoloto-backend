from typing import List, Dict, Any, Optional

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