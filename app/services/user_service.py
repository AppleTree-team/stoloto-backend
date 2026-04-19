from app.db.db import fetch


# --------------------
# USER PROFILE
# --------------------
def get_user_profile(user_id: int):
    user = fetch(
        "SELECT id, username, balance, created_at, is_bot FROM users WHERE id = %s",
        (user_id,)
    )

    if not user:
        return None

    history = fetch(
        """
        SELECT 
            r.id as room_id,
            r.status,
            r.winner_id,
            r.created_at,
            rp.game,
            rp.join_cost
        FROM room_members rm
        JOIN rooms r ON rm.room_id = r.id
        JOIN room_pattern rp ON r.room_pattern_id = rp.id
        WHERE rm.user_id = %s
        ORDER BY rm.joined_at DESC 
        LIMIT 10
        """,
        (user_id,)
    )

    # обработка результата
    if not isinstance(history, list):
        history = [history] if history else []

    return {
        "user": user,
        "history": history
    }