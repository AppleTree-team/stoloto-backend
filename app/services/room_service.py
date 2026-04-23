import secrets
from typing import List, Dict, Any, Optional


from app.db.db import fetch_one, fetch_all, execute_with_returning


# =========================================================
# 🔧 AUXILIARY FUNCTIONS
# =========================================================

def generate_access_token() -> str:
    """Генерирует длинную случайную строку для токена комнаты."""
    return secrets.token_urlsafe(48)


def get_room_by_id(room_id: int):
    return fetch_one("""
        SELECT * 
        FROM room
        WHERE id = %s
    """, (room_id,))


def get_room_by_token(token: str) -> Optional[Dict]:
    """Возвращает id, status, game, cost комнаты по токену."""
    return fetch_one("""
        SELECT
            r.*,
            rp.game,
            rp.join_cost,
            rp.max_members_count,
            rp.rank,
            rp.waiting_lobby_stage,
            rp.waiting_shop_stage,
            rp.boost_cost_per_point
        FROM rooms r
        JOIN room_pattern rp ON rp.id = r.room_pattern_id
        WHERE r.access_token = %s
    """, (token,))


def start_lobby_if_waiting(room_id: int, waiting_lobby_stage_seconds: int) -> bool:
    """
    Если комната в статусе waiting — переводит в lobby и выставляет started_at как
    (текущее время + waiting_lobby_stage).

    Возвращает True, если статус реально изменился.
    """
    result = execute_with_returning("""
        WITH locked AS (
            SELECT pg_advisory_xact_lock(%s, 1)
        )
        UPDATE rooms
        SET status = 'lobby',
            started_at = NOW() + (%s * INTERVAL '1 second')
        WHERE id = %s AND status = 'waiting'
        RETURNING id
    """, (int(room_id), int(waiting_lobby_stage_seconds or 0), room_id))
    return bool(result)


def set_lobby_timer_if_missing(room_id: int, waiting_lobby_stage_seconds: int) -> bool:
    """
    Если комната уже в lobby, но таймер не выставлен (started_at IS NULL) —
    выставляет started_at = NOW() + waiting_lobby_stage.

    Возвращает True, если started_at был установлен в этом вызове.
    """
    result = execute_with_returning("""
        WITH locked AS (
            SELECT pg_advisory_xact_lock(%s, 1)
        )
        UPDATE rooms
        SET started_at = NOW() + (%s * INTERVAL '1 second')
        WHERE id = %s AND status = 'lobby' AND started_at IS NULL
        RETURNING id
    """, (int(room_id), int(waiting_lobby_stage_seconds or 0), room_id))
    return bool(result)


def ensure_user_added_to_room_once(room_id: int, user_id: int) -> Dict[str, Any]:
    """
    Добавляет пользователя в комнату (1 слот) ровно один раз и списывает стоимость входа.
    Идемпотентно и безопасно при конкурентных вызовах.

    Возвращает:
      - success: bool
      - inserted: bool (создан ли слот в этом вызове)
      - already_joined: bool
      - message: str (если success=False)
    """
    result = execute_with_returning("""
        WITH user_locked AS (
            SELECT pg_advisory_xact_lock(%s, 2)
        ),
        locked AS (
            SELECT pg_advisory_xact_lock(%s, 1)
        ),
        room_data AS (
            SELECT r.status, rp.max_members_count, rp.join_cost
            FROM rooms r
            JOIN room_pattern rp ON rp.id = r.room_pattern_id
            WHERE r.id = %s
        ),
        other_active AS (
            SELECT r.id AS active_room_id, r.access_token AS active_room_access_token, r.status AS active_room_status
            FROM room_members rm
            JOIN rooms r ON r.id = rm.room_id
            WHERE rm.user_id = %s
              AND r.status IN ('waiting', 'lobby', 'shop', 'running')
              AND r.id <> %s
            ORDER BY COALESCE(r.started_at, r.created_at) DESC, r.id DESC
            LIMIT 1
        ),
        existing AS (
            SELECT rm.id
            FROM room_members rm
            WHERE rm.room_id = %s AND rm.user_id = %s
            LIMIT 1
        ),
        counts AS (
            SELECT (SELECT COUNT(*)::int FROM room_members WHERE room_id = %s) AS members_count
        ),
        allowed AS (
            SELECT
                (rd.status IN ('waiting', 'lobby')) AS ok_status,
                (c.members_count < rd.max_members_count) AS ok_capacity,
                (NOT EXISTS (SELECT 1 FROM other_active)) AS ok_user_free,
                (SELECT active_room_id FROM other_active) AS active_room_id,
                (SELECT active_room_access_token FROM other_active) AS active_room_access_token,
                (SELECT active_room_status FROM other_active) AS active_room_status,
                rd.join_cost AS join_cost
            FROM room_data rd, counts c
        ),
        pay AS (
            UPDATE users
            SET balance = balance - (SELECT join_cost FROM allowed)
            WHERE id = %s
              AND is_bot = FALSE
              AND balance >= (SELECT join_cost FROM allowed)
              AND NOT EXISTS (SELECT 1 FROM existing)
              AND (SELECT ok_status AND ok_capacity AND ok_user_free FROM allowed)
            RETURNING id
        ),
        ins AS (
            INSERT INTO room_members (room_id, user_id, boost)
            SELECT %s, %s, 0
            WHERE EXISTS (SELECT 1 FROM pay)
            RETURNING id
        ),
        escrow_init AS (
            INSERT INTO room_escrow (room_id, amount)
            VALUES (%s, 0)
            ON CONFLICT (room_id) DO NOTHING
        ),
        escrow_upd AS (
            UPDATE room_escrow
            SET amount = amount + (SELECT join_cost FROM allowed),
                stake_amount = stake_amount + (SELECT join_cost FROM allowed),
                updated_at = NOW()
            WHERE room_id = %s AND EXISTS (SELECT 1 FROM ins)
            RETURNING amount
        ),
        ledger_user AS (
            INSERT INTO ledger_entries (room_id, user_id, account, entry_type, amount, meta)
            SELECT
                %s, %s, 'user', 'join', -(SELECT join_cost FROM allowed),
                jsonb_build_object('slot_id', (SELECT id FROM ins), 'kind', 'join')
            WHERE EXISTS (SELECT 1 FROM ins)
            RETURNING 1
        ),
        ledger_escrow AS (
            INSERT INTO ledger_entries (room_id, user_id, account, entry_type, amount, meta)
            SELECT
                %s, %s, 'escrow', 'join', (SELECT join_cost FROM allowed),
                jsonb_build_object('slot_id', (SELECT id FROM ins), 'kind', 'join')
            WHERE EXISTS (SELECT 1 FROM ins)
            RETURNING 1
        )
        SELECT
            (EXISTS (SELECT 1 FROM existing)) AS already_joined,
            (SELECT ok_status FROM allowed) AS ok_status,
            (SELECT ok_capacity FROM allowed) AS ok_capacity,
            (SELECT ok_user_free FROM allowed) AS ok_user_free,
            (SELECT active_room_id FROM allowed) AS active_room_id,
            (SELECT active_room_access_token FROM allowed) AS active_room_access_token,
            (SELECT active_room_status FROM allowed) AS active_room_status,
            (SELECT join_cost FROM allowed) AS join_cost,
            (SELECT id FROM ins) AS slot_id,
            (SELECT COUNT(*)::int FROM ins) AS inserted
    """, (
        int(user_id),  # user lock
        int(room_id),  # room lock
        int(room_id),  # room_data
        int(user_id),  # other_active.user_id
        int(room_id),  # other_active.exclude room_id
        int(room_id),  # existing.room_id
        int(user_id),  # existing.user_id
        int(room_id),  # counts.room_id
        int(user_id),  # pay.user_id
        int(room_id),  # ins.room_id
        int(user_id),  # ins.user_id
        int(room_id),  # escrow_init.room_id
        int(room_id),  # escrow_upd.room_id
        int(room_id),  # ledger_user.room_id
        int(user_id),  # ledger_user.user_id
        int(room_id),  # ledger_escrow.room_id
        int(user_id),  # ledger_escrow.user_id
    ))

    if not result:
        return {"success": False, "message": "Room not found"}

    if result.get("already_joined"):
        return {"success": True, "inserted": False, "already_joined": True}

    ok_status = bool(result.get("ok_status"))
    ok_capacity = bool(result.get("ok_capacity"))
    ok_user_free = bool(result.get("ok_user_free"))
    inserted = bool(result.get("inserted"))

    if inserted:
        return {"success": True, "inserted": True, "already_joined": False, "slot_id": result.get("slot_id")}

    if not ok_status:
        return {"success": False, "message": "Room is not joinable now"}
    if not ok_capacity:
        return {"success": False, "message": "No free slots"}
    if not ok_user_free:
        return {
            "success": False,
            "message": "User already in active game",
            "active_room_id": result.get("active_room_id"),
            "active_room_access_token": result.get("active_room_access_token"),
            "active_room_status": result.get("active_room_status"),
        }
    return {"success": False, "message": "Not enough balance"}


