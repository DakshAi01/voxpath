from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data" / "news"
SEEN_HASHES_FILE = DATA_DIR / "seen_hashes.json"


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)


def load_seen_hashes() -> set[str]:
    if not SEEN_HASHES_FILE.exists():
        return set()
    try:
        return set(json.loads(SEEN_HASHES_FILE.read_text(encoding="utf-8")))
    except Exception:
        return set()


def save_seen_hashes(hashes: set[str]) -> None:
    ensure_dirs()
    temp = SEEN_HASHES_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(sorted(hashes)), encoding="utf-8")
    temp.replace(SEEN_HASHES_FILE)


def get_current_filename() -> Path:
    ensure_dirs()
    date_str = datetime.now().strftime("%Y-%m-%d")
    return DATA_DIR / f"headlines_{date_str}.jsonl"


def append_to_jsonl(records: list[dict]) -> Path:
    ensure_dirs()
    filename = get_current_filename()
    if records:
        with filename.open("a", encoding="utf-8") as file_obj:
            for record in records:
                file_obj.write(json.dumps(record, ensure_ascii=False) + "\n")
    return filename


def get_latest_file() -> Path | None:
    ensure_dirs()
    files = sorted(DATA_DIR.glob("headlines_*.jsonl"), reverse=True)
    return files[0] if files else None


def read_jsonl(filepath: Path | None) -> list[dict]:
    if filepath is None or not filepath.exists():
        return []
    records: list[dict] = []
    with filepath.open("r", encoding="utf-8") as file_obj:
        for line in file_obj:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records
