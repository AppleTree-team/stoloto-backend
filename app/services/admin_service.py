from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.db.db import execute, execute_with_returning, fetch_all, fetch_one
from app.services.user_service import get_user_game_history, get_user_current_game


def get_system_config() -> Dict[str, Any]:
    execute("INSERT INTO system_config (id) VALUES (1) ON CONFLICT (id) DO NOTHING")
    row = fetch_one(
        """
        SELECT
            id,
            max_active_rooms,
            casino_balance,
            COALESCE(bots_enabled, TRUE) AS bots_enabled,
            COALESCE(min_join_cost, 0)::bigint AS min_join_cost,
            COALESCE(max_join_cost, 1000000000)::bigint AS max_join_cost
        FROM system_config
        WHERE id = 1
        """
    )
    return row or {
        "id": 1,
        "max_active_rooms": 50,
        "casino_balance": 0,
        "bots_enabled": True,
        "min_join_cost": 0,
        "max_join_cost": 1000000000,
    }


def update_system_config(
    *,
    max_active_rooms: Optional[int] = None,
    casino_balance: Optional[int] = None,
    bots_enabled: Optional[bool] = None,
    min_join_cost: Optional[int] = None,
    max_join_cost: Optional[int] = None,
) -> Dict[str, Any]:
    if max_active_rooms is not None and int(max_active_rooms) < 0:
        return {"success": False, "message": "max_active_rooms must be >= 0"}
    if casino_balance is not None and int(casino_balance) < 0:
        return {"success": False, "message": "casino_balance must be >= 0"}
    if min_join_cost is not None and int(min_join_cost) < 0:
        return {"success": False, "message": "min_join_cost must be >= 0"}
    if max_join_cost is not None and int(max_join_cost) < 0:
        return {"success": False, "message": "max_join_cost must be >= 0"}
    if (min_join_cost is not None and max_join_cost is not None) and int(min_join_cost) > int(max_join_cost):
        return {"success": False, "message": "min_join_cost must be <= max_join_cost"}

    row = execute_with_returning(
        """
        WITH ensure AS (
            INSERT INTO system_config (id) VALUES (1)
            ON CONFLICT (id) DO NOTHING
            RETURNING 1
        ),
        upd AS (
            UPDATE system_config
            SET
                max_active_rooms = COALESCE(%s, max_active_rooms),
                casino_balance   = COALESCE(%s, casino_balance),
                bots_enabled     = COALESCE(%s, bots_enabled),
                min_join_cost    = COALESCE(%s, min_join_cost),
                max_join_cost    = COALESCE(%s, max_join_cost)
            WHERE id = 1
            RETURNING *
        )
        SELECT * FROM upd
        """,
        (
            None if max_active_rooms is None else int(max_active_rooms),
            None if casino_balance is None else int(casino_balance),
            bots_enabled,
            None if min_join_cost is None else int(min_join_cost),
            None if max_join_cost is None else int(max_join_cost),
        ),
    )
    if not row:
        return {"success": False, "message": "Config not updated"}
    return {"success": True, "config": row}


def search_users(query: str, limit: int = 50) -> List[Dict[str, Any]]:
    q = (query or "").strip()
    if not q:
        return []
    if q.isdigit():
        row = fetch_one(
            """
            SELECT id, username, balance, created_at, is_bot, is_admin
            FROM users
            WHERE id = %s
            """,
            (int(q),),
        )
        return [row] if row else []
    return fetch_all(
        """
        SELECT id, username, balance, created_at, is_bot, is_admin
        FROM users
        WHERE username ILIKE %s
        ORDER BY id DESC
        LIMIT %s
        """,
        (f"%{q}%", int(limit)),
    )


def get_room_by_id_admin(room_id: int) -> Optional[Dict[str, Any]]:
    return fetch_one(
        """
        SELECT
            r.*,
            rp.game,
            rp.join_cost,
            rp.max_members_count,
            rp.rank,
            rp.boost_cost_per_point
        FROM rooms r
        JOIN room_pattern rp ON rp.id = r.room_pattern_id
        WHERE r.id = %s
        """,
        (int(room_id),),
    )


