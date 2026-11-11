# TripMate manual test plan

How to check each module by hand: REST, MCP tools, RAG, Agent, UI, and how to look inside the Chroma store.
Automated tests (`make test`, `make test-web`) cover much of this; this plan is for a human at the keyboard.
Expected values below come from the fixtures in `samples/` and `LIVE_MODE=mock`.

Legend: **Expected** is what you should see. Tick the box when it matches. Anything that differs is a bug (or a doc fix): note the ID.

---

## 0. Test environment

Use a **separate stack** so your own data on :8000 / :5173 is never touched.

```bash
cd /Users/A-7878/Learning/trip-mate
export TD=/tmp/tm-manual                      # throwaway data dir (rm -rf $TD to reset)
# Backend on :8010. Pick ONE LLM:
cd backend
TRIPMATE_DATA_DIR=$TD LIVE_MODE=mock LLM_PROVIDER=demo ../.venv/bin/uvicorn app.main:app --port 8010          # demo stand-in (no AI, deterministic)
# TRIPMATE_DATA_DIR=$TD LIVE_MODE=mock ../.venv/bin/uvicorn app.main:app --port 8010                           # your .env LLM (Gemini or local)
# Web on :5180 (needs Node 22):
cd ../web && PATH=$HOME/.nvm/versions/node/v22.22.2/bin:$PATH VITE_API_TARGET=http://localhost:8010 npx vite --port 5180
```
Local model: `make local-llm` must be running on :8080 and your `.env` must point to it (README: "Run with a local model").
Seed a trip quickly: `.venv/bin/python scripts/demo_seed.py --with-itinerary` (prints the trip id; used as `$T` below).
Set `B=http://localhost:8010` and `T=<trip id>`.

Which LLM for which section: sections 1, 2, 3 need **no LLM**. Section 4 (Agent) needs a real model for meaningful answers; `demo` is enough to check plumbing (events, citations, undo).

---

## 1. REST endpoints

Base `$B`. Errors have the shape `{"error":{"code","message","retryable"}}`.

| ID | Step (curl) | Expected |
|---|---|---|
| R-01 | `curl $B/api/health` | `ok: true`, `live_mode`, `llm_provider`, `llm_configured` |
| R-02 | `curl -X POST $B/api/trips -H 'content-type: application/json' -d '{"name":"Tokyo Dec 2026","destinations":["Tokyo"],"start_date":"2026-11-30","end_date":"2026-12-06","timezone":"Asia/Tokyo"}'` | **201**, body has `id`, `itinerary: []`, `documents: []` on GET |
| R-03 | Same with `end_date` before `start_date` | **422** `VALIDATION_FAILED`, message mentions end_date |
| R-04 | Same with `destinations: []` or missing `name` | **422** `VALIDATION_FAILED` |
| R-05 | `GET $B/api/trips` and `GET $B/api/trips/$T` | list contains the trip; detail has `itinerary`, `documents` (with `key_facts`) |
| R-06 | `GET $B/api/trips/nope` | **404** `NOT_FOUND` |
| R-07 | Upload: `curl -F file=@samples/hotel_confirmation.txt $B/api/trips/$T/documents` | **202** `{id, filename, status:"queued"}` |
| R-08 | Poll `GET $B/api/trips/$T/documents/$D/status` every second | `queued` -> `processing` -> **`ready`** with `doc_type` (`confirmation`); `error: null` |
| R-09 | Upload the 3 other samples (`flight_itinerary.txt`, `japan_entry_rules.txt`, `tokyo_guide.md`) and the PDF `hotel_confirmation.pdf` | all reach `ready`; types: itinerary, rules, guide, confirmation |
| R-10 | Upload `x.exe` (unsupported) and an empty `.txt` | `.exe`: **422** `VALIDATION_FAILED` "Only PDF, TXT and MD files are supported". Empty file: 202, then status **`failed`** with `error: "No extractable text found in document"`. Never a 500. |
| R-11 | `GET $B/api/trips/$T` after R-09 | `documents[*].key_facts`: Check-in 3:00 PM, Check-out 11:00 AM, Hotel; sensitive ones (Passport number, Booking reference, Card number) have `sensitive: true` and **masked** values like `•••••••07` |
| R-12 | `GET $B/api/documents/$D/facts/<index of Passport>/reveal` | `{"value":"P48213907","reveal_seconds":30}` (raw value only here) |
| R-13 | `GET $B/api/documents/$D/chunks/$CHUNK` (take a chunk id from the RAG report, section 3.7) | `{chunk_id, document_name, page, text, surrounding:[...]}`; sensitive values masked in `text` and `surrounding` |
| R-14 | `POST $B/api/trips/$T/itinerary` `{"type":"reservation","title":"Dinner","start_at":"2026-12-02T20:00:00","end_at":"2026-12-02T21:30:00"}` | **201**, `source:"user"` |
| R-15 | Add `{"type":"activity","title":"Show","start_at":"2026-12-02T21:00:00","end_at":"2026-12-02T22:00:00"}`, then `GET .../itinerary` | list ordered by `start_at`; both items show `conflicts_with` pointing at each other |
| R-16 | `GET .../itinerary` with a date filter via the MCP tool (section 2) | only that day |
| R-17 | `PATCH .../itinerary/$ITEM` `{"title":"Late dinner"}` | 200, title changed; `DELETE` -> **204**, item gone |
| R-18 | `POST $B/api/trips/$T/undo/nope` | **404** `NOT_FOUND` "Undo entry not found" |
| R-19 | `GET $B/api/trips/$T/places?query=vegetarian&location=Shinjuku` | results with name, distance_m, rating, hours, open_now (mock: Tokyo fixtures) |
| R-20 | `GET $B/api/trips/$T/status` | `integrations`: flight, weather, places, fx with `mode` (mock) and `last_contacted`; `llm_limits` (Gemini only) |
| R-21 | Chat (SSE): `curl -N -X POST $B/api/trips/$T/chat -H 'content-type: application/json' -d '{"message":"What time is check-out?"}'` | `data:` lines with `agent_start`, `tool_start`, `tool_result`, `token`..., `citation`, `confidence`, `done` (`llmCalls`, `toolCalls`) |
| R-22 | `GET $B/api/trips/$T/conversations/$CID/messages` (CID from a previous chat, or pass `conversationId`) | the saved user/assistant messages in order |
| R-23 | `DELETE $B/api/trips/$T/documents/$D` | **204**; doc gone from the trip; its chunks gone from the RAG report (3.7) |
| R-24 | Chat for an unknown trip id | 404 `NOT_FOUND` |

