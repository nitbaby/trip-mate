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
| Embeddings | `EMBEDDINGS=onnx` (default): Chroma's bundled all-MiniLM-L6-v2, downloads once from AWS S3 to `~/.cache/chroma`. `fastembed` needs huggingface.co (blocked on this network). `hash` = tests only. |
| LLM | **Gemini (default)** via Google's OpenAI-compatible endpoint, free tier, no card; `LLM_PROVIDER=gemini|openai|anthropic` in `.env`. `openai` covers Groq/OpenRouter/Ollama etc. Claude (Anthropic SDK) kept as an option. Adapters in `backend/app/agent/llm.py`; Anthropic-shaped blocks are the canonical internal format. |
| API key | `GEMINI_API_KEY` (or the key for the chosen provider) in root `.env` (gitignored). Never read/print/commit it. Check with `scripts/llm_check.py`. |
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
- [x] **Phase 2 – RAG, confidence, agent** (code + tests done with a scripted fake Claude; **live Claude run still pending: the key in `.env` returned 401 invalid x-api-key on 2026-11-10**. Original note: Build the agent on `app/mcp_client.py`: `McpToolClient().list_tools()` already returns Anthropic tool format; inject `trip_id` into tool args server-side. Samples already exist in `samples/`.)
  - `samples/` documents (hotel confirmation w/ check-out + breakfast, flight itinerary, Japan medication rules).
  - `search_docs` + confidence level (high/low/none from top score + agreement); thresholds tuned later with eval set.
  - Agent loop with Claude tool use: max 6 tools/turn, 30 external calls/session; SSE `POST /api/trips/{id}/chat` emitting the `ChatEvent` types in spec §5.2 (token, tool_start, tool_result, citation, confidence, verify, itinerary_updated, error, done); persist conversations/messages.
  - Guardrails per spec §7.2: citation or low-confidence; verify event for visa/medication/customs/currency; "I couldn't find it" + official-source suggestion.
  - Exit: demo flows 1 (check-out/breakfast) and 3 (medication + verify badge) work via curl; tests use a fake Claude client.
- [x] **Phase 3 – MCP server + live tools** (done before Phase 2; no dependency on the agent loop. `search_docs` returns raw scores; the confidence level is added in Phase 2.)
  - MCP server in `mcp-server/` exposing `search_docs`, `read_itinerary`, `write_itinerary` (sets `source=agent`), `get_flight_status`, `get_weather`, `search_places`, `convert_currency`; backend uses an MCP client.
  - `api_cache` TTL caching, last-updated timestamps, mock/real providers, `GET /api/trips/{id}/places`, `GET /api/trips/{id}/status` (integration health), undo support for agent writes.
  - Exit: flows 2, 4, 5 work via curl.
- [x] **Phase 4 – PWA front end** (`web/`; built + visually verified in Chrome at 375px; offline/install is Phase 5): 375px phone-first. Screens: Trips/Create, Docs (status, masked fact cards, 30s reveal), Chat (streaming, citation chips, Source Drawer, tool cards, low-confidence + verify banners, quick actions, stop/retry), Itinerary (timeline opening on today, bottom-sheet edit, conflict warning, "Added by TripMate" badge + 10s Undo toast), Settings (integration status, units/currency, privacy note). Map is a stretch goal (first thing cut).
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
- 2026-11-10 Default Gemini model is now `gemini-3.5-flash-lite` (user request; better rate limits). Live test: check-out/breakfast and flight-delay flows were correct, cited and ~7 s each (vs 25-44 s for 3.5-flash); the remaining flows (medication, places, itinerary add, not-found) were NOT verified because the key's Google project then returned **402 "prepayment credits are depleted"** for every model (the project is on prepaid billing, not free tier). Needs a top-up or a key from a free-tier project, then re-run the 6 questions. 402 now maps to a clear user-facing message.
- 2026-11-10 **Phase 4 built** (`web/`, React 19 + Vite 8 + Tailwind 4 + TanStack Query + React Router; no zustand/Leaflet): trips list/create, tab layout (Chat, Itinerary, Docs, Settings), SSE chat client (`lib/sse.ts` parser, `lib/chatReducer.ts` pure event folding, `lib/useChat.ts`), streaming answers with citation chips -> Source Drawer, collapsed tool cards, low-confidence + verify banners, stop/retry, quick actions, suggested prompts from the trip's docs, undo toast (10 s), itinerary timeline opening on today with bottom-sheet CRUD / conflict warning / "Added by TripMate" badge, docs with status polling + masked fact cards + 30 s reveal, settings (integration status, units/currency/language/theme, privacy note), dark mode after 8 PM or system dark, aria-live announces each finished answer once. 14 vitest tests; `e2e/shots.mjs` drives the real UI via system Chrome and saves screenshots. Map screen NOT built (stretch, first cut).
  - Env gotchas: web needs **Node 22** (`web/.nvmrc`; Vite 8/Vitest 5 fail on 20.15). `web/.npmrc` and `e2e/.npmrc` point at registry.npmjs.org because the corporate Artifactory login expired. npm bug: lockfile missed the macOS arm64 rolldown binding, so `@rolldown/binding-darwin-arm64` is an optional dependency. Test env is happy-dom (jsdom 31 needs newer Node).
  - Backend additions: `preferences` (units/currency/language, validated) in the chat body -> system prompt; `LLM_PROVIDER=demo` (`app/agent/demo_llm.py`): deterministic rule-based stand-in, NOT an AI, so UI/E2E/demos need no key, network or rate limit. Use it for Phase 6 E2E. Fixed Breakfast fact truncation.
