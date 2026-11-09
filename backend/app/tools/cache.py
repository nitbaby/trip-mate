"""TTL cache in SQLite `api_cache` (LIVE-06). Every payload gets last_updated (LIVE-05)."""
import json
from datetime import UTC, datetime

from ..db import connect

TTL = {"flight": 300, "weather": 1800, "places": 900, "fx": 3600}


def cached(key: str, ttl: int, fetch, *, force: bool = False) -> dict:
    """Return fetch() result with `last_updated` and `cached` flags. On fetch failure, serve stale if present."""
    now = datetime.now(UTC)
    with connect() as c:
        row = c.execute("SELECT * FROM api_cache WHERE key=?", (key,)).fetchone()
        if row and not force:
            age = (now - datetime.fromisoformat(row["fetched_at"])).total_seconds()
            if age < row["ttl_seconds"]:
                return {**json.loads(row["payload"]), "last_updated": row["fetched_at"], "cached": True,
                        "stale": False}
        try:
            payload = fetch()
        except Exception as e:
            if row:  # serve stale rather than fail
                return {**json.loads(row["payload"]), "last_updated": row["fetched_at"], "cached": True,
                        "stale": True, "warning": f"live lookup failed: {type(e).__name__}"}
            raise
        ts = now.isoformat(timespec="seconds")
        c.execute("INSERT OR REPLACE INTO api_cache VALUES (?,?,?,?)", (key, json.dumps(payload), ts, ttl))
        return {**payload, "last_updated": ts, "cached": False, "stale": False}


def last_contacted() -> dict[str, str | None]:
    """Most recent fetch time per integration prefix (for the status endpoint, SET-01)."""
    out = {}
    with connect() as c:
        for p in TTL:
            r = c.execute("SELECT MAX(fetched_at) m FROM api_cache WHERE key LIKE ?", (p + ":%",)).fetchone()
            out[p] = r["m"]
    return out