---

## 2. MCP tool server

The 7 tools run in a stdio MCP server, the same code the agent calls. Poke them directly (no LLM):

```bash
TRIPMATE_DATA_DIR=$TD .venv/bin/python scripts/mcp_call.py                 # lists tools
TRIPMATE_DATA_DIR=$TD .venv/bin/python scripts/mcp_call.py <tool> '{json}'  # calls one
```
Add `LIVE_MODE=real` to try real providers. `trip_id` is a real tool parameter here (the agent hides it from the model).

| ID | Call | Expected (mock mode) |
|---|---|---|
| M-01 | no args | lists `search_docs, read_itinerary, write_itinerary, get_flight_status, get_weather, search_places, convert_currency` |
| M-02 | `search_docs {"trip_id":"$T","query":"What time is check-out at the hotel?"}` | `confidence: "high"`; top result is the hotel chunk (score ~0.65); raw card/passport numbers are **masked** in `text` |
| M-03 | `search_docs` with `"query":"wifi password at the airport lounge"` | `confidence: "low"` or `"none"` with `closest_score` (nothing relevant) |
| M-04 | `search_docs` with `"doc_type":"rules"` | only the rules document |
| M-05 | `search_docs` with an unknown trip id | error `NOT_FOUND` (not "no matches") |
| M-06 | `read_itinerary {"trip_id":"$T"}` | all items with `conflicts_with` |
| M-07 | `read_itinerary` with `"date_from":"2026-12-02","date_to":"2026-12-02"` | **includes items on Dec 2** (a date-only end date covers the whole day) |
| M-08 | `write_itinerary {"trip_id":"$T","action":"create","type":"activity","title":"Museum","start_at":"2026-12-03T10:00:00"}` | `item_id`, `undo_id`, `conflicts_with` if any; item has `source:"agent"` |
| M-09 | `write_itinerary` create **without** `title` | error mentioning `title` required |
| M-10 | `write_itinerary` update/delete with `item_id` | applied; each returns an `undo_id`; `POST .../undo/<id>` restores it |
| M-11 | `get_flight_status {"flight_number":"JL 44","date":"2026-11-30"}` | `status: delayed`, `delay_minutes: 35`, gate 114, terminal 3, `source: mock`, estimated 18:35 |
| M-12 | `get_flight_status {"flight_number":"JL 43","date":"2026-12-06"}` | `on_time` |
| M-13 | `get_flight_status` with `"flight_number":"hello"` | validation error ("must look like 'JL44'") |
| M-14 | `get_weather {"location":"Tokyo","days":2}` | 2 daily entries with high/low, conditions, precip %, `last_updated` |
| M-15 | `convert_currency {"amount":100,"from_currency":"USD","to_currency":"JPY"}` | `converted`, `rate`, `source`, `last_updated`, `cached` |
| M-16 | Same call twice quickly | second shows `cached: true` (TTL cache) |
| M-17 | `search_places {"location":"Shinjuku","query":"ramen"}` | mock Tokyo places with `distance_m`, `open_now` |
| M-18 | `LIVE_MODE=real`: M-14, M-15, M-17 | live Open-Meteo / Frankfurter / OpenStreetMap data (places have no rating/hours/diet data) |
| M-19 | `LIVE_MODE=real`: M-11 | still **mock** flight (`LIVE_FLIGHTS=mock` default). With `LIVE_FLIGHTS=real` -> error "Real flight provider not configured" |