- 2026-11-10 **Live Gemini run** (gemini-3.5-flash, reasoning_effort=low, real onnx embeddings, samples uploaded): flows 1-5 and a not-in-docs question all worked with correct answers, citations, verify badge, undo id. Findings: `gemini-2.5-flash` is retired for new users (404 "no longer available"), `gemini-flash-latest` hangs, `gemini-3.8-flash` returned 503 high demand, `gemini-3.1-flash-lite` is faster per call but missed the flight number and the places search (worse tool use), so default = `gemini-3.5-flash`. Latency is 20-44 s per question: backend/tools are fast (MCP spawn 1.6 s, search_docs 0.03-0.3 s); the time is Gemini free-tier latency (4-8 s per call x 2-4 calls) plus occasional 429/503 retries. Free-tier rate limit (429) was hit after ~25 requests. Mitigations to consider in Phase 4/6: show tool-progress cards immediately (already streamed), fewer round trips (prompt nudged), pre-recorded/cached demo answers, or a paid/other provider. Fixed: mock places ignored generic query words ("vegetarian restaurant" returned 0); itinerary writes no longer emit a confidence banner; 60 s request timeout.
- 2026-11-10: the Anthropic key in `.env` was rejected (401 invalid x-api-key) and the user has no working Claude key, so the default LLM is now Gemini (free tier). `OpenAICompatLLM` streams chat completions, accumulates tool calls (name = start of a new call; handles missing ids/indexes), echoes `extra_content` (Gemini thought signatures) back, sanitizes tool schemas (Gemini rejects `anyOf` null/`title`/`default`), maps errors to user-facing `LLMError`. **Not yet run against live Gemini** (no key yet); tested with a mock streaming server (14 tests). Free-tier caveat: prompts may be retained/trained on, so use only fake sample data. Default model `gemini-2.5-flash` may need changing; run `scripts/llm_check.py --models`.
- 2026-11-10 Phase 2 built: chunking is now paragraph-level (max 450 chars) with `scripts/reindex.py` to re-ingest existing docs; `app/confidence.py` (thresholds in config: high 0.45, agree 0.35, low 0.25, calibrated on samples; irrelevant queries scored <=0.14, relevant >=0.43) and `search_docs` now returns `confidence` plus only passages >= conf_low; `app/agent/` (`loop.py`, `llm.py`, `hub.py` long-lived MCP subprocess, `guardrails.py`, `prompt.py`); `POST /api/trips/{id}/chat` (SSE) and `GET /api/trips/{id}/conversations/{cid}/messages`. Backend injects `trip_id` into tools (hidden from the model), numbers passages as [n], emits citation events only for markers the model used, downgrades confidence to low when nothing is cited, emits verify for visa/medication/customs/currency, caps 6 tools/turn and 30 external calls/conversation (table `usage`). Spec deviation: `itinerary_updated` event also carries `undoId` (needed for the Undo toast). `scripts/chat_cli.py` is a terminal chat client. 37 tests (fake LLM in `tests/fakes.py`).
- Tests are pinned to mock mode and hash embeddings regardless of `.env`.
- 2026-11-10: bug: relative `TRIPMATE_DATA_DIR=./data` resolved against cwd, so backend (cwd `backend/`) and scripts (repo root) used different DBs. Now anchored to repo root. Also `search_docs` and the chunk endpoint now redact sensitive values (passport/booking ref/card) before text reaches the model or browser; Phase 2 must keep sending only redacted text to Claude.
- 2026-11-09 Phase 3 built: `app/tools/` (flights mock-only, weather Open-Meteo, places mock fixtures / Nominatim, fx Frankfurter, TTL `api_cache` with stale-on-failure), `app/services/itinerary.py` (shared by REST and tools; `agent_write` sets source=agent and logs undo), `POST /api/trips/{id}/undo/{undoId}`, `GET /api/trips/{id}/places`, `GET /api/trips/{id}/status`, `mcp-server/tripmate_mcp/server.py` (FastMCP stdio, 7 tools; pinned `mcp<2`), `app/mcp_client.py` (forwards only TRIPMATE_DATA_DIR/LIVE_MODE/EMBEDDINGS env to the subprocess, never the API key). Real mode verified for weather + fx; real places is Nominatim only (no ratings/hours/diet filter; Overpass is unreachable here). Mock flight JL44 is delayed 35 min (demo flow 2). 17 tests.
- 2026-11-09: huggingface.co and GCS return 403 on this network, so fastembed ingestion failed (`Could not load model ... from any source`). Switched default to Chroma ONNX MiniLM (S3 reachable). Existing `.env` files must set `EMBEDDINGS=onnx`.
- 2026-11-09: added `samples/` docs; fixed booking-reference masking regex bug found by uploading them.
- Repo moved to `/Users/A-7878/Learning/trip-mate`. Remote `origin` = github.com/nitbaby/trip-mate; first push failed with 403 'account suspended' (unresolved).
