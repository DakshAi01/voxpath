"""Central logging configuration for VoxPath.

Provides:
- Structured console + rotating-file logs (backend/logs/voxpath.log).
- A per-request / per-voice-session trace id (8-char) carried via a ContextVar
  so every log line emitted while handling one request can be grepped together.
- get_logger() for module-level loggers.

Log level is controlled by the LOG_LEVEL env var (default INFO). Set LOG_LEVEL=DEBUG
for verbose tracing (audio chunk counts, LLM prompts, etc.).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime
from logging.handlers import RotatingFileHandler
from pathlib import Path

_trace_id: ContextVar[str] = ContextVar("trace_id", default="-")

LOG_FORMAT = "%(asctime)s | %(levelname)-7s | %(trace_id)-8s | %(name)-18s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
LOG_DIR = Path(__file__).resolve().parent / "logs"
LOG_FILE = LOG_DIR / "voxpath.log"
TOOL_LOG_FILE = LOG_DIR / "tool_calls.log"
TOOL_READABLE_FILE = LOG_DIR / "tool_calls_readable.log"

_configured = False
_tool_logger: logging.Logger | None = None
_readable_logger: logging.Logger | None = None


def new_trace_id(prefix: str = "") -> str:
    """Generate and install a fresh trace id for the current context."""
    tid = (prefix + uuid.uuid4().hex)[:8]
    _trace_id.set(tid)
    return tid


def set_trace_id(value: str) -> None:
    _trace_id.set(value)


def get_trace_id() -> str:
    return _trace_id.get()


class _TraceIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.trace_id = _trace_id.get()
        return True


def setup_logging() -> None:
    """Configure root logging once. Safe to call multiple times."""
    global _configured
    if _configured:
        return

    level = os.getenv("LOG_LEVEL", "INFO").upper()
    LOG_DIR.mkdir(exist_ok=True)

    formatter = logging.Formatter(LOG_FORMAT, DATE_FORMAT)
    trace_filter = _TraceIdFilter()

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(formatter)
    console.addFilter(trace_filter)

    file_handler = RotatingFileHandler(
        LOG_FILE, maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(trace_filter)

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(file_handler)

    # Let uvicorn's loggers flow through our handlers/format instead of their own.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.propagate = True

    # Dedicated structured JSON-lines log for tool calls (separate file, no console).
    global _tool_logger
    tool_logger = logging.getLogger("voxpath.toolcalls.file")
    tool_logger.setLevel(logging.INFO)
    tool_logger.propagate = False
    tool_handler = RotatingFileHandler(
        TOOL_LOG_FILE, maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    tool_handler.setFormatter(logging.Formatter("%(message)s"))
    tool_logger.handlers.clear()
    tool_logger.addHandler(tool_handler)
    _tool_logger = tool_logger

    # Human-readable, curated tool-output log (separate file, no console).
    global _readable_logger
    readable_logger = logging.getLogger("voxpath.toolcalls.readable")
    readable_logger.setLevel(logging.INFO)
    readable_logger.propagate = False
    readable_handler = RotatingFileHandler(
        TOOL_READABLE_FILE, maxBytes=5_000_000, backupCount=5, encoding="utf-8"
    )
    readable_handler.setFormatter(logging.Formatter("%(message)s"))
    readable_logger.handlers.clear()
    readable_logger.addHandler(readable_handler)
    _readable_logger = readable_logger

    _configured = True
    root.getChild("logging").debug("Logging initialized at level %s -> %s", level, LOG_FILE)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def log_tool_call(tool: str, tool_input, output, duration_ms: float, status: str) -> None:
    """Append one structured JSON line to tool_calls.log for parsing/replay."""
    if _tool_logger is None:
        return
    record = {
        "ts": datetime.now().isoformat(timespec="milliseconds"),
        "trace": _trace_id.get(),
        "tool": tool,
        "status": status,
        "duration_ms": round(duration_ms, 1),
        "input": tool_input,
        "output": output,
    }
    _tool_logger.info(json.dumps(record, ensure_ascii=False, default=str))


def log_tool_readable(tool: str, body: str, duration_ms: float, status: str) -> None:
    """Append a curated, human-readable block to tool_calls_readable.log."""
    if _readable_logger is None:
        return
    ts = datetime.now().isoformat(timespec="seconds")
    flag = "OK" if status == "ok" else "ERROR"
    header = f"========== {ts} | {_trace_id.get()} | {tool} | {flag} | {duration_ms:.0f}ms"
    _readable_logger.info(f"{header}\n{body}\n")
