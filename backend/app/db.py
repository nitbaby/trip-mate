import json
import sqlite3
import uuid
from datetime import UTC, datetime

from .config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS trips (
  id TEXT PRIMARY KEY, name TEXT NOT NULL, destinations TEXT NOT NULL,
  start_date TEXT NOT NULL, end_date TEXT NOT NULL, timezone TEXT NOT NULL,
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS documents (
  id TEXT PRIMARY KEY, trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
  filename TEXT NOT NULL, doc_type TEXT, status TEXT NOT NULL, error TEXT,
  uploaded_at TEXT NOT NULL, key_facts TEXT NOT NULL DEFAULT '[]');
CREATE TABLE IF NOT EXISTS chunks (
  id TEXT PRIMARY KEY, document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
  page INTEGER NOT NULL, text TEXT NOT NULL, metadata TEXT NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS itinerary_items (
  id TEXT PRIMARY KEY, trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
  type TEXT NOT NULL, title TEXT NOT NULL, start_at TEXT NOT NULL, end_at TEXT,
  location TEXT, notes TEXT, source TEXT NOT NULL DEFAULT 'user', document_id TEXT);
CREATE TABLE IF NOT EXISTS conversations (
  id TEXT PRIMARY KEY, trip_id TEXT NOT NULL REFERENCES trips(id) ON DELETE CASCADE,
  created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS messages (
  id TEXT PRIMARY KEY, conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
  role TEXT NOT NULL, content TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS undo_log (
  id TEXT PRIMARY KEY, trip_id TEXT NOT NULL, action TEXT NOT NULL, item_id TEXT NOT NULL,
  before TEXT, created_at TEXT NOT NULL, undone INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS usage (
  conversation_id TEXT PRIMARY KEY, external_calls INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS api_cache (
  key TEXT PRIMARY KEY, payload TEXT NOT NULL, fetched_at TEXT NOT NULL, ttl_seconds INTEGER NOT NULL);
"""


def new_id() -> str:
    return uuid.uuid4().hex[:12]


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(get_settings().db_path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def row_to_dict(row: sqlite3.Row | None, json_fields: tuple[str, ...] = ()) -> dict | None:
    if row is None:
        return None
    d = dict(row)
    for f in json_fields:
        if f in d and isinstance(d[f], str):
            d[f] = json.loads(d[f])
    return d
