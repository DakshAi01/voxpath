"""Background news refresher.

Periodically crawls the configured news sources on a timer so the voice/chat
tools can read already-stored, fresh headlines instantly (no crawl latency on
the user's request). Controlled by NEWS_REFRESH_INTERVAL (seconds, default 300).
"""

from __future__ import annotations

import asyncio
import os
import time

import services
from logging_config import get_logger, new_trace_id

log = get_logger("voxpath.scheduler")

REFRESH_INTERVAL = float(os.getenv("NEWS_REFRESH_INTERVAL", "300"))

_task: asyncio.Task | None = None
_last_refresh: float | None = None  # epoch seconds of last successful crawl


async def _refresh_once() -> None:
    global _last_refresh
    new_trace_id(prefix="n")
    result = await asyncio.to_thread(
        services.crawl_news, source_query=None, dry_run=False, limit=None
    )
    _last_refresh = time.time()
    saved = result.get("saved")
    sources = len(result.get("summary") or [])
    log.info("news refresh complete: saved=%s from %s sources", saved, sources)


def status() -> dict:
    """Current refresher state for the /news/status endpoint."""
    age = (time.time() - _last_refresh) if _last_refresh else None
    return {
        "last_refresh": _last_refresh,
        "age_seconds": age,
        "interval_seconds": REFRESH_INTERVAL,
    }


async def _loop() -> None:
    log.info("background news refresher started (every %.0fs)", REFRESH_INTERVAL)
    while True:
        try:
            await _refresh_once()
        except asyncio.CancelledError:
            raise
        except Exception as error:  # noqa: BLE001
            log.warning("news refresh failed: %s", error)
        await asyncio.sleep(REFRESH_INTERVAL)


def start() -> None:
    """Start the background refresh loop (idempotent)."""
    global _task
    if _task is None or _task.done():
        _task = asyncio.create_task(_loop())


async def stop() -> None:
    """Cancel the background refresh loop."""
    global _task
    if _task and not _task.done():
        _task.cancel()
        try:
            await _task
        except asyncio.CancelledError:
            pass
    _task = None
