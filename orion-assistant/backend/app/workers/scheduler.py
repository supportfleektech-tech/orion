from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db.database import SessionLocal
from app.db.models import Automation

log = logging.getLogger(__name__)


class AutomationScheduler:
    """Lightweight in-process scheduler for recurring agent automations."""

    def __init__(self, tick_seconds: int = 30) -> None:
        self.tick_seconds = tick_seconds
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()

    async def start(self) -> None:
        if self._task is None:
            self._stop.clear()
            self._task = asyncio.create_task(self._loop())
            log.info("Automation scheduler started")

    async def stop(self) -> None:
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass  # expected: we just cancelled it
            except Exception:
                # The loop already catches per-tick failures, so reaching here
                # means the scheduler itself died. Swallowing that silently
                # leaves automations permanently stopped with no trace of why.
                log.exception("Automation scheduler stopped with an error")
            self._task = None

    async def _loop(self) -> None:
        while not self._stop.is_set():
            try:
                await self._tick()
            except Exception:  # pragma: no cover
                log.exception("Scheduler tick failed")
            try:
                await asyncio.wait_for(self._stop.wait(), timeout=self.tick_seconds)
            except TimeoutError:
                continue

    async def _tick(self) -> None:
        from app.services.agent_runtime import run_agent

        db = SessionLocal()
        try:
            now = datetime.now(UTC)
            automations = db.scalars(select(Automation).where(Automation.enabled.is_(True))).all()
            for automation in automations:
                last = automation.last_run_at
                if last is not None and last.tzinfo is None:
                    last = last.replace(tzinfo=UTC)
                if last and now - last < timedelta(seconds=automation.schedule_seconds):
                    continue
                log.info("Running automation %s", automation.name)
                try:
                    out = await run_agent(db, automation.prompt, mode="auto")
                    automation.last_status = "degraded" if out["degraded"] else "succeeded"
                    automation.last_result = (out["result"] or "")[:4000]
                except Exception as exc:
                    automation.last_status = "failed"
                    automation.last_result = str(exc)[:1000]
                automation.last_run_at = now
                db.commit()
        finally:
            db.close()


scheduler = AutomationScheduler()
