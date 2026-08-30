import sys
import uuid

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
if hasattr(sys.stderr, "reconfigure"):
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from fastapi import FastAPI, HTTPException

from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import agent, monday_client

app = FastAPI(title="Skylark BI Agent")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# In-memory session store: {session_id: [ {"role":..,"content":..}, ... ]}
# Fine for a single-instance prototype; see README for the swap-to-Redis note.
SESSIONS: dict[str, list] = {}


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None


class ChatResponse(BaseModel):
    reply: str
    session_id: str


@app.post("/chat", response_model=ChatResponse)
def chat(req: ChatRequest):
    session_id = req.session_id or str(uuid.uuid4())
    history = SESSIONS.get(session_id, [])
    history.append({"role": "user", "content": req.message})
    try:
        reply_text, api_messages = agent.run_agent_turn(history)
    except Exception as e:
        reply_text = f"The BI Agent encountered an API issue: {str(e)}. Please try again in a few seconds."
        api_messages = history
    SESSIONS[session_id] = api_messages
    return ChatResponse(reply=reply_text, session_id=session_id)



@app.post("/reset")
def reset(session_id: str):
    SESSIONS.pop(session_id, None)
    return {"ok": True}


@app.get("/health")
def health():
    ok = {
        "llm_provider": "gemini",
        "gemini_configured": bool(agent.config.GEMINI_API_KEY),
        "llm_configured": bool(agent.config.GEMINI_API_KEY),
        "monday": bool(agent.config.MONDAY_API_TOKEN),
    }

    try:
        boards = monday_client.get_boards()
        data_source = monday_client.get_last_data_source()
        ok["monday_reachable"] = (data_source == "live_monday_api")
        ok["data_source"] = data_source
        ok["boards"] = [{"id": b["id"], "name": b["name"], "items": b["items_count"]} for b in boards]
    except Exception as e:
        ok["monday_reachable"] = False
        ok["data_source"] = "unreachable"
        ok["monday_error"] = str(e)
    return ok




from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIR = BASE_DIR / "frontend"

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


@app.get("/")
def index():
    html_file = FRONTEND_DIR / "index.html"
    if html_file.exists():
        return FileResponse(str(html_file))
    return {"message": "Skylark BI Agent API running"}

