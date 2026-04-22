import asyncio
import logging
import secrets
from typing import Optional

from app.services.redis_service import get_redis, close_redis
from app.services.room_service import (
    get_lobby_rooms_ready_for_shop,
    get_shop_rooms_due,
    finish_lobby_to_shop_if_lobby,
    start_game_if_shop,
    finish_game_and_pick_winner_if_running,
)


_LOCK_KEY = "stoloto:stage_manager:lock"
_LOCK_TTL_MS = 15_000


_REFRESH_LUA = """
if redis.call("GET", KEYS[1]) == ARGV[1] then
  return redis.call("PEXPIRE", KEYS[1], ARGV[2])
end
return 0
"""


logger = logging.getLogger(__name__)


class StageManager:
    def __init__(self) -> None:
        self._task: Optional[asyncio.Task] = None
        self._stop = asyncio.Event()
        self._instance_id = secrets.token_hex(12)

    async def start(self) -> None:
        if self._task is not None:
            return
        self._stop.clear()
        self._task = asyncio.create_task(self._run(), name="stage-manager")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop.set()
        try:
            await asyncio.wait_for(self._task, timeout=5)
        except Exception:
            self._task.cancel()
            try:
                await self._task
            except Exception:
                pass
        finally:
            self._task = None
            await close_redis()

    async def _run(self) -> None:
        client = get_redis()
        if client is None:
            # Redis not configured — manager won't run.
            return

        while not self._stop.is_set():
            try:
                acquired = await client.set(
                    _LOCK_KEY,
                    self._instance_id,
                    nx=True,
                    px=_LOCK_TTL_MS,
                )
                if not acquired:
                    await asyncio.sleep(1)
                    continue

                await asyncio.to_thread(self._tick_sync)
                await client.eval(_REFRESH_LUA, 1, _LOCK_KEY, self._instance_id, str(_LOCK_TTL_MS))
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Stage manager tick failed")
                await asyncio.sleep(1)

    def _tick_sync(self) -> None:
        lobby_rooms = get_lobby_rooms_ready_for_shop(limit=200)
        for room in lobby_rooms:
            finish_lobby_to_shop_if_lobby(room["id"], room["waiting_shop_stage"])

        shop_rooms = get_shop_rooms_due(limit=200)
        for room in shop_rooms:
            start_result = start_game_if_shop(room["id"])
            if start_result.get("success") and start_result.get("started"):
                logger.info(
                    "Started room %s with bots_added=%s free_slots=%s fill_slots=%s",
                    room["id"],
                    start_result.get("bots_added"),
                    start_result.get("free_slots"),
                    start_result.get("fill_slots"),
                )
            else:
                logger.warning("Room %s was not started from shop: %s", room["id"], start_result)
            finish_game_and_pick_winner_if_running(room["id"])


stage_manager = StageManager()
