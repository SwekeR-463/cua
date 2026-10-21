"""The routine clock: fire scheduled bot tasks while the app is open.

Mirrors ``CuaBotsCua/RoutineClock.swift``.  It runs in the backend process, so
routines work whenever the desktop app (or the backend) is running.
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from .models import TaskState, iso, utcnow
from .store import BotStore


class RoutineClock:
    def __init__(self, store: BotStore, path: Path | str):
        self.store = store
        self.path = Path(path)
        self.log: list[dict[str, Any]] = []
        self._task: Optional[asyncio.Task] = None
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                data = json.loads(self.path.read_text())
                self.log = data if isinstance(data, list) else []
            except Exception:
                self.log = []

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.log[-100:], indent=2))
        temp.replace(self.path)

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            self._task = None

    async def _loop(self) -> None:
        try:
            while True:
                await self.tick()
                await asyncio.sleep(20)
        except asyncio.CancelledError:
            return

    async def tick(self) -> None:
        now = utcnow()
        for bot in list(self.store.bots):
            for task in list(self.store.tasks_for(bot.id)):
                if not task.schedule or task.state is not TaskState.SCHEDULED:
                    continue
                if task.next_run and task.next_run > now:
                    continue
                summary = "Ran"
                if bot.is_paused:
                    summary = "Skipped: paused"
                elif self.store.is_busy(bot.id):
                    summary = "Skipped: busy"
                else:
                    try:
                        fired = await self.store.fire(task.id, bot.id)
                        summary = "Ran" if fired else "Skipped"
                    except Exception as exc:  # noqa: BLE001
                        summary = f"Failed: {exc}"
                # Always move the clock forward, even when skipped, so a busy
                # bot does not pile up every minute.
                task.next_run = task.schedule.next_fire(now)
                self.store.persist_tasks(bot.id)
                self.log.insert(0, {
                    "id": f"{task.id}-{int(now.timestamp())}",
                    "bot_id": bot.id,
                    "title": task.title,
                    "at": iso(now),
                    "summary": summary,
                })
                self._save()
                self.store.emit()
                break