def get_room_escrow_amount(room_id: int) -> int:
    snapshot = get_room_escrow_snapshot(room_id)
    return int(snapshot["amount"])


def get_room_escrow_snapshot(room_id: int) -> Dict[str, int]:
    result = fetch_one("""
        SELECT
            COALESCE(COUNT(rm.id), 0)::bigint * COALESCE(rp.join_cost, 0)::bigint AS stake_amount,
            COALESCE(SUM(COALESCE(rm.boost, 0)), 0)::bigint * COALESCE(rp.boost_cost_per_point, 0)::bigint AS boost_amount
        FROM rooms r
        JOIN room_pattern rp ON rp.id = r.room_pattern_id
        LEFT JOIN room_members rm ON rm.room_id = r.id
        WHERE r.id = %s
        GROUP BY rp.join_cost, rp.boost_cost_per_point
    """, (room_id,))
    if not result:
        return {"amount": 0, "stake_amount": 0, "boost_amount": 0}
    stake_amount = int(result.get("stake_amount") or 0)
    boost_amount = int(result.get("boost_amount") or 0)
    return {
        "amount": stake_amount + boost_amount,
        "stake_amount": stake_amount,
        "boost_amount": boost_amount,
    }


def get_room_members_count(room_id: int) -> int:
    result = fetch_one("""
        SELECT COUNT(*)::int AS cnt
        FROM room_members
        WHERE room_id = %s
    """, (room_id,))
    return int(result["cnt"]) if result else 0


def get_lobby_seconds_left(room_id: int) -> Optional[int]:
    """
    Возвращает оставшееся время лобби (started_at - NOW()) в секундах.
    None если started_at не установлен.
    """
    result = fetch_one("""
        SELECT
            CASE
                WHEN started_at IS NULL THEN NULL
                ELSE GREATEST(0, FLOOR(EXTRACT(EPOCH FROM (started_at - NOW())))::int)
            END AS seconds_left
        FROM rooms
        WHERE id = %s
    """, (room_id,))
    if not result:
        return None
    return result["seconds_left"]


def get_room_total_weight(room_id: int) -> int:
    result = fetch_one("""
        SELECT COALESCE(SUM(1 + COALESCE(boost, 0)), 0)::int AS total_weight
        FROM room_members
        WHERE room_id = %s
    """, (room_id,))
    return int(result["total_weight"]) if result else 0


def get_room_victory_chance(room_id: int, user_id: int) -> Dict[str, Any]:
    """
    Возвращает "шанс победы" пользователя в комнате.

    - current: шанс среди текущих участников (user_weight / total_weight)
    - capacity: шанс, если считать, что свободные места будут заняты слотами с весом 1
      (user_weight / (total_weight + free_slots)). Это то, что обычно ожидают как "процент от общего кол-ва мест".
    """
    row = fetch_one("""
        SELECT
            rp.max_members_count::int AS max_members_count,
            (SELECT COUNT(*)::int FROM room_members WHERE room_id = %s) AS members_count,
            (SELECT COALESCE(SUM(1 + COALESCE(boost, 0)), 0)::int FROM room_members WHERE room_id = %s) AS total_weight,
            (SELECT COALESCE(SUM(1 + COALESCE(boost, 0)), 0)::int FROM room_members WHERE room_id = %s AND user_id = %s) AS user_weight
        FROM rooms r
        JOIN room_pattern rp ON rp.id = r.room_pattern_id
        WHERE r.id = %s
    """, (int(room_id), int(room_id), int(room_id), int(user_id), int(room_id)))

    if not row:
        return {"success": False, "message": "Room not found"}

    max_members_count = int(row.get("max_members_count") or 0)
    members_count = int(row.get("members_count") or 0)
    total_weight = int(row.get("total_weight") or 0)
    user_weight = int(row.get("user_weight") or 0)

    free_slots = max(0, max_members_count - members_count)

    chance_current = (user_weight / total_weight) if total_weight > 0 else 0.0
    denom_capacity = total_weight + free_slots
    chance_capacity = (user_weight / denom_capacity) if denom_capacity > 0 else 0.0

    return {
        "success": True,
        "max_members_count": max_members_count,
        "members_count": members_count,
        "free_slots": free_slots,
        "total_weight": total_weight,
        "user_weight": user_weight,
        "chance_current": chance_current,
        "chance_current_percent": chance_current * 100.0,
        "chance_capacity": chance_capacity,
        "chance_capacity_percent": chance_capacity * 100.0,
    }


