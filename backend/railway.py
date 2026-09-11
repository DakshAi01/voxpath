"""Indian Railways (IRCTC) data access for VoxPath.

Ported from the standalone India_Railway_Tracking_System FastMCP server into a
plain function module so VoxPath's voice/chat agents can call it as tools.
All data comes from the IRCTC API via RapidAPI (host: irctc-api2.p.rapidapi.com).

Requires RAPIDAPI_KEY in the environment.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta

import requests

from logging_config import get_logger

log = get_logger("voxpath.railway")

RAPIDAPI_HOST = "irctc-api2.p.rapidapi.com"
BASE_URL = f"https://{RAPIDAPI_HOST}"


def get_headers() -> dict:
    key = os.getenv("RAPIDAPI_KEY")
    if not key:
        raise ValueError("RAPIDAPI_KEY is not configured. Set it in backend/.env.")
    return {"x-rapidapi-key": key, "x-rapidapi-host": RAPIDAPI_HOST}


# --- date / time helpers ---------------------------------------------------

def normalize_date(date_str: str | None) -> str | None:
    """Normalize DD-MM-YYYY / DD/MM/YYYY / YYYY-MM-DD to DD-MM-YYYY."""
    if not date_str:
        return None
    date_str = date_str.strip()
    if len(date_str) == 10 and date_str[2] == "-" and date_str[5] == "-":
        try:
            datetime.strptime(date_str, "%d-%m-%Y")
            return date_str
        except ValueError:
            pass
    if "/" in date_str:
        try:
            parts = date_str.split("/")
            if len(parts) == 3:
                if len(parts[2]) == 4:
                    return datetime.strptime(date_str, "%d/%m/%Y").strftime("%d-%m-%Y")
                if len(parts[0]) == 4:
                    return datetime.strptime(date_str, "%Y/%m/%d").strftime("%d-%m-%Y")
        except ValueError:
            pass
    if len(date_str) == 10 and date_str[4] == "-":
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d-%m-%Y")
        except ValueError:
            pass
    return None


def get_default_date(days_ahead: int = 1) -> str:
    return (datetime.now() + timedelta(days=days_ahead)).strftime("%d-%m-%Y")


def minutes_to_time(minutes: int | None) -> str:
    if minutes is None or minutes < 0:
        return "N/A"
    return f"{(minutes // 60) % 24:02d}:{minutes % 60:02d}"


def parse_time_to_minutes(time_str: str) -> int:
    if not time_str or time_str == "N/A":
        return -1
    try:
        parts = time_str.split(":")
        return int(parts[0]) * 60 + int(parts[1])
    except Exception:
        return -1


def parse_duration_to_minutes(duration_str: str) -> int:
    if not duration_str or duration_str == "N/A":
        return -1
    try:
        if "h" in duration_str:
            parts = duration_str.lower().replace("m", "").split("h")
            hours = int(parts[0].strip())
            mins = int(parts[1].strip()) if len(parts) > 1 and parts[1].strip() else 0
            return hours * 60 + mins
        if ":" in duration_str:
            parts = duration_str.split(":")
            return int(parts[0]) * 60 + int(parts[1])
        return int(duration_str)
    except Exception:
        return -1


def minutes_to_duration(mins: int) -> str:
    if mins < 0:
        return "N/A"
    hours, minutes = mins // 60, mins % 60
    return f"{hours}h {minutes}m" if hours > 0 else f"{minutes}m"


# --- city/station maps -----------------------------------------------------

DELHI_STATIONS = ["NDLS", "ANVT", "DLI", "DEE", "DEC", "SZM"]
MUMBAI_STATIONS = ["CSMT", "BCT", "LTT", "BDTS"]
KOLKATA_STATIONS = ["HWH", "SDAH", "KOAA"]
CHENNAI_STATIONS = ["MAS", "MS", "MSB"]

CITY_STATION_MAP = {
    "DELHI": DELHI_STATIONS, "NEW DELHI": DELHI_STATIONS,
    "MUMBAI": MUMBAI_STATIONS, "KOLKATA": KOLKATA_STATIONS, "CHENNAI": CHENNAI_STATIONS,
    "HAJIPUR": ["HJP"], "PATNA": ["PNBE", "PPTA", "RJPB"], "MUZAFFARPUR": ["MFP"],
    "GAYA": ["GAYA"], "DARBHANGA": ["DBG"],
    "LUCKNOW": ["LKO", "LJN"], "VARANASI": ["BSB", "BCY"], "KANPUR": ["CNB"],
    "ALLAHABAD": ["PRYJ", "ALD"], "PRAYAGRAJ": ["PRYJ", "ALD"], "AGRA": ["AGC", "AF"],
    "GORAKHPUR": ["GKP"], "JAIPUR": ["JP"], "JODHPUR": ["JU"], "UDAIPUR": ["UDZ"],
    "AJMER": ["AII"], "AHMEDABAD": ["ADI"], "SURAT": ["ST"], "VADODARA": ["BRC"],
    "BHOPAL": ["BPL"], "INDORE": ["INDB"], "JABALPUR": ["JBP"],
    "BANGALORE": ["SBC", "BNCE"], "BENGALURU": ["SBC", "BNCE"], "HYDERABAD": ["SC", "HYB"],
    "SECUNDERABAD": ["SC"], "COIMBATORE": ["CBE"], "TRIVANDRUM": ["TVC"], "KOCHI": ["ERS"],
    "BHUBANESWAR": ["BBS"], "RANCHI": ["RNC"], "GUWAHATI": ["GHY"],
    "AMRITSAR": ["ASR"], "CHANDIGARH": ["CDG"], "LUDHIANA": ["LDH"],
}

MAJOR_JUNCTIONS = [
    "NDLS", "CNB", "MGS", "HWH", "CSMT", "BCT", "NGP", "BZA",
    "MAS", "SBC", "SC", "ADI", "JP", "LKO", "PNBE",
]


def _resolve_station_internal(station_name: str) -> list[str]:
    station_name = station_name.strip().upper()
    if station_name in CITY_STATION_MAP:
        return CITY_STATION_MAP[station_name]
    if len(station_name) <= 5 and station_name.isalpha():
        return [station_name]
    try:
        r = requests.get(
            f"{BASE_URL}/stationSearch", headers=get_headers(),
            params={"code": station_name}, timeout=10,
        )
        if r.status_code == 200:
            data = r.json().get("data", [])
            if data:
                return [data[0].get("station_code", station_name)]
    except Exception as error:
        log.error("station resolution failed for %s: %s", station_name, error)
    return [station_name]


# --- public tool functions -------------------------------------------------

def get_pnr_status(pnr: str) -> dict:
    """Detailed PNR status: train info, journey details, passenger status."""
    log.info("PNR status: %s", pnr)
    if not pnr:
        return {"error": "PNR number is required"}
    pnr = pnr.strip()
    if not pnr.isdigit() or len(pnr) != 10:
        return {"error": "PNR must be exactly 10 digits"}
    try:
        r = requests.get(f"{BASE_URL}/pnrStatus", headers=get_headers(), params={"pnr": pnr}, timeout=15)
        r.raise_for_status()
        data = r.json().get("data", {})
        if not data:
            return {"error": "No data found. PNR might be invalid."}
        journey_date = (
            data.get("dateOfJourney") or data.get("doj") or data.get("journeyDate")
            or data.get("date") or "N/A"
        )
        return {
            "pnr": pnr,
            "train_info": {
                "name": data.get("trainName", "Unknown"),
                "number": data.get("trainNumber", "Unknown"),
            },
            "journey_details": {
                "date_of_journey": journey_date,
                "departure_time": data.get("departureTime", "N/A"),
                "arrival_time": data.get("arrivalTime", "N/A"),
                "from_station": data.get("from") or data.get("fromStation", "N/A"),
                "to_station": data.get("to") or data.get("toStation", "N/A"),
                "duration": data.get("duration", "N/A"),
                "class": data.get("class") or data.get("journeyClass", "N/A"),
                "chart_status": data.get("chartStatus") or data.get("chartPrepared", "N/A"),
            },
            "passengers": [
                {
                    "number": idx + 1,
                    "booking_status": p.get("bookingStatus", "N/A"),
                    "current_status": p.get("currentStatus", "N/A"),
                }
                for idx, p in enumerate(data.get("passengers", []))
            ],
        }
    except Exception as error:
        log.error("PNR API error: %s", error)
        return {"error": str(error)}


def resolve_station_code(station_name: str) -> dict:
    """Find the station code(s) for a city/station name (e.g. 'Delhi' -> 'NDLS')."""
    log.info("resolve station: %s", station_name)
    if not station_name or not station_name.strip():
        return {"error": "Station name is required"}
    try:
        r = requests.get(f"{BASE_URL}/stationSearch", headers=get_headers(), params={"code": station_name}, timeout=10)
        r.raise_for_status()
        data = r.json().get("data", [])
        if not data:
            return {"error": f"No station found for '{station_name}'"}
        return {
            "match_found": True,
            "stations": [
                {
                    "name": s.get("station_name"),
                    "code": s.get("station_code"),
                    "location": f"{s.get('city_name', '')}, {s.get('state_name', '')}",
                }
                for s in data[:5]
            ],
        }
    except Exception as error:
        log.error("station search error: %s", error)
        return {"error": f"Station search failed: {error}"}


def get_train_schedule(train_number: str) -> dict:
    """Complete schedule/route of a train with all stops and timings."""
    log.info("train schedule: %s", train_number)
    if not train_number:
        return {"error": "Train number is required"}
    train_number = train_number.strip()
    if not train_number.isdigit() or len(train_number) not in (4, 5):
        return {"error": "Train number must be 4-5 digits"}
    try:
        r = requests.get(f"{BASE_URL}/trainSchedule", headers=get_headers(), params={"trainNumber": train_number}, timeout=15)
        r.raise_for_status()
        data = r.json().get("data", [])
        if not data:
            return {"error": f"No schedule found for train {train_number}"}
        stops, major_stops = [], []
        for station in data:
            is_stop = station.get("stop", False)
            info = {
                "station_name": station.get("station_name", "N/A"),
                "station_code": station.get("station_code", "N/A"),
                "state": station.get("state_name", "N/A"),
                "departure_time": minutes_to_time(station.get("std_min")),
                "day": station.get("day", 1),
                "platform": station.get("platform_number", "N/A"),
                "is_stop": is_stop,
            }
            stops.append(info)
            if is_stop:
                major_stops.append(info)
        return {
            "train_number": train_number,
            "total_stations": len(stops),
            "total_stops": len(major_stops),
            "major_stops": major_stops,
        }
    except Exception as error:
        log.error("train schedule error: %s", error)
        return {"error": str(error)}


def get_live_train_status(train_number: str, date: str | None = None) -> dict:
    """Live running status of a train: current location, delay, running status."""
    log.info("live status: %s date=%s", train_number, date)
    if not train_number:
        return {"error": "Train number is required"}
    train_number = train_number.strip()
    if not train_number.isdigit() or len(train_number) not in (4, 5):
        return {"error": "Train number must be 4-5 digits"}
    params = {"trainNumber": train_number}
    if date:
        normalized = normalize_date(date)
        if normalized:
            d = normalized.split("-")
            params["date"] = f"{d[2]}-{d[1]}-{d[0]}"  # API wants YYYY-MM-DD
    try:
        r = requests.get(f"{BASE_URL}/liveTrainStatus", headers=get_headers(), params=params, timeout=15)
        r.raise_for_status()
        data = r.json().get("data", {})
        if not data:
            return {"error": f"No live status for train {train_number}. It may not be running today."}
        current = data.get("currentStation", {})
        return {
            "train_number": data.get("trainNumber", train_number),
            "train_name": data.get("trainName", "Unknown"),
            "running_status": data.get("status", "Unknown"),
            "delay_minutes": data.get("delay", 0),
            "current_station": {
                "name": current.get("stationName", "N/A"),
                "code": current.get("stationCode", "N/A"),
                "arrived": current.get("actualArrival", "N/A"),
                "departed": current.get("actualDeparture", "N/A"),
            },
            "last_updated": data.get("lastUpdated", "N/A"),
            "source": data.get("source", "N/A"),
            "destination": data.get("destination", "N/A"),
        }
    except Exception as error:
        log.error("live status error: %s", error)
        return {"error": str(error)}


def get_fare(train_number: str, source: str, destination: str, date: str | None = None) -> dict:
    """Ticket fare/price by class for a train between two station codes."""
    log.info("fare: %s %s->%s", train_number, source, destination)
    if not train_number or not source or not destination:
        return {"error": "Train number, source, and destination are required"}
    train_number = train_number.strip()
    source, destination = source.strip().upper(), destination.strip().upper()
    date = normalize_date(date) or get_default_date()
    try:
        r = requests.get(
            f"{BASE_URL}/trainAvailability", headers=get_headers(),
            params={"source": source, "destination": destination, "date": date}, timeout=20,
        )
        r.raise_for_status()
        data = r.json().get("data", [])
        if not data:
            return {"error": f"No trains found from {source} to {destination}"}
        train_data = next((t for t in data if t.get("trainNumber") == train_number), None)
        if not train_data:
            return {"error": f"Train {train_number} not found on route {source} to {destination}"}
        fares = [
            {
                "class": cls.get("class", "N/A"),
                "fare": f"₹{cls.get('fare', 'N/A')}",
                "availability": cls.get("displayStatus", "N/A"),
            }
            for cls in train_data.get("classAvailability", [])
        ]
        return {
            "train_number": train_number,
            "train_name": train_data.get("trainName", "Unknown"),
            "source": train_data.get("from", {}).get("name", source),
            "destination": train_data.get("to", {}).get("name", destination),
            "distance_km": train_data.get("distanceKm", "N/A"),
            "duration": train_data.get("duration", "N/A"),
            "fares_by_class": fares,
        }
    except Exception as error:
        log.error("fare error: %s", error)
        return {"error": str(error)}


def check_seat_availability(source: str, destination: str, date: str, train_number: str | None = None) -> dict:
    """Class-wise seat availability between two station codes on a date (DD-MM-YYYY)."""
    log.info("availability: %s->%s %s train=%s", source, destination, date, train_number)
    if not source or not destination or not date:
        return {"error": "Source, destination, and date are required"}
    source, destination = source.strip().upper(), destination.strip().upper()
    date = normalize_date(date) or date
    try:
        r = requests.get(
            f"{BASE_URL}/trainAvailability", headers=get_headers(),
            params={"source": source, "destination": destination, "date": date}, timeout=20,
        )
        r.raise_for_status()
        data = r.json().get("data", [])
        if not data:
            return {"error": f"No trains found from {source} to {destination} on {date}"}
        trains = []
        for train in data:
            if train_number and train.get("trainNumber") != train_number:
                continue
            class_availability = [
                {
                    "class": cls.get("class", "N/A"),
                    "status": cls.get("displayStatus", "N/A"),
                    "availability": cls.get("availability", "N/A"),
                    "fare": f"₹{cls.get('fare', 'N/A')}",
                    "confirmation_chance": cls.get("prediction", "N/A"),
                }
                for cls in train.get("classAvailability", [])
            ]
            trains.append({
                "train_number": train.get("trainNumber", "N/A"),
                "train_name": train.get("trainName", "N/A"),
                "from": train.get("from", {}).get("name", source),
                "to": train.get("to", {}).get("name", destination),
                "departure": train.get("departure", "N/A"),
                "arrival": train.get("arrival", "N/A"),
                "duration": train.get("duration", "N/A"),
                "class_availability": class_availability,
            })
        if not trains:
            return {"error": f"Train {train_number} not found on this route for {date}"}
        return {"source": source, "destination": destination, "date": date,
                "trains_found": len(trains), "trains": trains}
    except Exception as error:
        log.error("availability error: %s", error)
        return {"error": str(error)}


def search_trains(source: str, destination: str, date: str | None = None) -> dict:
    """Search all trains between two stations/cities (expands major cities)."""
    log.info("search trains: %s->%s", source, destination)
    if not source or not destination:
        return {"error": "Source and destination are required"}
    source, destination = source.strip().upper(), destination.strip().upper()
    source_stations = CITY_STATION_MAP.get(source, [source])
    dest_stations = CITY_STATION_MAP.get(destination, [destination])
    date = normalize_date(date) or get_default_date()
    all_trains, searched = [], []
    for src in source_stations:
        for dest in dest_stations:
            try:
                r = requests.get(
                    f"{BASE_URL}/trainAvailability", headers=get_headers(),
                    params={"source": src, "destination": dest, "date": date}, timeout=20,
                )
                if r.status_code == 200:
                    searched.append(f"{src} -> {dest}")
                    for t in r.json().get("data", []):
                        num = t.get("trainNumber")
                        if not any(tr["train_number"] == num for tr in all_trains):
                            all_trains.append({
                                "train_number": num,
                                "train_name": t.get("trainName", "N/A"),
                                "source_station": f"{t.get('from', {}).get('name', 'N/A')} ({t.get('from', {}).get('code', src)})",
                                "destination_station": f"{t.get('to', {}).get('name', 'N/A')} ({t.get('to', {}).get('code', dest)})",
                                "departure": t.get("departure", "N/A"),
                                "arrival": t.get("arrival", "N/A"),
                                "duration": t.get("duration", "N/A"),
                                "classes": t.get("allClasses", []),
                            })
            except Exception as error:
                log.error("search %s->%s error: %s", src, dest, error)
                continue
    if not all_trains:
        return {"error": f"No trains found from {source} to {destination}"}
    all_trains.sort(key=lambda x: x["departure"])
    return {"search_query": f"{source} to {destination}", "date": date,
            "train_count": len(all_trains), "trains": all_trains}