---

## 3. RAG (ingestion, retrieval, confidence)

### 3.1 Ingestion
| ID | Step | Expected |
|---|---|---|
| G-01 | Upload the 4 sample docs (R-07..R-09) | each `ready`; a 5-page PDF still `ready` |
| G-02 | Run the RAG report (3.7) | 12 chunks for the 4 samples, dimension **384**, distance **cosine**, SQLite chunk count matches Chroma |
| G-03 | Look at chunk sizes in the report | paragraph-based, each at most ~450 characters |
| G-04 | Upload the same file twice | two documents; both searchable (no crash) |
| G-05 | Delete one document (R-23), regenerate the report | its chunks disappear from Chroma **and** SQLite counts still match |
| G-06 | `scripts/reindex.py` (against the test data dir) | re-ingests everything; counts unchanged |

### 3.2 Sensitive data
| ID | Step | Expected |
|---|---|---|
| G-10 | UI Docs screen / `GET trips/$T` | passport, booking ref, card number are masked (`•••••••07`) |
| G-11 | `search_docs` results and chunk endpoint | masked in `text` (the model never sees raw values) |
| G-12 | Reveal endpoint | raw value for 30 s only (`reveal_seconds`) |
| G-13 | RAG report | masked by default; `--raw` shows what Chroma really stores (the index keeps raw text; masking happens on the way out) |

### 3.3 Retrieval and confidence
Use `search_docs` (M-02) or the report's `--query`. Thresholds: high >= 0.40 (or >= 0.35 with a second hit from the same document), low >= 0.25, below = none.

| ID | Query | Expected top document | Expected confidence |
|---|---|---|---|
| G-20 | What time is check-out at the hotel, and does it include breakfast? | hotel_confirmation.txt (breakfast chunk ~0.65; the header chunk with "Check-out: 11:00 AM" is also returned, as a same-document sibling) | high |
| G-21 | What are the rules for bringing medication into Japan? | japan_entry_rules.txt | high |
| G-22 | Where can I find vegetarian food? | tokyo_guide.md | high/low |
| G-23 | What time does my flight depart? | flight_itinerary.txt | high |
| G-24 | What is the wifi password at the airport lounge? | anything weak | **none** or **low** (never a confident wrong source) |
| G-25 | how do I bake sourdough bread | n/a | **none** (nothing returned, closest score reported) |
| G-26 | Same question as G-20 asked in capitals / with typos | same top document | still high |

### 3.4 Embedding backend
| ID | Step | Expected |
|---|---|---|
| G-30 | `EMBEDDINGS=onnx` (default) first run | downloads the MiniLM model once to `~/.cache/chroma` (needs AWS S3 access) |
| G-31 | Switch `EMBEDDINGS` after data exists | **do not**: dimensions differ; run `scripts/reindex.py` after changing (hash is for tests only) |

### 3.7 Visual check of the Chroma store (read-only)

```bash
TRIPMATE_DATA_DIR=$TD .venv/bin/python scripts/inspect_rag.py --out /tmp/rag_report.html --query "What time is check-out at the hotel?"
open /tmp/rag_report.html
```
No `TRIPMATE_DATA_DIR` = your real store (`data/chroma`). The script **copies** the Chroma folder before opening it and opens SQLite read-only, so it is safe while the backend runs. `--trip <id>` limits to one trip; `--raw` unmasks sensitive values.