def finish_lobby_to_shop_if_lobby(room_id: int, waiting_shop_stage_seconds: int) -> bool:
    """
    Переводит комнату из lobby в shop один раз.
    started_at выставляем как (NOW() + waiting_shop_stage) — это дедлайн стадии shop.
    """
    result = execute_with_returning("""
        WITH locked AS (
            SELECT pg_advisory_xact_lock(%s, 1)
        )
        UPDATE rooms
        SET status = 'shop',
            started_at = NOW() + (%s * INTERVAL '1 second')
        WHERE id = %s AND status = 'lobby'
        RETURNING id
    """, (int(room_id), int(waiting_shop_stage_seconds or 0), room_id))
    return bool(result)


def get_lobby_rooms_ready_for_shop(limit: int = 200) -> List[Dict[str, Any]]:
    """
    Комнаты в lobby, которые пора переводить в shop:
    - таймер лобби закончился (started_at <= NOW())
    - или набралось >= 50% мест (минимум 2 участника)
    """
    return fetch_all("""
        WITH counts AS (
            SELECT room_id, COUNT(*)::int AS members_count
            FROM room_members
            GROUP BY room_id
        )
        SELECT
            r.id,
            rp.waiting_shop_stage,
            rp.max_members_count,
            COALESCE(c.members_count, 0) AS members_count
        FROM rooms r
        JOIN room_pattern rp ON rp.id = r.room_pattern_id
        LEFT JOIN counts c ON c.room_id = r.id
        WHERE r.status = 'lobby'
          AND (
            (r.started_at IS NOT NULL AND r.started_at <= NOW() AND COALESCE(c.members_count, 0) >= 1)
            OR COALESCE(c.members_count, 0) >= GREATEST(2, (rp.max_members_count + 1) / 2)
          )
        ORDER BY r.id ASC
        LIMIT %s
    """, (int(limit),))


def get_shop_rooms_due(limit: int = 200) -> List[Dict[str, Any]]:
    """
    Комнаты в shop, у которых истёк таймер стадии (started_at <= NOW()).
    """
    return fetch_all("""
        WITH counts AS (
            SELECT room_id, COUNT(*)::int AS members_count
            FROM room_members
            GROUP BY room_id
        )
        SELECT r.id
        FROM rooms r
        JOIN counts c ON c.room_id = r.id
        WHERE r.status = 'shop'
          AND r.started_at IS NOT NULL
          AND r.started_at <= NOW()
          AND c.members_count >= 1
        ORDER BY r.id ASC
        LIMIT %s
    """, (int(limit),))


def finish_shop_and_pick_winner(room_id: int) -> Optional[Dict[str, Any]]:
    """
    Завершает стадию shop и выбирает победителя (веса: 1 + boost для каждого слота).
    Возвращает {id, winner_id, ended_at} или None, если апдейт не произошёл.
    """
    result = execute_with_returning("""
        WITH locked AS (
            SELECT pg_advisory_xact_lock(%s, 1)
        ),
        members AS (
            SELECT
                rm.id,
                rm.user_id,
                (1 + COALESCE(rm.boost, 0))::int AS weight,
                SUM((1 + COALESCE(rm.boost, 0))::int) OVER () AS total_weight,
                SUM((1 + COALESCE(rm.boost, 0))::int) OVER (ORDER BY rm.id) AS cum_weight
            FROM room_members rm
            WHERE rm.room_id = %s
        ),
        rnd AS (
            SELECT (FLOOR(RANDOM() * (SELECT total_weight FROM members LIMIT 1))::int + 1) AS r
        ),
        winner AS (
            SELECT m.user_id
            FROM members m, rnd
            WHERE m.cum_weight >= rnd.r
            ORDER BY m.cum_weight
            LIMIT 1
        ),
        upd AS (
            UPDATE rooms
            SET status = 'finished',
                winner_id = (SELECT user_id FROM winner),
                ended_at = NOW()
            WHERE id = %s
              AND status = 'shop'
              AND EXISTS (SELECT 1 FROM members)
            RETURNING id, winner_id, ended_at
        )
        SELECT * FROM upd
    """, (int(room_id), int(room_id), int(room_id)))
    return result


