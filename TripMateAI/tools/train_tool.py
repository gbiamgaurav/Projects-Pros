"""Indian train search via erail.in's public endpoint (no API key).

Unofficial: scrapes erail.in's `~`/`^`-delimited response. Can break if erail
changes format. India-only (Indian Railways data).
"""

import os
import certifi
import requests
from dotenv import load_dotenv

from tools.flight_tool import parse_trip_text, clean_text

load_dotenv()

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

ERAIL_URL = "https://erail.in/rail/getTrains.aspx"

DEFAULT_ORIGIN_STATION = os.getenv("DEFAULT_ORIGIN_STATION", "SBC")  # Bengaluru

# Major-city -> primary railway station code. Indian station codes have no open
# lookup API, so busy cities are pinned here (same approach as airports).
STATION_CODES = {
    "bangalore": "SBC",
    "bengaluru": "SBC",
    "mumbai": "CSMT",
    "bombay": "CSMT",
    "delhi": "NDLS",
    "new delhi": "NDLS",
    "chennai": "MAS",
    "madras": "MAS",
    "kolkata": "HWH",
    "calcutta": "HWH",
    "howrah": "HWH",
    "hyderabad": "SC",
    "secunderabad": "SC",
    "pune": "PUNE",
    "ahmedabad": "ADI",
    "jaipur": "JP",
    "udaipur": "UDZ",
    "jodhpur": "JU",
    "goa": "MAO",
    "madgaon": "MAO",
    "kochi": "ERS",
    "cochin": "ERS",
    "ernakulam": "ERS",
    "trivandrum": "TVC",
    "thiruvananthapuram": "TVC",
    "lucknow": "LKO",
    "kanpur": "CNB",
    "varanasi": "BSB",
    "patna": "PNBE",
    "bhopal": "BPL",
    "indore": "INDB",
    "nagpur": "NGP",
    "surat": "ST",
    "vadodara": "BRC",
    "agra": "AGC",
    "amritsar": "ASR",
    "chandigarh": "CDG",
    "jammu": "JAT",
    "guwahati": "GHY",
    "bhubaneswar": "BBS",
    "visakhapatnam": "VSKP",
    "vizag": "VSKP",
    "coimbatore": "CBE",
    "madurai": "MDU",
    "mysore": "MYS",
    "mysuru": "MYS",
    "mangalore": "MAQ",
    "ranchi": "RNC",
    "raipur": "R",
    "gwalior": "GWL",
    "ajmer": "AII",
    "haridwar": "HW",
    "dehradun": "DDN",
    "shimla": "SML",
}

_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def resolve_station(text: str):
    """Resolve free text to an Indian Railways station code, or None."""
    if not text:
        return None

    raw = text.strip()

    # Deliberate uppercase station code (e.g. "NDLS", "SBC").
    if 2 <= len(raw) <= 5 and raw.isupper() and raw.isalpha():
        return raw

    cleaned = clean_text(raw)
    if cleaned in STATION_CODES:
        return STATION_CODES[cleaned]

    # Try individual words (e.g. "new delhi railway" -> "new delhi").
    for key in STATION_CODES:
        if key in cleaned:
            return STATION_CODES[key]

    return None


def _fmt_days(bitmask: str) -> str:
    if not bitmask or len(bitmask) < 7:
        return "?"
    runs = [d for d, b in zip(_DAYS, bitmask[:7]) if b == "1"]
    if len(runs) == 7:
        return "Daily"
    return ",".join(runs) if runs else "?"


def _fmt_time(t: str) -> str:
    """erail times look like '05.15' -> '05:15'."""
    return t.replace(".", ":") if t else "--:--"


def _fmt_duration(t: str) -> str:
    """erail travel time '39.00' -> '39h00m'."""
    if t and "." in t:
        h, m = t.split(".", 1)
        return f"{h}h{m}m"
    return t or "?"


def _parse_train(rec: str) -> str:
    f = rec.split("~")
    if len(f) < 14:
        return rec[:80]
    number, name = f[0], f[1]
    from_name, from_code = f[6], f[7]
    to_name, to_code = f[8], f[9]
    dep, arr, dur, days = f[10], f[11], f[12], f[13]
    return (
        f"{number} {name}"
        f" | {from_code} {_fmt_time(dep)} -> {to_code} {_fmt_time(arr)}"
        f" | {_fmt_duration(dur)} | runs {_fmt_days(days)}"
    )


def search_trains(destination: str, origin: str = None, limit: int = 8) -> str:
    """Search Indian trains between two stations (schedule; no live price).

    `origin` / `destination` accept a station code, city name, or a full
    sentence like "Plan a trip from Bangalore to Udaipur". No API key needed.
    """
    # Destination may be a full sentence ("... from X to Y") -> parse it.
    if origin is None or resolve_station(destination) is None:
        parsed_origin, parsed_dest = parse_trip_text(destination)
        origin = origin or parsed_origin
        destination = parsed_dest or destination

    origin = origin or DEFAULT_ORIGIN_STATION
    from_code = resolve_station(origin)
    to_code = resolve_station(destination)

    if not from_code:
        return f"Could not resolve origin station for '{origin}'."
    if not to_code:
        return f"Could not resolve destination station for '{destination}'."

    params = {
        "Station_From": from_code,
        "Station_To": to_code,
        "DataSource": 0,
        "Language": 0,
        "Cache": "true",
    }

    try:
        resp = requests.get(
            ERAIL_URL,
            params=params,
            headers={"User-Agent": "Mozilla/5.0"},
            timeout=20,
        )
        resp.raise_for_status()
        body = resp.text
    except requests.RequestException as e:
        return f"Train API request failed: {e}"

    # First '^'-chunk is a header; the rest are trains.
    chunks = [c for c in body.split("^") if c.strip()]
    trains = chunks[1:] if len(chunks) > 1 else []
    if not trains:
        return f"No direct trains found {from_code} -> {to_code}."

    lines = [f"Trains {from_code} -> {to_code}:"]
    for i, rec in enumerate(trains[:limit], 1):
        lines.append(f"{i}. {_parse_train(rec)}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(search_trains("Plan a 7 days trip from Bangalore to Udaipur"))
    print("\n" + "=" * 80 + "\n")
    print(search_trains("Mumbai", origin="Delhi"))
