import os
import re
import datetime
import certifi
import airportsdata
from dotenv import load_dotenv
from fast_flights import FlightQuery, Passengers, create_query, get_flights

load_dotenv()

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

DEFAULT_ORIGIN_IATA = os.getenv("DEFAULT_ORIGIN_IATA", "BLR")

# Flight prices come from Google Flights via the `fast-flights` scraper
# (no API key). Unofficial: depends on Google's internal format and can break.
CURRENCY = os.getenv("FLIGHT_CURRENCY", "INR")

# iata_code -> record {name, city, subd, country (ISO alpha-2), lat, lon, tz, ...}
AIRPORTS = airportsdata.load("IATA")


# ---------------------------------------------------------------------------
# City name resolution
# ---------------------------------------------------------------------------

# City names are ambiguous worldwide (London UK vs London Ontario) and share
# spellings with unrelated IATA codes, so busy/ambiguous cities are pinned here.
# get_airport_for_city() handles the long tail dynamically.
CITY_MAIN_AIRPORT = {
    "london": "LHR",
    "new york": "JFK",
    "paris": "CDG",
    "tokyo": "HND",
    "moscow": "SVO",
    "milan": "MXP",
    "chicago": "ORD",
    "washington": "IAD",
    "houston": "IAH",
    "sao paulo": "GRU",
    "rio de janeiro": "GIG",
    "buenos aires": "EZE",
    "istanbul": "IST",
    "beijing": "PEK",
    "shanghai": "PVG",
    "osaka": "KIX",
    "seoul": "ICN",
    "bangkok": "BKK",
    "delhi": "DEL",
    "new delhi": "DEL",
    "mumbai": "BOM",
    "goa": "GOI",
    "bengaluru": "BLR",
    "bangalore": "BLR",
    "rome": "FCO",
    "berlin": "BER",
    "toronto": "YYZ",
    "los angeles": "LAX",
    "san francisco": "SFO",
}


def clean_text(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text)
    stop_words = [
        "flight", "flights", "ticket", "tickets", "trip", "travel",
        "plan", "complete", "days", "day", "including", "hotel",
        "hotels", "sightseeing", "under", "budget", "info", "information",
        "to", "from", "for", "the", "a", "an", "in", "at",
    ]

    words = [w for w in text.split() if w not in stop_words]
    return " ".join(words).strip()


# ---------------------------------------------------------------------------
# Airport resolution
# ---------------------------------------------------------------------------

def _score_airport(airport: dict) -> int:
    """Heuristic 'importance' score (no traffic data available)."""
    name = str(airport.get("name", "")).lower()
    city = str(airport.get("city", "")).lower()

    score = 0
    if "international" in name:
        score += 50
    # Airport named after its own city tends to be the primary one.
    if city and city in name:
        score += 20
    for weak in ("regional", "municipal", "air base", "airfield", "airstrip"):
        if weak in name:
            score -= 40
    return score


def get_airport_for_city(city_text: str):
    """Return the best airport IATA code matching a city name, or None."""
    city_text = clean_text(city_text)
    if not city_text:
        return None

    if city_text in CITY_MAIN_AIRPORT:
        return CITY_MAIN_AIRPORT[city_text]

    # Exact city-name match only (substring matching pulled in wrong cities).
    best_iata, best_score = None, None
    for iata, airport in AIRPORTS.items():
        if not iata:
            continue
        if str(airport.get("city", "")).strip().lower() == city_text:
            score = _score_airport(airport)
            if best_score is None or score > best_score:
                best_iata, best_score = iata, score

    return best_iata


def resolve_airport(text: str):
    """Resolve free text (IATA code or city) to an airport IATA code, or None."""
    if not text:
        return None

    raw = text.strip()

    # 1. Deliberate uppercase 3-letter IATA code (e.g. "BLR", "JFK").
    if len(raw) == 3 and raw.isupper() and raw in AIRPORTS:
        return raw

    # 2. City name.
    return get_airport_for_city(raw)