def start_game_if_shop(room_id: int) -> Dict[str, Any]:
    """
    Переводит комнату из shop в running (старт игры) один раз.
    """
    result = execute_with_returning("""
        WITH locked AS (
            SELECT pg_advisory_xact_lock(%s, 1)
        ),
        anchor AS (
            SELECT 1 AS one
        ),
        room_data AS (
            SELECT r.id, r.status, rp.max_members_count, rp.join_cost
            FROM rooms r
            JOIN room_pattern rp ON rp.id = r.room_pattern_id
            WHERE r.id = %s
            FOR UPDATE
        ),
        cfg AS (
            SELECT casino_balance::bigint AS casino_balance,
                   COALESCE(bots_enabled, TRUE) AS bots_enabled
            FROM system_config
            WHERE id = 1
            FOR UPDATE
        ),
        cfg_row AS (
            SELECT casino_balance, bots_enabled
            FROM cfg
            UNION ALL
            SELECT 0::bigint AS casino_balance, TRUE AS bots_enabled
            WHERE NOT EXISTS (SELECT 1 FROM cfg)
        ),
        counts AS (
            SELECT COUNT(*)::int AS members_count
            FROM room_members
            WHERE room_id = %s
        ),
        to_fill AS (
            SELECT
                (COALESCE(rd.status::text, '') = 'shop') AS ok_shop,
                COALESCE(rd.join_cost, 0)::bigint AS join_cost,
                COALESCE(rd.max_members_count, 0)::int AS max_members_count,
                c.members_count::int AS members_count,
                cfg.casino_balance::bigint AS casino_balance,
                GREATEST(0, COALESCE(rd.max_members_count, 0) - c.members_count)::int AS free_slots,
                LEAST(
                    GREATEST(0, COALESCE(rd.max_members_count, 0) - c.members_count)::bigint,
                    CASE
                        WHEN NOT cfg.bots_enabled THEN 0
                        WHEN COALESCE(rd.join_cost, 0) > 0 THEN (cfg.casino_balance / rd.join_cost)
                        ELSE 0
                    END
                )::int AS fill_slots
            FROM anchor a
            LEFT JOIN room_data rd ON TRUE
            CROSS JOIN cfg_row cfg
            CROSS JOIN counts c
        ),
        bots AS (
            SELECT id AS bot_id
            FROM users
            WHERE is_bot = TRUE
              AND id NOT IN (SELECT user_id FROM room_members WHERE room_id = %s)
            ORDER BY RANDOM()
            LIMIT (SELECT fill_slots FROM to_fill)
        ),
        ins AS (
            INSERT INTO room_members (room_id, user_id, boost)
            SELECT %s, bot_id, 0
            FROM bots
            WHERE (SELECT ok_shop FROM to_fill) AND (SELECT fill_slots FROM to_fill) > 0
            RETURNING id, user_id
        ),
        cost AS (
            SELECT ((SELECT join_cost FROM to_fill) * (SELECT COUNT(*) FROM ins))::bigint AS total_cost,
                   (SELECT COUNT(*)::int FROM ins) AS bots_added
        ),
        escrow_init AS (
            INSERT INTO room_escrow (room_id, amount)
            VALUES (%s, 0)
            ON CONFLICT (room_id) DO NOTHING
        ),
        escrow_upd AS (
            UPDATE room_escrow
            SET amount = amount + (SELECT total_cost FROM cost),
                stake_amount = stake_amount + (SELECT total_cost FROM cost),
                updated_at = NOW()
            WHERE room_id = %s AND (SELECT total_cost FROM cost) > 0
            RETURNING amount
        ),
        cfg_upd AS (
            UPDATE system_config
            SET casino_balance = casino_balance - (SELECT total_cost FROM cost)
            WHERE id = 1 AND (SELECT total_cost FROM cost) > 0
            RETURNING casino_balance
        ),
        ledger_casino AS (
            INSERT INTO ledger_entries (room_id, user_id, account, entry_type, amount, meta)
            SELECT
                %s,
                NULL,
                'casino',
                'bot_slots',
                -(SELECT total_cost FROM cost),
                jsonb_build_object(
                    'bots_added', (SELECT bots_added FROM cost),
                    'bot_ids', COALESCE((SELECT jsonb_agg(user_id) FROM ins), '[]'::jsonb)
                )
            WHERE (SELECT total_cost FROM cost) > 0
            RETURNING 1
        ),
        ledger_escrow AS (
            INSERT INTO ledger_entries (room_id, user_id, account, entry_type, amount, meta)
            SELECT
                %s,
                NULL,
                'escrow',
                'bot_slots',
                (SELECT total_cost FROM cost),
                jsonb_build_object('bots_added', (SELECT bots_added FROM cost))
            WHERE (SELECT total_cost FROM cost) > 0
            RETURNING 1
        ),
        upd_room AS (
            UPDATE rooms
            SET status = 'running',
                started_at = NOW()
            WHERE id = %s
              AND status = 'shop'
              AND EXISTS (SELECT 1 FROM room_members WHERE room_id = %s)
            RETURNING id
        )
        SELECT
            (SELECT id FROM upd_room) AS id,
            (SELECT ok_shop FROM to_fill) AS ok_shop,
            (SELECT members_count FROM to_fill) AS members_before,
            (SELECT free_slots FROM to_fill) AS free_slots,
            (SELECT fill_slots FROM to_fill) AS fill_slots,
            (SELECT max_members_count FROM to_fill) AS max_members_count,
            (SELECT bots_added FROM cost) AS bots_added,
            (SELECT total_cost FROM cost) AS total_cost,
            (SELECT amount FROM escrow_upd) AS escrow_amount_after
        FROM to_fill
    """, (
        int(room_id),  # lock
        int(room_id),  # room_data
        int(room_id),  # counts
        int(room_id),  # bots exclude existing
        int(room_id),  # ins room_id
        int(room_id),  # escrow_init
        int(room_id),  # escrow_upd
        int(room_id),  # ledger_casino
        int(room_id),  # ledger_escrow
        int(room_id),  # upd_room
        int(room_id),  # upd_room exists
    ))
    if not result:
        return {
            "success": False,
            "room_id": int(room_id),
            "started": False,
            "message": "Room not found",
        }

    return {
        "success": True,
        "room_id": int(room_id),
        "started": bool(result.get("id")),
        **result,
    }


