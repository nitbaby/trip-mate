from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import errors
from .agent.hub import McpHub
from .config import get_settings
from .routes import chat, documents, itinerary, live, trips


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.hub = McpHub()  # MCP tool server starts lazily on the first chat
    app.state.llm = None      # tests inject a scripted fake here
    yield
    await app.state.hub.aclose()


app = FastAPI(title="TripMate API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])
errors.install(app)
for r in (trips.router, documents.router, itinerary.router, live.router, chat.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    s = get_settings()
    return {"ok": True, "live_mode": s.live_mode, "anthropic_configured": bool(s.anthropic_api_key)}
