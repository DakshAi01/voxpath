"""Human-readable rendering of tool outputs for tool_calls_readable.log.

Turns each tool's JSON result into a clean, indented text block so the log can
be read at a glance. Unknown shapes fall back to pretty-printed JSON.
"""

from __future__ import annotations

import json


def _kv(label: str, value) -> str:
    return f"{label}: {value}"


def _pnr(o: dict) -> str:
    ti = o.get("train_info", {})
    j = o.get("journey_details", {})
    lines = [
        f"PNR {o.get('pnr', '?')} — {ti.get('name', '?')} ({ti.get('number', '?')})",
        f"  {j.get('from_station', '?')} -> {j.get('to_station', '?')}  on {j.get('date_of_journey', '?')}",
        f"  Class {j.get('class', '?')} | Chart: {j.get('chart_status', '?')} | Dep {j.get('departure_time', '?')}",
        "  Passengers:",
    ]
    for p in o.get("passengers", []):
        lines.append(
            f"    {p.get('number', '?')}. Booking {p.get('booking_status', '?')} | Current {p.get('current_status', '?')}"
        )
    return "\n".join(lines)


def _news(o: dict) -> str:
    items = o.get("headlines", [])
    lines = [f"Latest headlines ({o.get('count', len(items))}):"]
    for i, h in enumerate(items, 1):
        lines.append(f"  {i}. {h.get('headline', '?')}  —  {h.get('source', '?')}")
    return "\n".join(lines)


def _stock(o: dict) -> str:
    return f"Price: {o.get('result', '?')}"


def _stations(o: dict) -> str:
    lines = ["Stations:"]
    for s in o.get("stations", []):
        lines.append(f"  {s.get('name', '?')} ({s.get('code', '?')}) — {s.get('location', '')}")
    return "\n".join(lines)


def _live_status(o: dict) -> str:
    cur = o.get("current_station", {})
    return "\n".join([
        f"Train {o.get('train_number', '?')} — {o.get('train_name', '?')}",
        f"  Status: {o.get('running_status', '?')} | Delay: {o.get('delay_minutes', 0)} min",
        f"  At: {cur.get('name', '?')} ({cur.get('code', '?')})  arr {cur.get('arrived', '?')} / dep {cur.get('departed', '?')}",
        f"  {o.get('source', '?')} -> {o.get('destination', '?')} | Updated {o.get('last_updated', '?')}",
    ])


def _schedule(o: dict) -> str:
    lines = [
        f"Train {o.get('train_number', '?')} — {o.get('total_stops', '?')} stops of {o.get('total_stations', '?')} stations:"
    ]
    for s in o.get("major_stops", []):
        lines.append(
            f"  {s.get('station_code', '?'):<6} {s.get('station_name', '?'):<28} dep {s.get('departure_time', '?')}  day {s.get('day', '?')}  plat {s.get('platform', '?')}"
        )
    return "\n".join(lines)


def _search(o: dict) -> str:
    lines = [f"Trains {o.get('search_query', '?')} on {o.get('date', '?')} ({o.get('train_count', '?')} found):"]
    for t in o.get("trains", []):
        lines.append(
            f"  {t.get('train_number', '?')} {t.get('train_name', '?')}  {t.get('departure', '?')} -> {t.get('arrival', '?')} ({t.get('duration', '?')})  [{', '.join(t.get('classes', []))}]"
        )
    return "\n".join(lines)


def _availability(o: dict) -> str:
    lines = [
        f"Availability {o.get('source', '?')} -> {o.get('destination', '?')} on {o.get('date', '?')} ({o.get('trains_found', '?')} trains):"
    ]
    for t in o.get("trains", []):
        lines.append(f"  {t.get('train_number', '?')} {t.get('train_name', '?')}  {t.get('departure', '?')} -> {t.get('arrival', '?')}")
        for c in t.get("class_availability", []):
            lines.append(
                f"      {c.get('class', '?'):<5} {c.get('status', '?')} | {c.get('fare', '?')} | conf {c.get('confirmation_chance', '?')}"
            )
    return "\n".join(lines)


def _fare(o: dict) -> str:
    lines = [
        f"Fare — {o.get('train_number', '?')} {o.get('train_name', '?')}  {o.get('source', '?')} -> {o.get('destination', '?')} ({o.get('distance_km', '?')} km, {o.get('duration', '?')})"
    ]
    for f in o.get("fares_by_class", []):
        lines.append(f"  {f.get('class', '?'):<5} {f.get('fare', '?')}  ({f.get('availability', '?')})")
    return "\n".join(lines)


_RENDERERS = {
    "get_pnr_status": _pnr,
    "get_latest_news": _news,
    "get_stock_price": _stock,
    "resolve_station_code": _stations,
    "get_live_train_status": _live_status,
    "get_train_schedule": _schedule,
    "search_trains": _search,
    "check_seat_availability": _availability,
    "get_fare": _fare,
}


def render(tool: str, tool_input: dict, output) -> str:
    """Return a readable, indented text block for a tool result."""
    header = f"Input: {json.dumps(tool_input, ensure_ascii=False)}"
    if isinstance(output, dict) and output.get("error"):
        return f"{header}\nERROR: {output['error']}"
    renderer = _RENDERERS.get(tool)
    if renderer and isinstance(output, dict):
        try:
            return f"{header}\n{renderer(output)}"
        except Exception:  # noqa: BLE001 - never let formatting break logging
            pass
    return f"{header}\n{json.dumps(output, ensure_ascii=False, indent=2)}"