def finish_game_and_pick_winner_if_running(room_id: int) -> Optional[Dict[str, Any]]:
    """
    Завершает игру (running -> finished) и выбирает победителя.
    Веса: 1 + boost для каждого слота.
    """
    result = execute_with_returning("""
        WITH locked AS (
            SELECT pg_advisory_xact_lock(%s, 1)
        ),
        room_data AS (
            SELECT r.id, rp.rank, rp.join_cost, rp.boost_cost_per_point
            FROM rooms r
            JOIN room_pattern rp ON rp.id = r.room_pattern_id
            WHERE r.id = %s
        ),
        funds AS (
            SELECT
                (COUNT(rm.id)::bigint * rd.join_cost::bigint) AS stake_fund,
                (COALESCE(SUM(COALESCE(rm.boost, 0)), 0)::bigint * rd.boost_cost_per_point::bigint) AS boost_fund,
                ((COUNT(rm.id)::bigint * rd.join_cost::bigint) + (COALESCE(SUM(COALESCE(rm.boost, 0)), 0)::bigint * rd.boost_cost_per_point::bigint)) AS total_fund
            FROM room_data rd
            LEFT JOIN room_members rm ON rm.room_id = rd.id
            GROUP BY rd.join_cost, rd.boost_cost_per_point
        ),
        members AS (
            SELECT
                rm.id,
                rm.user_id,
                (1 + COALESCE(rm.boost, 0))::int AS weight,
                SUM((1 + COALESCE(rm.boost, 0))::int) OVER () AS total_weight,
                SUM((1 + COALESCE(rm.boost, 0))::int) OVER (ORDER BY rm.id) AS cum_weight
            FROM room_members rm
            WHERE rm.room_id = %s
        ),
        rnd AS (
            SELECT (FLOOR(RANDOM() * (SELECT total_weight FROM members LIMIT 1))::int + 1) AS r
        ),
        winner AS (
            SELECT m.user_id
            FROM members m, rnd
            WHERE m.cum_weight >= rnd.r
            ORDER BY m.cum_weight
            LIMIT 1
        ),
        calc AS (
            SELECT
                f.total_fund,
                f.stake_fund,
                f.boost_fund,
                FLOOR(f.stake_fund * (rd.rank / 100.0))::bigint AS casino_cut,
                GREATEST(0, f.stake_fund - FLOOR(f.stake_fund * (rd.rank / 100.0))::bigint) + f.boost_fund AS prize_pool,
                GREATEST(0, f.stake_fund - FLOOR(f.stake_fund * (rd.rank / 100.0))::bigint) + f.boost_fund AS winner_payout
            FROM funds f, room_data rd
        ),
        upd_room AS (
            UPDATE rooms
            SET status = 'finished',
                winner_id = (SELECT user_id FROM winner),
                ended_at = NOW()
            WHERE id = %s
              AND status = 'running'
              AND EXISTS (SELECT 1 FROM members)
            RETURNING id, winner_id, ended_at
        ),
        upd_winner AS (
            UPDATE users
            SET balance = balance + (SELECT winner_payout FROM calc)
            WHERE id = (SELECT winner_id FROM upd_room)
              AND (SELECT winner_payout FROM calc) > 0
            RETURNING id
        ),
        upd_casino AS (
            UPDATE system_config
            SET casino_balance = casino_balance + (SELECT (total_fund - winner_payout) FROM calc)
            WHERE id = 1 AND EXISTS (SELECT 1 FROM upd_room)
            RETURNING casino_balance
        ),
        escrow_zero AS (
            UPDATE room_escrow
            SET amount = 0,
                stake_amount = 0,
                boost_amount = 0,
                updated_at = NOW()
            WHERE room_id = %s AND EXISTS (SELECT 1 FROM upd_room)
            RETURNING amount
        ),
        ledger_winner AS (
            INSERT INTO ledger_entries (room_id, user_id, account, entry_type, amount, meta)
            SELECT
                (SELECT id FROM upd_room),
                (SELECT winner_id FROM upd_room),
                'user',
                'payout',
                (SELECT winner_payout FROM calc),
                jsonb_build_object(
                    'total_fund', (SELECT total_fund FROM calc),
                    'stake_fund', (SELECT stake_fund FROM calc),
                    'boost_fund', (SELECT boost_fund FROM calc),
                    'rank_percent', (SELECT rank FROM room_data),
                    'casino_cut', (SELECT casino_cut FROM calc),
                    'prize_pool', (SELECT prize_pool FROM calc),
                    'winner_payout_percent_applied', 100,
                    'payout_rule', 'stake_after_rake_plus_boosts'
                )
            WHERE EXISTS (SELECT 1 FROM upd_room) AND (SELECT winner_payout FROM calc) > 0
            RETURNING 1
        ),
        ledger_casino AS (
            INSERT INTO ledger_entries (room_id, user_id, account, entry_type, amount, meta)
            SELECT
                (SELECT id FROM upd_room),
                NULL,
                'casino',
                'casino_income',
                (SELECT (total_fund - winner_payout) FROM calc),
                jsonb_build_object(
                    'total_fund', (SELECT total_fund FROM calc),
                    'stake_fund', (SELECT stake_fund FROM calc),
                    'boost_fund', (SELECT boost_fund FROM calc),
                    'casino_cut', (SELECT casino_cut FROM calc),
                    'rank_percent', (SELECT rank FROM room_data),
                    'winner_payout_percent_applied', 100,
                    'winner_payout', (SELECT winner_payout FROM calc)
                )
            WHERE EXISTS (SELECT 1 FROM upd_room) AND (SELECT total_fund FROM calc) > 0
            RETURNING 1
        ),
        ledger_escrow AS (
            INSERT INTO ledger_entries (room_id, user_id, account, entry_type, amount, meta)
            SELECT
                (SELECT id FROM upd_room),
                NULL,
                'escrow',
                'escrow_out',
                -(SELECT total_fund FROM calc),
                jsonb_build_object(
                    'total_fund', (SELECT total_fund FROM calc),
                    'stake_fund', (SELECT stake_fund FROM calc),
                    'boost_fund', (SELECT boost_fund FROM calc),
                    'winner_payout', (SELECT winner_payout FROM calc),
                    'rank_percent', (SELECT rank FROM room_data),
                    'winner_payout_percent_applied', 100,
                    'casino_income', (SELECT (total_fund - winner_payout) FROM calc)
                )
            WHERE EXISTS (SELECT 1 FROM upd_room) AND (SELECT total_fund FROM calc) > 0
            RETURNING 1
        )
        SELECT
            (SELECT id FROM upd_room) AS id,
            (SELECT winner_id FROM upd_room) AS winner_id,
            (SELECT ended_at FROM upd_room) AS ended_at,
            (SELECT total_fund FROM calc) AS total_fund,
            (SELECT stake_fund FROM calc) AS stake_fund,
            (SELECT boost_fund FROM calc) AS boost_fund,
            (SELECT casino_cut FROM calc) AS casino_cut,
            (SELECT winner_payout FROM calc) AS winner_payout
    """, (
        int(room_id),
        int(room_id),
        int(room_id),
        int(room_id),
        int(room_id),
    ))
    return result


