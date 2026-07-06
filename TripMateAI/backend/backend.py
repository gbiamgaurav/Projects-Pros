
import os
import sys
import certifi
from dotenv import load_dotenv

# Ensure the project root is importable so `tools` resolves regardless of the
# current working directory (e.g. `python3 backend/backend.py` or from inside backend/).
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

load_dotenv()

os.environ["SSL_CERT_FILE"] = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

# --- Logging (console + rotating file at logs/tripmate.log) ----------------
import logging
from logging.handlers import RotatingFileHandler

_LOG_DIR = os.path.join(_PROJECT_ROOT, "logs")
os.makedirs(_LOG_DIR, exist_ok=True)

if not logging.getLogger().handlers:
    _fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _file = RotatingFileHandler(
        os.path.join(_LOG_DIR, "tripmate.log"), maxBytes=2_000_000, backupCount=5
    )
    _file.setFormatter(_fmt)
    _stream = logging.StreamHandler()
    _stream.setFormatter(_fmt)
    logging.basicConfig(level=logging.INFO, handlers=[_file, _stream])

logger = logging.getLogger("tripmate.backend")

from typing import TypedDict, Annotated
import operator
import uuid 
import psycopg
from psycopg.rows import dict_row
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver
from langchain_core.messages import (
    AnyMessage,
    HumanMessage,
    AIMessage,
    SystemMessage
)

from langchain_google_genai import ChatGoogleGenerativeAI
from tools.tavily_tool import * 
from tools.flight_tool import * 
from tools.train_tool import * 

def get_database_url():
    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise ValueError(
            "DATABASE_URL is missing. Please add your Render PostgreSQL External Database"
        )
    
    if "sslmode=" not in database_url:
        separator = "&" if "?" in database_url else "?"
        database_url = f"{database_url}{separator}sslmode=require"

    return database_url


GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY is missing. Please add it to your .env file.")

llm = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash-lite",
)


# State

class TravelState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    user_query: str 
    flight_results: str
    hotel_results: str
    train_results: str
    itinerary: str
    llm_calls: int



# Flight Agent

def flight_agent(state: TravelState):
    query = state["user_query"]
    logger.info("[flight_agent] searching flights for: %s", query)
    flight_data = search_flights(query)
    logger.info("[flight_agent] got %d chars", len(flight_data or ""))
    return {"flight_results": flight_data}


# Train Agent

def train_agent(state: TravelState):
    query = state["user_query"]
    logger.info("[train_agent] searching trains for: %s", query)
    train_data = search_trains(query)
    logger.info("[train_agent] got %d chars", len(train_data or ""))
    return {"train_results": train_data}


# Hotel Agent

def hotel_agent(state: TravelState):
    query = f"Best hotels for {state['user_query']}"
    logger.info("[hotel_agent] searching hotels for: %s", state["user_query"])
    hotel_results = tavily_search(query)
    logger.info("[hotel_agent] got %d chars", len(hotel_results or ""))
    return {"hotel_results": hotel_results}


# Planner prompt (single LLM call replaces the old itinerary + final agents).
# The LLM synthesis is done OUTSIDE the graph so the endpoint can stream it.

_PLANNER_SYSTEM = "You are a professional AI travel booking assistant."


def build_planner_messages(
    user_query, flight_results, train_results, hotel_results, history=""
):
    """One prompt: itinerary + formatted final answer in a single LLM call.

    `history` is prior-turn context so follow-ups ("make it cheaper", "add a
    day") remember the earlier trip.
    """
    history_block = (
        f"\nPrevious conversation (for context, honour earlier details like "
        f"group size, dates, budget):\n{history}\n" if history else ""
    )
    prompt = f"""
You are answering the user's CURRENT request below. Use the search data and,
if present, the earlier conversation for context only.
{history_block}
Current User Request:
{user_query}

Flights:
{flight_results}

Trains:
{train_results}

Hotels:
{hotel_results}

CRITICAL RULES — follow exactly:
    - The CURRENT request wins. If it conflicts with anything earlier
      (duration, budget, mode of transport), obey the current request.
    - TRIP DURATION: use exactly the number of days the user states. If they
      say "2 days", produce a 2-day itinerary — never more. If no duration is
      given, use 2-3 days and say it's a suggestion. NEVER invent 7 days.
    - Do NOT confuse GROUP SIZE with days. "family of 7 persons" means 7
      travellers, NOT a 7-day trip.
    - ANSWER THE ACTUAL QUESTION. If the user only asks a narrow thing (e.g.
      "flight ticket prices", "best trains"), answer that directly and briefly.
      Do NOT dump a full 7-section itinerary for a one-line question.
    - For a full trip-planning request, you may use these sections as a guide,
      including only the ones that are relevant:
      Trip Summary · Flights · Trains · Hotels · Day-by-Day Itinerary ·
      Estimated Budget · Final Recommendations.
    - Be practical, budget-aware, and concise. Prefer the real search data
      over generic advice.
"""
    return [
        SystemMessage(content=_PLANNER_SYSTEM),
        HumanMessage(content=prompt),
    ]


# Build Graph — the 3 tool agents run in PARALLEL (fan-out from START, fan-in
# at END). They're independent (all read user_query, write different keys), so
# concurrent execution replaces the old ~7s sequential chain with ~max(4,1,2)s.

graph = StateGraph(TravelState)

graph.add_node("flight_agent", flight_agent)
graph.add_node("hotel_agent", hotel_agent)
graph.add_node("train_agent", train_agent)

graph.add_edge(START, "flight_agent")
graph.add_edge(START, "train_agent")
graph.add_edge(START, "hotel_agent")
graph.add_edge("flight_agent", END)
graph.add_edge("train_agent", END)
graph.add_edge("hotel_agent", END)


# PostgreSQL Checkpointer

DATABASE_URL = get_database_url()

_conn = psycopg.connect(
    DATABASE_URL,
    autocommit=True,
    row_factory=dict_row
)


checkpointer = PostgresSaver(_conn)
checkpointer.setup()

travel_graph = graph.compile(checkpointer=checkpointer)


# --- Conversation memory (per thread, via the checkpointer) ----------------

_HISTORY_TURNS = 4          # how many recent Q/A pairs to feed back
_ANSWER_CLIP = 1200         # cap each stored answer in the prompt to stay small


def _thread_config(thread_id):
    return {"configurable": {"thread_id": thread_id}}


def load_history(thread_id):
    """Return prior turns as a 'User: … / Assistant: …' string (or '')."""
    try:
        state = travel_graph.get_state(_thread_config(thread_id))
    except Exception:
        return ""
    msgs = (state.values or {}).get("messages", []) if state else []
    if not msgs:
        return ""

    lines = []
    for m in msgs[-(_HISTORY_TURNS * 2):]:
        role = getattr(m, "type", "")
        content = (getattr(m, "content", "") or "").strip()
        if not content:
            continue
        if role == "human":
            lines.append(f"User: {content}")
        elif role == "ai":
            lines.append(f"Assistant: {content[:_ANSWER_CLIP]}")
    return "\n".join(lines)


def save_turn(thread_id, question, answer):
    """Append this turn's question + answer to the thread's persisted history.

    as_node is required because the graph fans out to 3 parallel nodes, so an
    unattributed update is ambiguous. Any real node works — the messages reducer
    (operator.add) just appends.
    """
    try:
        travel_graph.update_state(
            _thread_config(thread_id),
            {"messages": [HumanMessage(content=question), AIMessage(content=answer)]},
            as_node="flight_agent",
        )
    except Exception:
        logger.exception("[memory] failed to save turn for thread=%s", thread_id)


