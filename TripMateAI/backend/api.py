import os
import sys
import json
import uuid
import time
import logging

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from langchain_core.messages import HumanMessage

# Ensure the project root is importable so `backend`/`tools` resolve regardless
# of the current working directory.
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from backend.backend import (
    travel_graph,
    llm,
    build_planner_messages,
    load_history,
    save_turn,
)

logger = logging.getLogger("tripmate.api")

app = FastAPI(title="TripMate AI")

app.mount(
    "/static",
    StaticFiles(directory=os.path.join(_PROJECT_ROOT, "static")),
    name="static",
)
templates = Jinja2Templates(directory=os.path.join(_PROJECT_ROOT, "templates"))


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None


def _gather(user_input: str, thread_id: str):
    """Run the parallel tool graph -> flight/train/hotel results.

    Note: we do NOT push the user message here — history is persisted via
    save_turn() so questions aren't stored twice.
    """
    config = {"configurable": {"thread_id": thread_id}}
    result = travel_graph.invoke(
        {
            "user_query": user_input,
            "flight_results": "",
            "train_results": "",
            "hotel_results": "",
            "itinerary": "",
            "llm_calls": 0,
        },
        config=config,
    )
    return {
        "flight_results": result.get("flight_results", ""),
        "train_results": result.get("train_results", ""),
        "hotel_results": result.get("hotel_results", ""),
    }


# --- Non-streaming (used by test.py / API clients) -------------------------

def run_travel_agent(user_input: str, thread_id: str | None = None):
    if not thread_id:
        thread_id = f"user_{uuid.uuid4().hex}"

    logger.info("[chat] thread=%s | QUESTION: %s", thread_id, user_input)
    started = time.time()

    history = load_history(thread_id)
    data = _gather(user_input, thread_id)
    messages = build_planner_messages(
        user_input, data["flight_results"], data["train_results"],
        data["hotel_results"], history,
    )
    answer = llm.invoke(messages).content
    save_turn(thread_id, user_input, answer)

    elapsed = time.time() - started
    logger.info(
        "[chat] thread=%s | done in %.1fs | answer=%d chars | history=%d chars",
        thread_id, elapsed, len(answer or ""), len(history),
    )
    logger.info("[chat] thread=%s | RESPONSE: %s", thread_id, answer)

    return {
        "thread_id": thread_id,
        "answer": answer,
        "llm_calls": 1,
        **data,
    }


# --- Streaming -------------------------------------------------------------

def stream_travel_agent(user_input: str, thread_id: str | None = None):
    """Yield a JSON meta line first, then the answer token-by-token.

    Wire format: line 1 = JSON metadata (thread_id + raw results) + '\\n',
    everything after = streamed markdown answer.
    """
    if not thread_id:
        thread_id = f"user_{uuid.uuid4().hex}"

    logger.info("[stream] thread=%s | QUESTION: %s", thread_id, user_input)
    started = time.time()

    history = load_history(thread_id)
    data = _gather(user_input, thread_id)

    meta = {"type": "meta", "thread_id": thread_id, **data}
    yield json.dumps(meta) + "\n"

    messages = build_planner_messages(
        user_input, data["flight_results"], data["train_results"],
        data["hotel_results"], history,
    )

    collected = []
    for chunk in llm.stream(messages):
        token = chunk.content or ""
        if token:
            collected.append(token)
            yield token

    answer = "".join(collected)
    save_turn(thread_id, user_input, answer)

    elapsed = time.time() - started
    logger.info(
        "[stream] thread=%s | done in %.1fs | answer=%d chars | history=%d chars",
        thread_id, elapsed, len(answer), len(history),
    )
    logger.info("[stream] thread=%s | RESPONSE: %s", thread_id, answer)


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(request, "index.html")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/chat")
def chat(req: ChatRequest):
    try:
        return run_travel_agent(req.message, req.thread_id)
    except Exception:
        logger.exception("[chat] failed for message: %s", req.message)
        raise


@app.post("/chat/stream")
def chat_stream(req: ChatRequest):
    return StreamingResponse(
        stream_travel_agent(req.message, req.thread_id),
        media_type="text/plain; charset=utf-8",
    )