def shop_buy_slot(room_id: int, user_id: int) -> Dict[str, Any]:
    """
    Покупка 1 дополнительного слота в стадии shop.
    Ограничение: шанс пользователя (слоты + бусты) не должен стать > 50%.
    """
    result = execute_with_returning("""
        WITH user_locked AS (
            SELECT pg_advisory_xact_lock(%s, 2)
        ),
        locked AS (
            SELECT pg_advisory_xact_lock(%s, 1)
        ),
        room_data AS (
            SELECT r.status, rp.max_members_count, rp.join_cost
            FROM rooms r
            JOIN room_pattern rp ON rp.id = r.room_pattern_id
            WHERE r.id = %s
        ),
        existing_user AS (
            SELECT 1
            FROM room_members
            WHERE room_id = %s AND user_id = %s
            LIMIT 1
        ),
        counts AS (
            SELECT
                (SELECT COUNT(*)::int FROM room_members WHERE room_id = %s) AS members_count,
                (SELECT COALESCE(SUM(1 + COALESCE(boost, 0)), 0)::int FROM room_members WHERE room_id = %s) AS total_weight,
                (SELECT COALESCE(SUM(1 + COALESCE(boost, 0)), 0)::int FROM room_members WHERE room_id = %s AND user_id = %s) AS user_weight
        ),
        allowed AS (
            SELECT
                (rd.status = 'shop') AS ok_status,
                (EXISTS (SELECT 1 FROM existing_user)) AS ok_member,
                (c.members_count < rd.max_members_count) AS ok_capacity,
                ((c.user_weight + 1) * 2 <= (c.total_weight + GREATEST(0, rd.max_members_count - c.members_count))) AS ok_chance,
                rd.join_cost AS join_cost,
                rd.max_members_count AS max_members_count,
                c.members_count AS members_count,
                c.total_weight AS total_weight,
                c.user_weight AS user_weight
            FROM room_data rd, counts c
        ),
        pay AS (
            UPDATE users
            SET balance = balance - (SELECT join_cost FROM allowed)
            WHERE id = %s
              AND is_bot = FALSE
              AND balance >= (SELECT join_cost FROM allowed)
              AND (SELECT ok_status AND ok_member AND ok_capacity AND ok_chance FROM allowed)
            RETURNING id
        ),
        ins AS (
            INSERT INTO room_members (room_id, user_id, boost)
            SELECT %s, %s, 0
            WHERE EXISTS (SELECT 1 FROM pay)
            RETURNING id
        ),
        escrow_init AS (
            INSERT INTO room_escrow (room_id, amount)
            VALUES (%s, 0)
            ON CONFLICT (room_id) DO NOTHING
        ),
        escrow_upd AS (
            UPDATE room_escrow
            SET amount = amount + (SELECT join_cost FROM allowed),
                stake_amount = stake_amount + (SELECT join_cost FROM allowed),
                updated_at = NOW()
            WHERE room_id = %s AND EXISTS (SELECT 1 FROM ins)
            RETURNING amount
        ),
        ledger_user AS (
            INSERT INTO ledger_entries (room_id, user_id, account, entry_type, amount, meta)
            SELECT
                %s, %s, 'user', 'shop_buy_slot', -(SELECT join_cost FROM allowed),
                jsonb_build_object('slot_id', (SELECT id FROM ins), 'kind', 'slot')
            WHERE EXISTS (SELECT 1 FROM ins)
            RETURNING 1
        ),
        ledger_escrow AS (
            INSERT INTO ledger_entries (room_id, user_id, account, entry_type, amount, meta)
            SELECT
                %s, %s, 'escrow', 'shop_buy_slot', (SELECT join_cost FROM allowed),
                jsonb_build_object('slot_id', (SELECT id FROM ins), 'kind', 'slot')
            WHERE EXISTS (SELECT 1 FROM ins)
            RETURNING 1
        )
        SELECT
            (SELECT COUNT(*)::int FROM ins) AS inserted,
            (SELECT id FROM ins) AS slot_id,
            (SELECT ok_status FROM allowed) AS ok_status,
            (SELECT ok_member FROM allowed) AS ok_member,
            (SELECT ok_capacity FROM allowed) AS ok_capacity,
            (SELECT ok_chance FROM allowed) AS ok_chance,
            (SELECT max_members_count FROM allowed) AS max_members_count,
            ((SELECT members_count FROM allowed) + (SELECT COUNT(*)::int FROM ins)) AS members_count_after,
            ((SELECT max_members_count FROM allowed) - ((SELECT members_count FROM allowed) + (SELECT COUNT(*)::int FROM ins))) AS free_slots_after,
            ((SELECT user_weight FROM allowed) + (SELECT COUNT(*)::int FROM ins)) AS user_weight_after,
            ((SELECT total_weight FROM allowed) + (SELECT COUNT(*)::int FROM ins)) AS total_weight_after,
            (SELECT amount FROM escrow_upd) AS escrow_amount_after
        FROM allowed
    """, (
        int(user_id),
        int(room_id),
        int(room_id),
        int(room_id),
        int(user_id),
        int(room_id),
        int(room_id),
        int(room_id),
        int(user_id),
        int(user_id),
        int(room_id),
        int(user_id),
        int(room_id),
        int(room_id),
        int(room_id),
        int(user_id),
        int(room_id),
        int(user_id),
    ))

    if not result:
        return {"success": False, "message": "Room not found"}

    inserted = bool(result.get("inserted"))
    ok_status = bool(result.get("ok_status"))
    ok_member = bool(result.get("ok_member"))
    ok_capacity = bool(result.get("ok_capacity"))
    ok_chance = bool(result.get("ok_chance"))

    if inserted:
        return {"success": True, **result}

    if not ok_status:
        return {"success": False, "message": "Shop is not available now", **result}
    if not ok_member:
        return {"success": False, "message": "User is not in this room", **result}
    if not ok_capacity:
        return {"success": False, "message": "No free slots", **result}
    if not ok_chance:
        return {"success": False, "message": "Chance cannot exceed 50%", **result}
    return {"success": False, "message": "Not enough balance", **result}


