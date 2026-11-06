# TripMate MVP Implementation Plan

Source of truth for *what* to build: `docs/tripmate_spec.md` (requirement IDs, API, data model) and `docs/tripmate_overview.md`.
This file is the *how/when* and the running status. **Update the status checkboxes and "Decisions/Notes" as work proceeds.**

Assumption: one developer working with Claude (not the spec's team of 4–5), so phases are ordered to reach a demo early.

## Repo layout (single git repo, root = this folder)
```
backend/     FastAPI: REST + SSE, agent loop, RAG, confidence, trip services, MCP client  (package `app`)
mcp-server/  Python MCP server: search_docs, read/write_itinerary, live-data tools (imports backend `app` for DB/vectors)
web/         React + Vite + TS + Tailwind PWA
samples/     fake hotel confirmation, flight itinerary, Japan medication rules, etc.
eval/        30–50 question eval set + runner
e2e/         Playwright tests (phone viewport) for the 5 demo flows
scripts/     dev, seed, demo-reset helpers
docs/        spec, overview, this plan
```

## Decisions (made, don't relitigate)
| Topic | Choice |
|---|---|
| Vector store | Chroma (persistent, `data/chroma`) |
| Embeddings | Local `fastembed` (BAAI/bge-small-en-v1.5); `EMBEDDINGS=hash` for offline tests only |
| LLM | Claude via Anthropic SDK tool use; model id from `ANTHROPIC_MODEL` env (default `claude-sonnet-5-5`) |
| API key | `ANTHROPIC_API_KEY` in root `.env` (gitignored). Never read/print/commit it. |
| Weather / Places / FX | Open-Meteo / OpenStreetMap (Overpass+Nominatim) / frankfurter.app — no keys |
| Flights | **Mock provider** behind a provider interface (user-approved). Real AviationStack optional later. |
| Demo safety | `LIVE_MODE=mock|real`; mock uses recorded fixtures so the demo works offline / without quotas |
| Test/demo target | **Desktop Chrome** (phone emulation at 375px). iOS/Android real-device install is out of scope for now. |
| Python | 3.12, root `.venv`, `pip install -e backend[dev]`; no `uv`. Node 20 + pnpm/npm available. |
| DB | stdlib `sqlite3` with row dicts (no ORM), schema in `backend/app/db.py` |
| Storage | `data/` (gitignored): `tripmate.db`, `uploads/<docId>/`, `chroma/` |

## Phases and status
- [x] **Phase 0 – Scaffold**: git init, folders, Makefile, `.env.example`, README, docs moved.
- [x] **Phase 1 – Backend core** (commit 46fa205): trips + itinerary CRUD (conflict detection, `source=agent`), document upload + background ingestion (parse → chunk → classify → key facts → masking → Chroma), reveal endpoint (DOC-06), chunk/Source Drawer endpoint. 7 tests passing (`make test`).
- [ ] **Phase 2 – RAG, confidence, agent**
  - `samples/` documents (hotel confirmation w/ check-out + breakfast, flight itinerary, Japan medication rules).
  - `search_docs` + confidence level (high/low/none from top score + agreement); thresholds tuned later with eval set.
  - Agent loop with Claude tool use: max 6 tools/turn, 30 external calls/session; SSE `POST /api/trips/{id}/chat` emitting the `ChatEvent` types in spec §5.2 (token, tool_start, tool_result, citation, confidence, verify, itinerary_updated, error, done); persist conversations/messages.
  - Guardrails per spec §7.2: citation or low-confidence; verify event for visa/medication/customs/currency; "I couldn't find it" + official-source suggestion.
  - Exit: demo flows 1 (check-out/breakfast) and 3 (medication + verify badge) work via curl; tests use a fake Claude client.
- [ ] **Phase 3 – MCP server + live tools**
  - MCP server in `mcp-server/` exposing `search_docs`, `read_itinerary`, `write_itinerary` (sets `source=agent`), `get_flight_status`, `get_weather`, `search_places`, `convert_currency`; backend uses an MCP client.
  - `api_cache` TTL caching, last-updated timestamps, mock/real providers, `GET /api/trips/{id}/places`, `GET /api/trips/{id}/status` (integration health), undo support for agent writes.
  - Exit: flows 2, 4, 5 work via curl.
- [ ] **Phase 4 – PWA front end** (`web/`): 375px phone-first. Screens: Trips/Create, Docs (status, masked fact cards, 30s reveal), Chat (streaming, citation chips, Source Drawer, tool cards, low-confidence + verify banners, quick actions, stop/retry), Itinerary (timeline opening on today, bottom-sheet edit, conflict warning, "Added by TripMate" badge + 10s Undo toast), Settings (integration status, units/currency, privacy note). Map is a stretch goal (first thing cut).
- [ ] **Phase 5 – Offline + PWA**: manifest/icons/installable, service worker app shell, Dexie caches (itinerary, masked docs + chunks for keyword search, last 100 chat msgs, last live responses labeled stale). Offline write queue only if time allows (second cut).
- [ ] **Phase 6 – Hardening + demo-ready**: Playwright E2E for the 5 flows at phone viewport (mock mode, plus real where possible); eval set + runner and threshold tuning; a11y pass (44px targets, live region, reduced motion, dark mode after 8PM/system); `make seed`/`make demo` reset; demo script + README; short recorded walkthrough.

## Definition of done
- 5 flows (spec §9) pass E2E.
- Installable and app shell works in airplane mode.
- Every factual answer has a citation or low-confidence banner.
- Agent writes are badged and undoable.
- `make dev` runs everything from a fresh clone with only the Anthropic key set.

## Scope cuts (in order) and never-cut
Cut order: map → offline writes → simplified Docs screen → simplified Source Drawer.
Never cut: citations, confidence/verify behavior, itinerary agent writes with undo, the five demo flows.

## Risks
PDF parsing quality (samples are mostly text); confidence thresholds need eval tuning; first fastembed run downloads a model (needs network once); PWA install requires localhost or HTTPS (localhost is fine for desktop Chrome).

## Working conventions
- Commit at the end of each phase (and sensible sub-steps). Commits end with: `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.
- Tests: `make test` (backend). Add tests with each feature; use fake Claude client + `EMBEDDINGS=hash` so tests need no network or key.
- Keep logs free of raw document text; sensitive values only leave the server via the reveal endpoint.

## Decisions/Notes log
- (append here as work proceeds)