def get_room_by_token_admin(access_token: str) -> Optional[Dict[str, Any]]:
    return fetch_one(
        """
        SELECT
            r.*,
            rp.game,
            rp.join_cost,
            rp.max_members_count,
            rp.rank,
            rp.boost_cost_per_point
        FROM rooms r
        JOIN room_pattern rp ON rp.id = r.room_pattern_id
        WHERE r.access_token = %s
        """,
        (access_token,),
    )


def list_rooms(
    *,
    status: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    where = ""
    params: List[Any] = []
    if status:
        where = "WHERE r.status = %s"
        params.append(status)
    params.extend([int(limit), int(offset)])
    return fetch_all(
        f"""
        SELECT
            r.id,
            r.room_pattern_id,
            r.created_at,
            r.started_at,
            r.ended_at,
            r.status,
            r.winner_id,
            r.access_token,
            rp.game,
            rp.join_cost,
            rp.max_members_count,
            rp.rank,
            rp.boost_cost_per_point,
            COALESCE(w.username, NULL) AS winner_username,
            (SELECT COUNT(*)::int FROM room_members rm WHERE rm.room_id = r.id) AS slots_count,
            (SELECT COALESCE(SUM(COALESCE(rm.boost, 0)), 0)::int FROM room_members rm WHERE rm.room_id = r.id) AS total_boost_points
        FROM rooms r
        JOIN room_pattern rp ON rp.id = r.room_pattern_id
        LEFT JOIN users w ON w.id = r.winner_id
        {where}
        ORDER BY COALESCE(r.ended_at, r.created_at) DESC, r.id DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params),
    )


def list_finished_rooms(*, days: int = 30, limit: int = 50, offset: int = 0) -> List[Dict[str, Any]]:
    return fetch_all(
        """
        SELECT
            r.id,
            r.created_at,
            r.started_at,
            r.ended_at,
            r.status,
            r.winner_id,
            r.access_token,
            rp.game,
            rp.join_cost,
            rp.rank,
            rp.max_members_count,
            rp.boost_cost_per_point,
            COALESCE(w.username, NULL) AS winner_username,
            (SELECT COUNT(*)::int FROM room_members rm WHERE rm.room_id = r.id) AS slots_count,
            (SELECT COALESCE(SUM(COALESCE(rm.boost, 0)), 0)::int FROM room_members rm WHERE rm.room_id = r.id) AS total_boost_points
        FROM rooms r
        JOIN room_pattern rp ON rp.id = r.room_pattern_id
        LEFT JOIN users w ON w.id = r.winner_id
        WHERE r.status = 'finished'
          AND COALESCE(r.ended_at, r.created_at) >= NOW() - (%s * INTERVAL '1 day')
        ORDER BY COALESCE(r.ended_at, r.created_at) DESC, r.id DESC
        LIMIT %s OFFSET %s
        """,
        (int(days), int(limit), int(offset)),
    )


def get_user_history_admin(user_id: int, limit: int = 50) -> List[Dict[str, Any]]:
    return get_user_game_history(int(user_id), limit=int(limit))


def get_user_current_game_admin(user_id: int) -> Optional[Dict[str, Any]]:
    return get_user_current_game(int(user_id))


def get_room_card(room_id: int, ledger_limit: int = 200) -> Optional[Dict[str, Any]]:
    room = get_room_by_id_admin(room_id)
    if not room:
        return None

    members = fetch_all(
        """
        SELECT
            rm.id AS slot_id,
            rm.user_id,
            u.username,
            u.is_bot,
            rm.boost,
            rm.joined_at
        FROM room_members rm
        JOIN users u ON u.id = rm.user_id
        WHERE rm.room_id = %s
        ORDER BY rm.id ASC
        """,
        (int(room_id),),
    )

    escrow = fetch_one(
        """
        SELECT room_id, amount, stake_amount, boost_amount, updated_at
        FROM room_escrow
        WHERE room_id = %s
        """,
        (int(room_id),),
    )

    ledger = fetch_all(
        """
        SELECT id, created_at, room_id, user_id, account, entry_type, amount, meta
        FROM ledger_entries
        WHERE room_id = %s
        ORDER BY id DESC
        LIMIT %s
        """,
        (int(room_id), int(ledger_limit)),
    )

    slots_count = len(members)
    stake_fund = int(slots_count) * int(room.get("join_cost") or 0)
    total_boost_points = sum(int(m.get("boost") or 0) for m in members)
    boost_fund = total_boost_points * int(room.get("boost_cost_per_point") or 0)
    total_fund = stake_fund + boost_fund

    return {
        "room": room,
        "members": members,
        "escrow": escrow,
        "funds": {
            "slots_count": slots_count,
            "stake_fund": stake_fund,
            "boost_points": total_boost_points,
            "boost_fund": boost_fund,
            "total_fund": total_fund,
        },
        "ledger": ledger,
    }


def force_finish_running_room(room_id: int) -> Dict[str, Any]:
    from app.services.room_service import finish_game_and_pick_winner_if_running

    res = finish_game_and_pick_winner_if_running(int(room_id))
    if not res:
        return {"success": False, "message": "Room not finished"}
    return {"success": True, "result": res}


def force_refund_room(*, admin_user_id: int, room_id: int, reason: str) -> Dict[str, Any]:
    if not reason or not str(reason).strip():
        return {"success": False, "message": "reason is required"}

    result = execute_with_returning(
        """
        WITH locked AS (
            SELECT pg_advisory_xact_lock(%s, 1)
        ),
        room_data AS (
            SELECT r.id, r.status, rp.join_cost, rp.boost_cost_per_point
            FROM rooms r
            JOIN room_pattern rp ON rp.id = r.room_pattern_id
            WHERE r.id = %s
            FOR UPDATE
        ),
        members AS (
            SELECT rm.user_id, COUNT(*)::int AS slots_count, COALESCE(SUM(COALESCE(rm.boost, 0)), 0)::int AS boost_points
            FROM room_members rm
            WHERE rm.room_id = %s
            GROUP BY rm.user_id
        ),
        refunds AS (
            SELECT
                m.user_id,
                (m.slots_count::bigint * rd.join_cost::bigint + m.boost_points::bigint * rd.boost_cost_per_point::bigint)::bigint AS refund_amount
            FROM members m
            JOIN room_data rd ON rd.id = %s
        ),
        totals AS (
            SELECT COALESCE(SUM(refund_amount), 0)::bigint AS total_refund
            FROM refunds
        ),
        upd_room AS (
            UPDATE rooms
            SET status = 'finished',
                winner_id = NULL,
                ended_at = NOW()
            WHERE id = %s
              AND status IN ('waiting', 'lobby', 'shop', 'running')
            RETURNING id, status, ended_at
        ),
        upd_users AS (
            UPDATE users u
            SET balance = balance + r.refund_amount
            FROM refunds r
            WHERE u.id = r.user_id
              AND EXISTS (SELECT 1 FROM upd_room)
            RETURNING u.id
        ),
        escrow_init AS (
            INSERT INTO room_escrow (room_id, amount)
            VALUES (%s, 0)
            ON CONFLICT (room_id) DO NOTHING
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
        ledger_users AS (
            INSERT INTO ledger_entries (room_id, user_id, account, entry_type, amount, meta)
            SELECT
                %s,
                r.user_id,
                'user',
                'admin_refund',
                r.refund_amount,
                jsonb_build_object('reason', %s, 'admin_user_id', %s)
            FROM refunds r
            WHERE EXISTS (SELECT 1 FROM upd_room) AND r.refund_amount > 0
            RETURNING 1
        ),
        ledger_escrow AS (
            INSERT INTO ledger_entries (room_id, user_id, account, entry_type, amount, meta)
            SELECT
                %s,
                NULL,
                'escrow',
                'admin_refund',
                -(SELECT total_refund FROM totals),
                jsonb_build_object('reason', %s, 'admin_user_id', %s)
            WHERE EXISTS (SELECT 1 FROM upd_room) AND (SELECT total_refund FROM totals) > 0
            RETURNING 1
        )
        SELECT
            (SELECT id FROM room_data) AS room_id,
            (SELECT status FROM room_data) AS status_before,
            (SELECT id FROM upd_room) AS finished_room_id,
            (SELECT ended_at FROM upd_room) AS ended_at,
            (SELECT total_refund FROM totals) AS total_refund
        """,
        (
            int(room_id),
            int(room_id),
            int(room_id),
            int(room_id),
            int(room_id),
            int(room_id),
            int(room_id),
            int(room_id),
            int(room_id),
            str(reason),
            int(admin_user_id),
            int(room_id),
            str(reason),
            int(admin_user_id),
        ),
    )

    if not result or not result.get("room_id"):
        return {"success": False, "message": "Room not found"}
    if not result.get("finished_room_id"):
        return {"success": False, "message": "Room is not active (already finished?)"}

    return {"success": True, **result}


def list_ledger(
    *,
    room_id: Optional[int] = None,
    user_id: Optional[int] = None,
    account: Optional[str] = None,
    entry_type: Optional[str] = None,
    date_from: Optional[datetime] = None,
    date_to: Optional[datetime] = None,
    limit: int = 200,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    where: List[str] = []
    params: List[Any] = []

    if room_id is not None:
        where.append("room_id = %s")
        params.append(int(room_id))
    if user_id is not None:
        where.append("user_id = %s")
        params.append(int(user_id))
    if account is not None:
        where.append("account = %s")
        params.append(account)
    if entry_type is not None:
        where.append("entry_type = %s")
        params.append(entry_type)
    if date_from is not None:
        where.append("created_at >= %s")
        params.append(date_from)
    if date_to is not None:
        where.append("created_at <= %s")
        params.append(date_to)

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    params.extend([int(limit), int(offset)])

    return fetch_all(
        f"""
        SELECT id, created_at, room_id, user_id, account, entry_type, amount, meta
        FROM ledger_entries
        {where_sql}
        ORDER BY id DESC
        LIMIT %s OFFSET %s
        """,
        tuple(params),
    )


def export_ledger_csv(rows: List[Dict[str, Any]]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["id", "created_at", "room_id", "user_id", "account", "entry_type", "amount", "meta"])
    for r in rows:
        writer.writerow(
            [
                r.get("id"),
                r.get("created_at"),
                r.get("room_id"),
                r.get("user_id"),
                r.get("account"),
                r.get("entry_type"),
                r.get("amount"),
                r.get("meta"),
            ]
        )
    return buf.getvalue()


def adjust_user_balance(
    *,
    admin_user_id: int,
    user_id: int,
    amount: int,
    reason: str,
    room_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Админская корректировка баланса:
      - amount > 0: начислить пользователю (списать у казино)
      - amount < 0: списать у пользователя (зачислить казино)
    """
    if amount == 0:
        return {"success": False, "message": "amount must be non-zero"}
    if not reason or not str(reason).strip():
        return {"success": False, "message": "reason is required"}

    result = execute_with_returning(
        """
        WITH locked_user AS (
            SELECT pg_advisory_xact_lock(%s, 2)
        ),
        locked_cfg AS (
            SELECT pg_advisory_xact_lock(1, 6)
        ),
        cfg AS (
            SELECT casino_balance::bigint AS casino_balance
            FROM system_config
            WHERE id = 1
            FOR UPDATE
        ),
        cfg_row AS (
            SELECT casino_balance FROM cfg
            UNION ALL
            SELECT 0::bigint AS casino_balance
            WHERE NOT EXISTS (SELECT 1 FROM cfg)
        ),
        upd_user AS (
            UPDATE users
            SET balance = balance + %s
            WHERE id = %s
              AND (balance + %s) >= 0
            RETURNING id, balance
        ),
        upd_casino AS (
            UPDATE system_config
            SET casino_balance = casino_balance - %s
            WHERE id = 1
              AND EXISTS (SELECT 1 FROM upd_user)
              AND ((SELECT casino_balance FROM cfg_row) - %s) >= 0
            RETURNING casino_balance
        ),
        ok AS (
            SELECT
                (SELECT COUNT(*) FROM upd_user) = 1 AS ok_user,
                (SELECT COUNT(*) FROM upd_casino) = 1 AS ok_casino
        ),
        ledger_user AS (
            INSERT INTO ledger_entries (room_id, user_id, account, entry_type, amount, meta)
            SELECT
                %s,
                %s,
                'user',
                'admin_adjust',
                %s,
                jsonb_build_object('reason', %s, 'admin_user_id', %s)
            WHERE (SELECT ok_user AND ok_casino FROM ok)
            RETURNING 1
        ),
        ledger_casino AS (
            INSERT INTO ledger_entries (room_id, user_id, account, entry_type, amount, meta)
            SELECT
                %s,
                NULL,
                'casino',
                'admin_adjust',
                -(%s),
                jsonb_build_object('reason', %s, 'admin_user_id', %s, 'target_user_id', %s)
            WHERE (SELECT ok_user AND ok_casino FROM ok)
            RETURNING 1
        )
        SELECT
            (SELECT ok_user FROM ok) AS ok_user,
            (SELECT ok_casino FROM ok) AS ok_casino,
            (SELECT balance FROM upd_user) AS user_balance_after,
            (SELECT casino_balance FROM upd_casino) AS casino_balance_after
        """,
        (
            int(user_id),
            int(amount),
            int(user_id),
            int(amount),
            int(amount),
            int(amount),
            int(room_id) if room_id is not None else None,
            int(user_id),
            int(amount),
            str(reason),
            int(admin_user_id),
            int(room_id) if room_id is not None else None,
            int(amount),
            str(reason),
            int(admin_user_id),
            int(user_id),
        ),
    )

    if not result:
        return {"success": False, "message": "Adjustment failed"}

    if not bool(result.get("ok_user")):
        return {"success": False, "message": "User not found or insufficient balance"}
    if not bool(result.get("ok_casino")):
        return {"success": False, "message": "Casino has insufficient balance for this adjustment"}

    return {"success": True, **result}


def get_anomalies(days: int = 7) -> Dict[str, Any]:
    return {
        "rooms_running_without_members": fetch_all(
            """
            SELECT r.id, r.access_token, r.started_at
            FROM rooms r
            WHERE r.status = 'running'
              AND NOT EXISTS (SELECT 1 FROM room_members rm WHERE rm.room_id = r.id)
            ORDER BY r.id DESC
            LIMIT 100
            """
        ),
        "rooms_shop_without_members": fetch_all(
            """
            SELECT r.id, r.access_token, r.started_at
            FROM rooms r
            WHERE r.status = 'shop'
              AND NOT EXISTS (SELECT 1 FROM room_members rm WHERE rm.room_id = r.id)
            ORDER BY r.id DESC
            LIMIT 100
            """
        ),
        "casino_income_last_days": fetch_one(
            """
            SELECT COALESCE(SUM(amount), 0)::bigint AS amount
            FROM ledger_entries
            WHERE account = 'casino'
              AND entry_type = 'casino_income'
              AND created_at >= NOW() - (%s * INTERVAL '1 day')
            """,
            (int(days),),
        )
        or {"amount": 0},
    }


def reconcile_casino_balance() -> Dict[str, Any]:
    cfg = get_system_config()
    ledger_sum = fetch_one(
        """
        SELECT COALESCE(SUM(amount), 0)::bigint AS amount
        FROM ledger_entries
        WHERE account = 'casino'
        """
    ) or {"amount": 0}
    income_sum = fetch_one(
        """
        SELECT COALESCE(SUM(amount), 0)::bigint AS amount
        FROM ledger_entries
        WHERE account = 'casino' AND entry_type = 'casino_income'
        """
    ) or {"amount": 0}
    bot_sum = fetch_one(
        """
        SELECT COALESCE(SUM(amount), 0)::bigint AS amount
        FROM ledger_entries
        WHERE account = 'casino' AND entry_type = 'bot_slots'
        """
    ) or {"amount": 0}

    casino_balance = int(cfg.get("casino_balance") or 0)
    ledger_total = int(ledger_sum.get("amount") or 0)
    return {
        "casino_balance": casino_balance,
        "ledger_total_casino": ledger_total,
        "ledger_income_casino": int(income_sum.get("amount") or 0),
        "ledger_bot_slots_casino": int(bot_sum.get("amount") or 0),
        "diff_balance_minus_ledger": casino_balance - ledger_total,
    }