# ---------------------------------------------------------------------------
# Free-text trip parsing
# ---------------------------------------------------------------------------

def parse_trip_text(text: str):
    """Pull (origin, destination) out of a free-text request.

    Handles 'from X to Y', 'X to Y', and 'to Y' (origin -> None).
    Returns (origin_or_None, destination_or_None).
    """
    if not text:
        return None, None

    t = " " + text.strip() + " "

    # from X to Y
    m = re.search(r"\bfrom\s+(.+?)\s+\bto\b\s+(.+)", t, re.IGNORECASE)
    if m:
        return _trim_place(m.group(1)), _trim_place(m.group(2))

    # ... to Y  (destination only). Split on the LAST 'to' so the infinitive in
    # "I want to travel to Kolkata" doesn't swallow the real destination.
    parts = re.split(r"\bto\b", t, flags=re.IGNORECASE)
    if len(parts) > 1 and parts[-1].strip():
        return None, _trim_place(parts[-1])

    # No connective words -> treat the whole thing as a destination.
    return None, _trim_place(text)


def _trim_place(text: str) -> str:
    """Reduce a phrase to just the place name.

    Cuts at punctuation ("Kolkata, what's cheapest" -> "Kolkata") and at trailing
    trip/duration clauses ("Goa for 5 days" -> "Goa").
    """
    text = text.strip()
    # Stop at the first sentence punctuation.
    text = re.split(r"[,.;:?!]", text, maxsplit=1)[0]
    # Stop at a trailing clause: 'for 5 days', 'in July', question words, digits.
    text = re.split(
        r"\b(?:for|over|during|within|in|on|next|this|around|about|under|below|"
        r"with|including|what|whats|which|where|cheapest|today|tomorrow|"
        r"tommorow|tomorow)\b|\d",
        text,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    return text.strip(" ,.-")


# ---------------------------------------------------------------------------
# Flight search (Google Flights via fast-flights: schedule + price, no key)
# ---------------------------------------------------------------------------

def _default_departure_date() -> str:
    """Google Flights needs a future date; default to 2 weeks out."""
    return (datetime.date.today() + datetime.timedelta(days=14)).isoformat()


def extract_date(text: str):
    """Pull a departure date (YYYY-MM-DD) from free text, or None.

    Handles explicit ISO dates and relative phrases: today, tomorrow (incl.
    common misspellings), day after tomorrow, next week/month, in N days.
    """
    if not text:
        return None
    t = text.lower()
    today = datetime.date.today()

    m = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", t)
    if m:
        return m.group(1)

    if "day after tomorrow" in t or "day after tommorow" in t:
        return (today + datetime.timedelta(days=2)).isoformat()
    if re.search(r"\btom+or+ow\b", t):  # tomorrow / tommorow / tomorow
        return (today + datetime.timedelta(days=1)).isoformat()
    if "today" in t or "tonight" in t:
        return today.isoformat()
    if "next week" in t:
        return (today + datetime.timedelta(days=7)).isoformat()
    if "next month" in t:
        return (today + datetime.timedelta(days=30)).isoformat()

    m = re.search(r"\bin\s+(\d+)\s+days?\b", t)
    if m:
        return (today + datetime.timedelta(days=int(m.group(1)))).isoformat()

    return None


def _fmt_dt(dt) -> str:
    """Format fast-flights SimpleDatetime.

    Google omits trailing zero fields, so date/time lists may be short
    (e.g. time=[3] means 03:00). Pad before unpacking.
    """
    try:
        d = (list(dt.date) + [1, 1, 1])[:3]
        t = (list(dt.time) + [0, 0])[:2]
        return f"{d[0]:04d}-{d[1]:02d}-{d[2]:02d} {t[0]:02d}:{t[1]:02d}"
    except Exception:
        return str(dt)


def _fmt_duration(minutes) -> str:
    try:
        return f"{minutes // 60}h{minutes % 60:02d}m"
    except Exception:
        return str(minutes)


def _format_flight(f) -> str:
    legs = getattr(f, "flights", []) or []
    airlines = ", ".join(getattr(f, "airlines", []) or []) or "Unknown"
    price = getattr(f, "price", "?")
    if not legs:
        return f"{airlines} | {price} {CURRENCY}"

    first, last = legs[0], legs[-1]
    stops = len(legs) - 1
    stops_txt = "nonstop" if stops == 0 else f"{stops} stop(s)"
    total_min = sum(getattr(l, "duration", 0) or 0 for l in legs)

    return (
        f"{airlines}"
        f" | {first.from_airport.code} {_fmt_dt(first.departure)}"
        f" -> {last.to_airport.code} {_fmt_dt(last.arrival)}"
        f" | {stops_txt} | {_fmt_duration(total_min)} | {price} {CURRENCY}"
    )


def search_flights(
    destination: str,
    origin: str = None,
    departure_date: str = None,
    adults: int = 1,
    limit: int = 5,
) -> str:
    """Search flights (schedule + price) from Google Flights via fast-flights.

    `origin` / `destination` accept an IATA code, city, or country name, or a
    full sentence like "Plan a trip from Bangalore to Udaipur".
    `departure_date` is YYYY-MM-DD; defaults to ~2 weeks out. No API key needed.
    """
    # Destination may be a full sentence ("Plan a trip from X to Y") -> parse it.
    raw_text = destination
    if origin is None or resolve_airport(destination) is None:
        parsed_origin, parsed_dest = parse_trip_text(destination)
        origin = origin or parsed_origin
        destination = parsed_dest or destination

    origin = origin or DEFAULT_ORIGIN_IATA
    dep_iata = resolve_airport(origin)
    arr_iata = resolve_airport(destination)

    if not dep_iata:
        return f"Could not resolve origin airport for '{origin}'."
    if not arr_iata:
        return f"Could not resolve destination airport for '{destination}'."

    # Date from explicit arg, else parsed from the request ("tomorrow"), else default.
    dep_date = departure_date or extract_date(raw_text) or _default_departure_date()

    # Google Flights via fast-flights. Its parser crashes (IndexError) on routes
    # it can't handle (small airports, connecting-only) -> fall back to web search.
    flights = []
    try:
        query = create_query(
            flights=[
                FlightQuery(date=dep_date, from_airport=dep_iata, to_airport=arr_iata)
            ],
            trip="one-way",
            seat="economy",
            passengers=Passengers(adults=adults),
            currency=CURRENCY,
        )
        flights = list(get_flights(query))
    except Exception:
        flights = []

    if not flights:
        return _flight_web_fallback(dep_iata, arr_iata, dep_date)

    lines = [f"Flights {dep_iata} -> {arr_iata} on {dep_date}:"]
    for i, f in enumerate(flights[:limit], 1):
        lines.append(f"{i}. {_format_flight(f)}")
    return "\n".join(lines)


def _flight_web_fallback(dep_iata: str, arr_iata: str, dep_date: str) -> str:
    """Google Flights scraper failed/empty -> web-search the route via Tavily."""
    header = (
        f"No live fares parsed for {dep_iata} -> {arr_iata} on {dep_date} "
        f"(route not covered by the Google Flights scraper). Web results:"
    )
    try:
        from tools.tavily_tool import tavily_search
        web = tavily_search(
            f"flights {dep_iata} to {arr_iata} on {dep_date} price and schedule"
        )
    except Exception as e:
        return f"{header}\n(web fallback unavailable: {e})"
    return f"{header}\n{web}"


if __name__ == "__main__":
    print(search_flights("Plan a 7 days trip from Bangalore to Udaipur"))
    print("\n" + "=" * 80 + "\n")
    print(search_flights("Delhi", origin="Mumbai"))