def shop_buy_boost(room_id: int, user_id: int, slot_id: int, boost_value: int) -> Dict[str, Any]:
    """
    Покупка буста на один слот (room_members.id) в стадии shop.
    Ограничение: шанс пользователя (слоты + бусты) не должен стать > 50%.
    """
    result = execute_with_returning("""
        WITH locked AS (
            SELECT pg_advisory_xact_lock(%s, 1)
        ),
        room_data AS (
            SELECT r.status, rp.boost_cost_per_point, rp.max_members_count
            FROM rooms r
            JOIN room_pattern rp ON rp.id = r.room_pattern_id
            WHERE r.id = %s
        ),
        slot AS (
            SELECT rm.id, rm.user_id, rm.boost
            FROM room_members rm
            WHERE rm.id = %s AND rm.room_id = %s
        ),
        weights AS (
            SELECT
                (SELECT COALESCE(SUM(1 + COALESCE(boost, 0)), 0)::int FROM room_members WHERE room_id = %s) AS total_weight,
                (SELECT COUNT(*)::int FROM room_members WHERE room_id = %s) AS members_count,
                (SELECT COALESCE(SUM(1 + COALESCE(boost, 0)), 0)::int FROM room_members WHERE room_id = %s AND user_id = %s) AS user_weight
        ),
        allowed AS (
            SELECT
                (SELECT status = 'shop' FROM room_data) AS ok_status,
                (SELECT COUNT(*) = 1 FROM slot WHERE user_id = %s) AS ok_owner,
                (SELECT boost = 0 FROM slot) AS ok_unboosted,
                ((w.user_weight + %s) * 2 <= ((w.total_weight + GREATEST(0, (SELECT max_members_count FROM room_data) - w.members_count)) + %s)) AS ok_chance,
                ((SELECT boost_cost_per_point FROM room_data) * %s)::bigint AS boost_cost,
                w.total_weight AS total_weight,
                w.user_weight AS user_weight
            FROM weights w
        ),
        pay AS (
            UPDATE users
            SET balance = balance - (SELECT boost_cost FROM allowed)
            WHERE id = %s
              AND is_bot = FALSE
              AND balance >= (SELECT boost_cost FROM allowed)
              AND (SELECT ok_status AND ok_owner AND ok_unboosted AND ok_chance FROM allowed)
            RETURNING id
        ),
        upd AS (
            UPDATE room_members
            SET boost = %s
            WHERE id = %s
              AND room_id = %s
              AND user_id = %s
              AND boost = 0
              AND EXISTS (SELECT 1 FROM pay)
            RETURNING id
        ),
        escrow_init AS (
            INSERT INTO room_escrow (room_id, amount)
            VALUES (%s, 0)
            ON CONFLICT (room_id) DO NOTHING
        ),
        escrow_upd AS (
            UPDATE room_escrow
            SET amount = amount + (SELECT boost_cost FROM allowed),
                boost_amount = boost_amount + (SELECT boost_cost FROM allowed),
                updated_at = NOW()
            WHERE room_id = %s AND EXISTS (SELECT 1 FROM upd)
            RETURNING amount
        ),
        ledger_user AS (
            INSERT INTO ledger_entries (room_id, user_id, account, entry_type, amount, meta)
            SELECT
                %s, %s, 'user', 'shop_buy_boost', -(SELECT boost_cost FROM allowed),
                jsonb_build_object('slot_id', %s, 'boost', %s, 'kind', 'boost')
            WHERE EXISTS (SELECT 1 FROM upd)
            RETURNING 1
        ),
        ledger_escrow AS (
            INSERT INTO ledger_entries (room_id, user_id, account, entry_type, amount, meta)
            SELECT
                %s, %s, 'escrow', 'shop_buy_boost', (SELECT boost_cost FROM allowed),
                jsonb_build_object('slot_id', %s, 'boost', %s, 'kind', 'boost')
            WHERE EXISTS (SELECT 1 FROM upd)
            RETURNING 1
        )
        SELECT
            (SELECT COUNT(*)::int FROM upd) AS updated,
            (SELECT ok_status FROM allowed) AS ok_status,
            (SELECT ok_owner FROM allowed) AS ok_owner,
            (SELECT ok_unboosted FROM allowed) AS ok_unboosted,
            (SELECT ok_chance FROM allowed) AS ok_chance,
            ((SELECT user_weight FROM allowed) + %s) AS user_weight_after,
            ((SELECT total_weight FROM allowed) + %s) AS total_weight_after,
            (SELECT amount FROM escrow_upd) AS escrow_amount_after,
            (SELECT boost_cost FROM allowed) AS boost_cost
        FROM allowed
    """, (
        int(room_id),
        int(room_id),
        int(slot_id),
        int(room_id),
        int(room_id),
        int(room_id),
        int(room_id),
        int(user_id),
        int(user_id),
        int(boost_value),
        int(boost_value),
        int(boost_value),
        int(user_id),
        int(boost_value),
        int(slot_id),
        int(room_id),
        int(user_id),
        int(room_id),
        int(room_id),
        int(room_id),
        int(user_id),
        int(slot_id),
        int(boost_value),
        int(room_id),
        int(user_id),
        int(slot_id),
        int(boost_value),
        int(boost_value),
        int(boost_value),
    ))

    if not result:
        return {"success": False, "message": "Room not found"}

    updated = bool(result.get("updated"))
    ok_status = bool(result.get("ok_status"))
    ok_owner = bool(result.get("ok_owner"))
    ok_unboosted = bool(result.get("ok_unboosted"))
    ok_chance = bool(result.get("ok_chance"))

    if updated:
        return {"success": True, **result}

    if not ok_status:
        return {"success": False, "message": "Shop is not available now", **result}
    if not ok_owner:
        return {"success": False, "message": "Slot not found", **result}
    if not ok_unboosted:
        return {"success": False, "message": "Boost already purchased for this slot", **result}
    if not ok_chance:
        return {"success": False, "message": "Chance cannot exceed 50%", **result}
    return {"success": False, "message": "Not enough balance", **result}


def get_all_rooms(limit=100):
    return fetch_all("""
        SELECT r.*, rp.game, rp.join_cost
        (SELECT COUNT(*) FROM room_members WHERE room_id = r.id) as members_count
        FROM rooms r
        JOIN room_pattern rp ON rp.id = r.room_pattern_id
        WHERE r.status IN ('waiting', 'lobby', 'shop', 'running')
        ORDER BY r.created_at DESC
        LIMIT %s
    """, (limit,))


def get_room_by_pattern(pattern_id: int) -> Optional[Dict]:
    """
    Возвращает комнату со статусом 'lobby', имеющую хотя бы 1 свободный слот.
    """
    rooms = fetch_all("""
        SELECT r.*, rp.game, rp.join_cost, rp.max_members_count
        FROM rooms r
        JOIN room_pattern rp ON rp.id = r.room_pattern_id
        WHERE r.room_pattern_id = %s
        AND r.status IN ('lobby', 'waiting')
        ORDER BY r.created_at ASC
    """, (pattern_id,))

    for room in rooms:
        occupied = fetch_one("""
            SELECT COUNT(*) as cnt
            FROM room_members
            WHERE room_id = %s
        """, (room['id'],))['cnt']

        if room['max_members_count'] - occupied >= 1:
            return room
    return None


# =========================================================
# 🔍 GET MEMBERS
# =========================================================

def get_room_members(room_id: int):
     return fetch_all("""
         SELECT rm.id, rm.user_id, rm.boost, u.is_bot
         FROM room_members rm
         JOIN users u ON u.id = rm.user_id
         WHERE rm.room_id = %s
    """, (room_id,))


def get_user_slots_in_room(room_id: int, user_id: int) -> List[Dict]:
    """Возвращает все слоты пользователя в комнате с их бустами."""
    return fetch_all("""
        SELECT id, boost
        FROM room_members
        WHERE room_id = %s AND user_id = %s
    """, (room_id, user_id))

