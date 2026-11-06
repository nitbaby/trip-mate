from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import errors
from .config import get_settings
from .routes import documents, itinerary, trips

app = FastAPI(title="TripMate API", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
                   allow_methods=["*"], allow_headers=["*"])
errors.install(app)
for r in (trips.router, documents.router, itinerary.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    s = get_settings()
    return {"ok": True, "live_mode": s.live_mode, "anthropic_configured": bool(s.anthropic_api_key)}