What the page shows and what to check:
- **Header:** collection `chunks`, chunk count (must equal "SQLite chunk rows"; a red note says to run `reindex.py` if not), embedding dimension (384 for MiniLM), distance `cosine`.
- **Query table (if `--query`):** every chunk scored by cosine similarity, marked *returned* or *dropped* by the confidence rules, plus the confidence level the agent would compute. Use it to understand or tune the thresholds in `config.py`.
- **Embedding map:** a 2-D projection (PCA) of all chunks, coloured by document; hover a dot to read the chunk. Chunks of the same document or topic should sit close together; a lone outlier is worth a look.
- **Documents and chunks:** each chunk's id, length, text and the first 6 embedding values.

Programmatic alternative: `.venv/bin/python -c "import chromadb; c=chromadb.PersistentClient('$TD/chroma').get_collection('chunks'); print(c.count(), c.peek(2))"` (do this on a copy if the backend is running).
In the app itself, the **Source Drawer** (tap a citation chip in chat) shows the exact chunk plus its neighbours: check it matches the report.

---

## 4. Agent

Needs an LLM (section 0). Per-question expectations assume the sample documents and `LIVE_MODE=mock`. Use the UI or `scripts/chat_cli.py $T "question" --url $B` (prints tool calls, citations, confidence, `llm_calls`).

### 4.1 Routing and answers (multi mode, the default)
| ID | Question | Expected agent / tools | Expected answer |
|---|---|---|---|
| A-01 | What time is check-out, and does the hotel include breakfast? | docs: `search_docs` (prefetched) | Check-out **11:00 AM**, breakfast included (6:30-10:00 AM); `[n]` chips -> Source Drawer; confidence **high** |
| A-02 | Is my 6 PM flight delayed? | live: `search_docs` + `get_flight_status` | JL 44 **delayed 35 min**, departs ~6:35 PM, Gate 114, Terminal 3, "last updated" shown |
| A-03 | What are the rules for bringing medication into Japan? | docs | summary of the rules with citations; **verify badge** (check with embassy/ministry) |
| A-04 | Find a vegetarian restaurant open now near my hotel. | live: uses the hotel address from the documents | with mock places may return few/no vegetarian matches; must not invent places |
| A-05 | Add dinner at 8 PM tomorrow to my itinerary. | itinerary: `write_itinerary` (forced first step) | item created, **undo** offered, `source: agent` badge in the itinerary, conflicts warned if overlapping |
| A-06 | What is the wifi password at the airport lounge? | docs | "could not find it in your documents", suggests official source, **low** confidence banner, no invented answer |
| A-07 | What's the weather in Tokyo and what's the check-out time? | docs + live in parallel, then **composer** | both answers merged; citation for check-out kept; UI shows agent headers (Documents, Live info, Composing) |
| A-08 | What's on my itinerary for Dec 1? / What are my travel plans? / What should I do on December 1? | itinerary: `read_itinerary` (prefetched) | lists items entered in the UI (e.g. Japanese Garden Visit 10:00); never "not found in the documents" |
| A-09 | Schedule a visit to Senso-ji on 2 December at 10 AM. | itinerary, forced write | item created with a title and the right time |

### 4.2 Guardrails
| ID | Check | Expected |
|---|---|---|
| A-20 | Every factual answer from documents | has a citation chip **or** the low-confidence banner |
| A-21 | A wrong citation (cited chunk does not contain the claim) | verifier drops the chip; confidence shows `low`; "N sources checked" note in the UI |
| A-22 | Itinerary write fails or the model claims a change without writing | visible "The itinerary was NOT changed" note; nothing saved |
| A-23 | Ask for the passport / card number | masked value only; the assistant never reconstructs it |
| A-24 | Tool limits | max 6 tool calls per turn and 30 external lookups per conversation (error text "Tool limit..." in the tool card) |
| A-25 | Preferences (Settings: units, currency, language) | answers follow them (e.g. temperatures in the chosen unit) |
| A-26 | Stop button during a streaming answer | answer stops; partial text is kept in history |
| A-27 | Same question in a long conversation after an earlier wrong answer | the fresh lookup wins (history does not poison it) |

