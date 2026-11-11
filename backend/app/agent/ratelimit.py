"""Client-side limits for the LLM API: requests per minute (shared by every agent in the app) and per day.

Why: a free tier allows e.g. 15 requests/min and 500/day, and one multi-agent question can need up to 5 requests,
several of them in parallel. We queue calls instead of letting them fail with 429, tell the UI when we are waiting,
and stop with a clear message when the daily budget is spent."""
import math
import re
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from zoneinfo import ZoneInfo

from ..config import Settings
from ..db import connect


@dataclass(frozen=True)
class Limits:
    rpm: int            # 0 = unlimited
    daily: int          # 0 = unlimited
    tz: str
    max_wait: float
    model_key: str      # quotas are counted per provider+model (Google's free-tier limits are per model)


def resolve_limits(s: Settings) -> Limits | None:
    rpm, daily = s.llm_max_rpm, s.llm_daily_limit
    if s.llm_provider == "gemini":
        rpm = 12 if rpm < 0 else rpm
        daily = 500 if daily < 0 else daily
    rpm, daily = max(rpm, 0), max(daily, 0)
    if not rpm and not daily:
        return None
    model = s.gemini_model if s.llm_provider == "gemini" else s.llm_model
    return Limits(rpm, daily, s.llm_quota_tz, float(s.llm_max_wait_seconds), f"{s.llm_provider}:{model}")


class TooLong(Exception):
    def __init__(self, seconds: float):
        super().__init__(f"would wait {seconds:.0f}s")
        self.seconds = seconds


class RateLimiter:
    """Sliding window. reserve() is synchronous (no await), so concurrent agents can't race for the same slot."""

    def __init__(self, rpm: int, window: float = 60.0, clock=time.monotonic):
        self.rpm, self.window, self.clock = rpm, window, clock
        self.stamps: deque[float] = deque()

    def reserve(self, max_wait: float) -> float:
        """Claim the next free slot and return how long to wait for it. Raises TooLong (and claims nothing)."""
        now = self.clock()
        while self.stamps and self.stamps[0] <= now - self.window:
            self.stamps.popleft()
        if len(self.stamps) < self.rpm:
            self.stamps.append(now)
            return 0.0
        slot = self.stamps[-self.rpm] + self.window
        wait = max(0.0, slot - now)
        if wait > max_wait:
            raise TooLong(wait)
        self.stamps.append(now + wait)
        return wait


_limiters: dict[tuple[str, int], RateLimiter] = {}


def limiter_for(key: str, rpm: int) -> RateLimiter:
    """One limiter per model for the whole process (the adapter is rebuilt for every chat request)."""
    return _limiters.setdefault((key, rpm), RateLimiter(rpm))


# ---------- daily budget (persisted, so it survives restarts) ----------

def day_key(tz: str, now: datetime | None = None) -> str:
    return (now or datetime.now(ZoneInfo(tz))).strftime("%Y-%m-%d")


def used_today(lim: Limits) -> int:
    with connect() as c:
        r = c.execute("SELECT requests FROM llm_usage WHERE day=? AND model_key=?", (day_key(lim.tz), lim.model_key)).fetchone()
        return r["requests"] if r else 0


def count_request(lim: Limits) -> int:
    with connect() as c:
        c.execute("""INSERT INTO llm_usage(day, model_key, requests) VALUES (?,?,1)
                     ON CONFLICT(day, model_key) DO UPDATE SET requests = requests + 1""", (day_key(lim.tz), lim.model_key))
        return c.execute("SELECT requests FROM llm_usage WHERE day=? AND model_key=?", (day_key(lim.tz), lim.model_key)).fetchone()["requests"]


def hours_until_reset(tz: str) -> int:
    now = datetime.now(ZoneInfo(tz))
    midnight = (now.replace(hour=0, minute=0, second=0, microsecond=0)).timestamp() + 86400
    return max(1, math.ceil((midnight - now.timestamp()) / 3600))


def quota_status(s: Settings) -> dict | None:
    lim = resolve_limits(s)
    if not lim or not lim.daily:
        return None
    return {"used": used_today(lim), "limit": lim.daily, "rpm": lim.rpm, "model": lim.model_key}


# ---------- reading the provider's own 429 hints ----------

def retry_after_seconds(headers, body_text: str) -> float | None:
    """Seconds the server asks us to wait: Retry-After header, or Gemini's RetryInfo "retryDelay": "23s"."""
    ra = headers.get("retry-after") if headers else None
    try:
        if ra:
            return float(ra)
    except ValueError:
        pass
    m = re.search(r'retryDelay"?\s*[:=]\s*"?(\d+(?:\.\d+)?)s', body_text or "")
    if m:
        return float(m.group(1))
    m = re.search(r"retry in (\d+(?:\.\d+)?)s", body_text or "", re.IGNORECASE)
    return float(m.group(1)) if m else None


def is_daily_exhausted(body_text: str) -> bool:
    return bool(re.search(r"PerDay|per day|daily", body_text or "", re.IGNORECASE))
