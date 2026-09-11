"""Resolve a company name or ticker to its official NSE symbol.

Fetches NSE's official equity master list from the net (cached), so any of the
~2,300 NSE-listed companies can be found by official name or symbol — no
hardcoded aliases. Used as the primary source by services.get_stock_price,
with Yahoo search as a secondary source for renames/demergers and BSE-only names.
"""

from __future__ import annotations

import csv
import io
import threading
import time

import requests

from logging_config import get_logger

log = get_logger("voxpath.stocks")

NSE_URL = "https://nsearchives.nseindia.com/content/equities/EQUITY_L.csv"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )
}
TTL_SECONDS = 24 * 3600

_rows: list[tuple[str, str]] = []  # (SYMBOL, NAME OF COMPANY upper-cased)
_fetched_at = 0.0
_lock = threading.Lock()

_NOISE = {"LIMITED", "LTD", "LTD.", "THE", "INDIA", "CORPORATION", "CORP", "COMPANY", "CO"}


def _load() -> list[tuple[str, str]]:
    """Return the cached NSE equity list, refreshing from the net if stale."""
    global _rows, _fetched_at
    with _lock:
        if _rows and (time.time() - _fetched_at) < TTL_SECONDS:
            return _rows
        try:
            response = requests.get(NSE_URL, headers=_HEADERS, timeout=15)
            response.raise_for_status()
            reader = csv.reader(io.StringIO(response.text))
            next(reader, None)  # header
            rows = [
                (row[0].strip(), row[1].strip().upper())
                for row in reader
                if len(row) >= 2 and row[0].strip()
            ]
            if rows:
                _rows, _fetched_at = rows, time.time()
                log.info("loaded %d NSE-listed symbols", len(rows))
        except Exception as error:  # noqa: BLE001 - keep any stale cache on failure
            log.warning("NSE equity list fetch failed: %s", error)
        return _rows


def nse_matches(query: str, limit: int = 3) -> list[str]:
    """Return up to `limit` NSE symbols matching a company name or ticker."""
    rows = _load()
    if not rows:
        return []

    q = query.strip().upper()
    compact = q.replace(" ", "")

    # Exact ticker match wins.
    for symbol, _name in rows:
        if symbol == compact:
            return [symbol]

    q_words = {w for w in q.split() if w not in _NOISE}
    scored: list[tuple[int, int, str]] = []
    for symbol, name in rows:
        if name == q:
            score = 100
        elif name.startswith(q + " "):
            score = 85
        elif q in name:
            score = 65
        elif q_words and q_words.issubset({w for w in name.split() if w not in _NOISE}):
            score = 55
        else:
            score = 0
        if score:
            scored.append((score, len(name), symbol))

    scored.sort(key=lambda item: (-item[0], item[1]))
    return [symbol for _score, _len, symbol in scored[:limit]]