### 4.3 Modes and providers
| ID | Check | Expected |
|---|---|---|
| A-30 | `AGENT_MODE=multi` vs request `{"agentMode":"single"}` | single: one agent with all tools (can skip the document search with small models); multi: router -> specialists -> composer -> verifier |
| A-31 | `scripts/compare_modes.py $T --url $B --yes` | table of seconds, LLM calls, citations, verifier drops per mode (uses real LLM calls/quota: demo provider needs no `--yes`) |
| A-32 | `LLM_PROVIDER=demo` | deterministic answers; **banner/label it as a stand-in, not an AI** |
| A-33 | Gemini rate limit (set `LLM_MAX_RPM=3` and ask a compound question) | amber "waiting for the assistant's rate limit" banner, then the answer (**not yet visually verified in the UI**) |
| A-34 | Stop the LLM server (local model) and ask | readable error with a retry hint, no crash |
| A-35 | Wrong API key | clear "key rejected" style message |

---

## 5. UI (desktop Chrome, phone emulation 375 x 812; also check dark mode)

Open `http://localhost:5180`. Use DevTools device toolbar for 375 px. Optional screenshot run: `cd e2e && BASE_URL=http://localhost:5180 node shots.mjs /tmp/tm-ui` (needs Node 22).

| ID | Step | Expected |
|---|---|---|
| U-01 | Open `/` with no trips | empty state with a "New trip" button |
| U-02 | New trip: name, destinations, start/end, timezone; submit with end before start | inline validation error, no trip created |
| U-03 | Create trip "Tokyo Dec 2026" (2026-11-30 to 2026-12-06, Asia/Tokyo) | lands on the Docs tab |
| U-04 | Upload the 4 samples in one go (file picker) | each row shows Queued/Reading, then Ready with a type label; passport, booking reference and card values appear masked |
| U-05 | "Reveal" on Passport number | value shows for ~30 s, then masks again |
| U-06 | Delete a document | removed from the list (and from search afterwards) |
| U-07 | Chat tab, empty state | suggestion/empty text, message box, Send |
| U-08 | Ask A-01 | answer streams; agent header; tool card "Searching your documents"; citation chips; confidence |
| U-09 | Tap a citation chip | Source Drawer slides up with the exact passage and neighbours; **Esc** closes it |
| U-10 | Ask A-03 | verify badge visible |
| U-11 | Ask A-05 | tool card "Updating your itinerary"; toast with **Undo**; tap Undo -> itinerary item gone |
| U-12 | Ask A-06 / "how do I bake sourdough bread" | low-confidence banner, no invented facts |
| U-13 | Ask A-07 | agent headers appear in order; one merged answer |
| U-14 | During an answer, press Stop | stops; partial text remains |
| U-15 | Itinerary tab | items grouped by day; agent-added items carry an "assistant" badge; overlapping items flagged |
| U-16 | "Add itinerary item" (sheet): add, edit, delete a manual item | list updates; ask A-08 afterwards: the new item is mentioned |
| U-17 | Settings tab | LLM provider and ready state, live mode, each integration with last contacted, units/currency/language preferences, "N of 500 used today" (Gemini), offline section says not enabled |
| U-18 | Change a preference and ask a question | answer follows it |
| U-19 | Dark mode (OS or DevTools emulate `prefers-color-scheme`) | all screens readable, no unreadable text |
| U-20 | Resize 375 px <-> 1280 px | layout adapts; bottom tabs on phone |
| U-21 | Reload the page mid-trip | trip, documents, itinerary and chat history are back |
| U-22 | Stop the backend and send a message | readable error with retry, UI stays usable |
| U-23 | Browser console | no errors or React warnings during U-03..U-16 |
| U-24 | Keyboard: tab through chat, Enter sends, Esc closes drawers | works without a mouse (full accessibility pass was dropped from scope) |

---

## 6. Cross-module regression (after any change)
1. `make test` (backend, about 2-3 min; run it with no `LLM_*` variables exported) and `make test-web`.
2. Sections 1 (R-02, R-07..R-11, R-14, R-21), 3.3 (G-20, G-24), 4.1 (A-01, A-05, A-06, A-08) and 5 (U-08, U-11).
3. If retrieval, chunking or embeddings changed: `reindex.py`, then the RAG report: counts match, thresholds still give the table in 3.3.

## 7. Sign-off sheet
| Module | Tested by | Date | Model/provider | Result | Notes |
|---|---|---|---|---|---|
| REST | | | n/a | | |
| MCP | | | n/a | | |
| RAG | | | embeddings: | | |
| Agent | | | | | |
| UI | | | | | |