# =========================================================
# ➕ CREATE ROOM
# =========================================================

def create_room(pattern_id: int) -> Dict:
    """Создаёт новую комнату (waiting), но уважает лимиты system_config.max_active_rooms и room_pattern.max_rooms_count."""
    token = generate_access_token()
    row = execute_with_returning("""
        WITH locked AS (
            SELECT pg_advisory_xact_lock(1, 3)
        ),
        cfg AS (
            SELECT COALESCE(max_active_rooms, 50)::int AS max_active_rooms
            FROM system_config
            WHERE id = 1
            FOR UPDATE
        ),
        cfg_row AS (
            SELECT max_active_rooms
            FROM cfg
            UNION ALL
            SELECT 50::int AS max_active_rooms
            WHERE NOT EXISTS (SELECT 1 FROM cfg)
        ),
        pat AS (
            SELECT
                rp.max_rooms_count::int AS max_rooms_count,
                rp.game,
                rp.join_cost,
                rp.max_members_count
            FROM room_pattern rp
            WHERE rp.id = %s
            FOR UPDATE
        ),
        active_all AS (
            SELECT COUNT(*)::int AS active_rooms_before
            FROM rooms
            WHERE status IN ('waiting', 'lobby', 'shop', 'running')
        ),
        active_pat AS (
            SELECT COUNT(*)::int AS active_pattern_rooms_before
            FROM rooms
            WHERE room_pattern_id = %s
              AND status IN ('waiting', 'lobby', 'shop', 'running')
        ),
        ins AS (
            INSERT INTO rooms (room_pattern_id, access_token, status)
            SELECT %s, %s, 'waiting'
            WHERE (SELECT active_rooms_before FROM active_all) < (SELECT max_active_rooms FROM cfg_row)
              AND (SELECT active_pattern_rooms_before FROM active_pat) < (SELECT max_rooms_count FROM pat)
            RETURNING *
        )
        SELECT
            (SELECT id FROM ins) AS id,
            (SELECT room_pattern_id FROM ins) AS room_pattern_id,
            (SELECT created_at FROM ins) AS created_at,
            (SELECT started_at FROM ins) AS started_at,
            (SELECT ended_at FROM ins) AS ended_at,
            (SELECT status FROM ins) AS status,
            (SELECT winner_id FROM ins) AS winner_id,
            (SELECT access_token FROM ins) AS access_token,
            (SELECT game FROM pat) AS game,
            (SELECT join_cost FROM pat) AS join_cost,
            (SELECT max_members_count FROM pat) AS max_members_count,
            (SELECT active_rooms_before FROM active_all) AS active_rooms_before,
            (SELECT max_active_rooms FROM cfg_row) AS max_active_rooms,
            (SELECT active_pattern_rooms_before FROM active_pat) AS active_pattern_rooms_before,
            (SELECT max_rooms_count FROM pat) AS max_rooms_count
    """, (int(pattern_id), int(pattern_id), int(pattern_id), token))

    if not row:
        return {"success": False, "message": "Pattern not found"}

    if not row.get("id"):
        if int(row.get("active_rooms_before") or 0) >= int(row.get("max_active_rooms") or 0):
            return {"success": False, "message": "Rooms limit reached", **row}
        if int(row.get("active_pattern_rooms_before") or 0) >= int(row.get("max_rooms_count") or 0):
            return {"success": False, "message": "Pattern rooms limit reached", **row}
        return {"success": False, "message": "Room not created", **row}

    room = {
        "id": row["id"],
        "room_pattern_id": row["room_pattern_id"],
        "created_at": row["created_at"],
        "started_at": row["started_at"],
        "ended_at": row["ended_at"],
        "status": row["status"],
        "winner_id": row["winner_id"],
        "access_token": row["access_token"],
        "game": row.get("game"),
        "join_cost": row.get("join_cost"),
        "max_members_count": row.get("max_members_count"),
    }
    return {"success": True, "room": room}






#ДОБАВИЛ СТАРТ ЛОББИ
def start_lobby(room_id: int):
    """
    Перевод комнаты из waiting → lobby
    и фиксирует старт времени.
    """
    fetch_one("""
        UPDATE rooms
        SET status = 'lobby',
            started_at = NOW()
        WHERE id = %s
          AND status = 'waiting'
    """, (room_id,))



def join_room(room_id: int, user_id: int) -> Dict:
    """
    Добавляет пользователя в комнату, занимает 1 слот, boost = 0.
    Возвращает: success, first_player, delay_seconds (если первый), room_id.
    """
    room = fetch_one("""
        SELECT * 
        FROM rooms 
        WHERE id = %s FOR UPDATE
    """, (room_id,))

    if not room:
        return {"success": False, "message": "Room not found"}

    if room['status'] != 'lobby':
        return {"success": False, "message": "Room is not joinable now"}

    pattern = fetch_one("""
        SELECT * 
        FROM room_pattern 
        WHERE id = %s
    """, (room['room_pattern_id'],))

    if not pattern:
        return {"success": False, "message": "Pattern not found"}

    current_slots = fetch_one("""
        SELECT COUNT(*) as cnt 
        FROM room_members 
        WHERE room_id = %s
    """, (room_id,))['cnt']

    if current_slots + 1 > pattern['max_members_count']:
        return {"success": False, "message": "No free slots"}

    user = fetch_one("""
        SELECT is_bot 
        FROM users 
        WHERE id = %s
    """, (user_id,))

    if not user or user['is_bot']:
        return {"success": False, "message": "Invalid user"}

    total_cost = pattern['join_cost']
    updated = fetch_one("""
        UPDATE users 
        SET balance = balance - %s
        WHERE id = %s AND balance >= %s
        RETURNING id
    """, (total_cost, user_id, total_cost))

    if not updated:
        return {"success": False, "message": "Not enough balance"}

    fetch_one("""
        INSERT INTO room_members (room_id, user_id, boost)
        VALUES (%s, %s, 0)
    """, (room_id, user_id))

    is_first = (current_slots == 0)

    #ДОБАВИЛ СТАРТ ЛОББИ
    # 9. 🔥 СТАРТ LOBBY ТУТ
    if is_first:
        start_lobby(room_id)


    return {
        "success": True,
        "first_player": is_first,
        "delay_seconds": pattern['waiting_lobby_stage'] if is_first else 0,
        "room_id": room_id
    }
