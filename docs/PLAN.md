# TripMate MVP Implementation Plan

**This file is the handoff.** A new session should be able to continue from this file alone (plus `CLAUDE.md`, which points here).
What to build: `docs/tripmate_spec.md` (requirement IDs, API, data model) and `docs/tripmate_overview.md`. How it fits together: `docs/ARCHITECTURE.md`.
Keep this file current: tick phases, update "Current state", and add only *non-obvious* learnings to the notes log.

Assumption: one developer working with Claude (not the spec's team of 4-5), ordered to reach a demo early.

---

## 1. Current state (as of 2026-11-11)

- Repo: `/Users/A-7878/Learning/trip-mate` (git, branch **`multi-agent-mode`**, all work committed; `main` is behind). Old copy at `/Users/A-7878/Learning/Claude_Learnings/TripMate` is a stale leftover: ignore it, never work there.
- Remote `origin` = https://github.com/nitbaby/trip-mate. **Not pushed:** the first push failed with `403 Your account is suspended` (GitHub account issue, user must resolve). Retry `git push -u origin main` only when the user says so.
- Done and working: backend (trips, docs ingestion, RAG, itinerary, undo), MCP tool server (7 tools), agent runtime in **multi-agent mode by default** (router -> specialists -> composer -> citation verifier; single-agent mode still available), React PWA UI (chat, itinerary, docs, settings), demo stand-in LLM.
- Tests: **111 backend** (`make test`, ~2-3 min) + **16 web** (`make test-web`). Both must stay green. Run the backend suite with no `LLM_*`/`TRIPMATE_DATA_DIR` variables exported (they leak into `test_factory_selection`).
- LLM status: default provider is Gemini (`gemini-3.5-flash-lite`) and **the user's key works** (verified 2026-11-10 with `scripts/llm_check.py`). User-stated limits: **15 requests/minute, 500/day**. Earlier the same day the API returned HTTP 402 "prepayment credits are depleted" for two models; it later worked again (cause unknown, possibly billing/quota state changed). If 402 or 429 appears, see Notes. Budget real-LLM runs: one question = 2-5 requests (compound multi-agent questions up to 5), so ~3 questions/minute and ~100-250 questions/day; `compare_modes.py` over 7 questions x 2 modes is ~40 requests.
- **Next step: Phase 6 (eval set + runner, optional Playwright E2E, `make seed`/`make demo`, docs).** Phase 5 (offline PWA) and the accessibility pass were dropped by the user on 2026-11-11. Phase 4c is done (below).

### How to run things
```
make setup                       # venv + deps + .env from .env.example (then user adds keys)
make dev-backend                 # API on :8000 (needs a working LLM key)   | make dev-backend-demo = no key, stand-in model
make web-install && make dev-web # UI on :5173 (proxies /api to :8000; override with VITE_API_TARGET)
make test && make test-web
.venv/bin/python scripts/llm_check.py [--models]          # verify the configured LLM works
.venv/bin/python scripts/chat_cli.py <trip_id> "question"  # chat from the terminal
.venv/bin/python scripts/compare_modes.py <trip_id> [--yes] # single vs multi agent; needs --yes for a real LLM
.venv/bin/python scripts/reindex.py                        # re-ingest docs after chunking/embedding changes
.venv/bin/python scripts/mcp_call.py [tool '{json}']       # poke the MCP tools
cd e2e && BASE_URL=http://localhost:5180 node shots.mjs    # drive the real UI in Chrome, save screenshots
```
Web/e2e commands need **Node 22**: `export PATH=$HOME/.nvm/versions/node/v22.22.2/bin:$PATH` (the Makefile does this). Python is `.venv` at the repo root.

---

## 2. Working agreements (read before acting)

- **Plan first for big changes.** The user asked to see a plan before implementation for multi-agent; keep doing that for anything large. Ask only when the decision is really theirs.
- **Never read, print or commit `.env`** (holds the user's API keys). Tell the user which line to edit instead.
- **The user runs their own backend/UI on :8000 and :5173** (long-running, with their real key and data in `data/`). Do NOT start servers on those ports or hit them. For your own testing use **backend :8010, vite :5180** (`VITE_API_TARGET=http://localhost:8010`), `TRIPMATE_DATA_DIR=/tmp/...`, and `LLM_PROVIDER=demo` unless the task is the real model. Before any script that calls an LLM, check which backend it targets (an earlier run accidentally used the user's key via :8000). Stop only processes you started.
- **Don't delete or rewrite the user's data or files** (`data/`, their `.git`, etc.). Known leftover to mention, not remove: test trip `291114cf6409` in `data/tripmate.db`.
- **Be exact about what is verified.** Say what ran live vs. only against mocks/fakes. Don't claim a file or change exists unless it was written (this slipped twice).
- Token economy: the user is cost-aware. Prefer short commands/outputs; suggest the user run long downloads themselves with `! <cmd>`.
- Commit at phase ends and sensible steps; commit messages end with `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Don't commit unless asked or it is a phase boundary the user expects.
- Tests: add tests with each feature. Test fixtures pin `LIVE_MODE=mock`, `EMBEDDINGS=hash`, `AGENT_MODE=single` regardless of `.env`; multi mode tests pass `agentMode: "multi"` per request.

---

## 3. Decisions (made, don't relitigate)

| Topic | Choice |
|---|---|
| Vector store | Chroma (`data/chroma`). SQLite (`data/tripmate.db`) holds trips/docs/chunks/itinerary/chat; search itself is Chroma only. |
| Embeddings | `EMBEDDINGS=onnx` (default): Chroma's bundled all-MiniLM-L6-v2, downloads once from AWS S3 to `~/.cache/chroma`. `fastembed` needs huggingface.co (blocked here). `hash` = tests only. |
| Chunking / confidence | Paragraph chunks <=450 chars. Confidence from cosine score: high >=0.45 (or >=0.35 with a second hit from the same doc), low >=0.25, else none (thresholds in `config.py`; re-tune with eval set in Phase 6). |
| Agents | `AGENT_MODE=multi` default: deterministic router (no LLM call) -> specialist agents (docs / live / itinerary) with own prompts + tool allowlists -> parallel if >1 intent -> composer merges -> deterministic citation verifier. `single` = original one-agent loop. Per-request override `agentMode`. See `docs/ARCHITECTURE.md`. |
| LLM | Provider via `.env`: `LLM_PROVIDER=gemini` (default; OpenAI-compatible endpoint; `GEMINI_MODEL=gemini-3.5-flash-lite`) \| `openai` (any OpenAI-compatible server: Groq, llama.cpp, Ollama...) \| `anthropic` \| `demo` (rule-based stand-in, NOT an AI, no key/network, for UI/E2E/demos). Adapters: `backend/app/agent/llm.py` (Anthropic-shaped blocks are the canonical internal format). |
| Gemini model notes | `gemini-2.5-flash` retired for new users; `gemini-flash-latest` hangs; `gemini-3.8-flash` 503 "high demand"; `gemini-3.1-flash-lite` weak at tools; `gemini-3.5-flash` ok but 20-44 s/question; `gemini-3.5-flash-lite` ~7 s/question and correct on 2/2 flows checked. `reasoning_effort=low` is sent for Gemini. |
| Live data | `LIVE_MODE=mock` default (fixtures; flight JL44 delayed 35 min; Tokyo places). `real`: Open-Meteo weather, Frankfurter FX, Nominatim places (no ratings/hours/diet filter). Flights have no real provider (mock only, user-approved): `LIVE_FLIGHTS=mock` (default) keeps flights mock even when `LIVE_MODE=real`. Real mode checked live 2026-11-11: weather, FX and places work (places have no ratings/hours/diet data). |
| Guardrails | Citation or low-confidence banner; verify badge for visa/medication/customs/currency; 6 tools/turn; 30 external calls/conversation; backend injects `trip_id`; sensitive values (passport/booking ref/card) masked in API and redacted before reaching the model; raw value only via reveal endpoint. |
| Privacy caveat | Hosted free tiers may retain prompts: use only the fake `samples/` data. A local model keeps everything on the machine. |
| UI | React 19 + Vite 8 + Tailwind 4 + TanStack Query + React Router (no zustand/Leaflet/Dexie yet). Target: desktop Chrome with 375 px phone emulation. Map screen cut (stretch). |
| Tooling | Python 3.12 + pip (no uv). Node 22 for web (`web/.nvmrc`; Vite 8/Vitest 5 fail on Node 20.15). Test env happy-dom. |

### Network constraints (this machine)
| Blocked (403) | Reachable |
|---|---|
| huggingface.co, hf-mirror.com, ollama.com, registry.ollama.ai, lmstudio.ai, openrouter.ai, storage.googleapis.com, corporate npm Artifactory login expired | PyPI, registry.npmjs.org (web/ and e2e/ use a project `.npmrc` for it), AWS S3 (Chroma model), **ModelScope (modelscope.cn)**, Homebrew formulae API, GitHub web/releases (ghcr.io needs token; unverified), Gemini API, Groq, Google AI Studio, NVIDIA NIM, DashScope, Open-Meteo, Nominatim, Frankfurter. Overpass unreachable. |

---

## 4. Phases and status

- [x] **Phase 0 - Scaffold.**
- [x] **Phase 1 - Backend core:** trips + itinerary CRUD (conflicts, `source=agent`), document upload + background ingestion, masking, reveal and chunk (Source Drawer) endpoints.
- [x] **Phase 2 - RAG, confidence, agent:** `search_docs` + confidence, SSE chat (`POST /api/trips/{id}/chat`), events per spec 5.2 (+`undoId`), guardrails, history, preferences (units/currency/language) in the prompt. Proven live with Gemini: all of flows 1-5 and a not-in-docs question on `gemini-3.5-flash`; only flows 1-2 on the current default `gemini-3.5-flash-lite` (the rest were not re-run because of the 402 above, which has since cleared).
- [x] **Phase 3 - MCP server + live tools:** `mcp-server/` (stdio, 7 tools), TTL cache, mock/real providers, undo, `/places`, `/status`.
- [x] **Phase 4 - PWA UI:** screens, streaming chat, citation chips + Source Drawer, tool cards, banners, undo toast, itinerary, docs, settings, dark mode, a11y basics. Visually verified in Chrome at 375 px.
- [x] **Phase 4b - Multi-agent mode (default):** `agent/router.py`, `agent/prompt.py` roles, `agent/verify.py`, `agent/loop.py` (`run_agent` + `Turn`), events `agent_start/agent_end/verified`, UI agent headers + "N sources checked", `scripts/compare_modes.py`, `docs/ARCHITECTURE.md`. Deviations from the approved plan: rules-only router (unmatched -> docs agent); live agent also has read-only `search_docs`. A fair single-vs-multi comparison on a real LLM is **still to do** (Gemini key works now; budget ~40 requests, run against your own backend on :8010 with `--yes`).

- [x] **Phase 4d - LLM rate-limit handling (done 2026-11-10):** `backend/app/agent/ratelimit.py` + adapter changes in `agent/llm.py`. One process-wide sliding-window limiter per model (`reserve()` is synchronous, so parallel specialists can't race for a slot) queues requests instead of letting them 429; waits are surfaced as a new `waiting` SSE event (`seconds`, `reason` = `rate_limit`|`retry`, optional `agent`) that the UI shows as an amber banner until the next progress event. Waits longer than `LLM_MAX_WAIT_SECONDS` (65) fail fast with a retryable error. 429 handling: honours `Retry-After` / Gemini `retryDelay` (up to 2 retries, only while no output has started), tells a per-day exhaustion (`PerDay`) from a per-minute one and stops with a message naming the Pacific-midnight reset; 5xx/connection errors retry once; SDK retries disabled (`max_retries=0`) so every request is counted and visible. Daily budget persisted in `llm_usage` (per provider+model, day in `LLM_QUOTA_TZ`=America/Los_Angeles), checked before each request. Defaults for Gemini: 12 req/min (free tier allows 15) and 500/day; `LLM_MAX_RPM` / `LLM_DAILY_LIMIT` override (-1 = provider default, 0 = unlimited; non-Gemini providers are unlimited unless set). `done` carries `quota {used, limit}` (UI note at >=90%); `GET /api/trips/{id}/status` has `llm_limits`; Settings shows "N of 500 used today"; `scripts/chat_cli.py` prints `[waiting]` and daily usage. Verified live on Gemini with `LLM_MAX_RPM=3`: a question waited 37 s then answered; counter 5 -> 8. Caveats: the daily counter only counts requests made through this app's database (other tools using the same key are invisible); with the real default of 12/min a 5-request compound question can wait up to about a minute.

### Phase 4c - Local open-weight model (done 2026-11-11)
**Result:** the app runs end to end in multi mode on **Qwen3-8B Q4_K_M** via llama.cpp (`make local-model`, `make local-llm`, four `.env` lines: see README "Run with a local model"). Roughly 6-20 s per answer on the M1 Pro 16 GB; no key, no rate limit, nothing leaves the machine. Qwen2.5-7B was tried first and is clearly worse (wrong values, skipped searches, claimed writes it never made). Gemini `gemini-3.5-flash-lite` is still faster (3-5 s) and cites more cleanly. Not tried: Llama 3.2/3.1, Gemma 3 (Gemma has no native tool format), nomic-embed-text (see feasibility discussion: low value, MiniLM is fine; Ollama is unreachable here, llama-server already serves the OpenAI API).
Environment gotchas on this machine: `brew install` failed with "user nbaby doesn't exist" because the shell had a stale `$USER` (use `USER=<real login> brew ...`); `modelscope` needs a CA bundle (system certs + company root cert) via `make local-model CA_BUNDLE=...`.
Six demo questions on Qwen3-8B (own backend :8010, mock live data): check-out/breakfast correct (but may show confidence `low` when the cited chunk is the wrong one: honest), delayed flight correct, medication correct with verify badge, vegetarian places finds the hotel then mock places returns 0, add dinner now works, not-in-docs refuses correctly.
`compare_modes.py` on Qwen3-8B (7 questions, one run each): single 115 s / 12 LLM calls / 2 citations / 0 dropped; multi 123 s / 12 calls / 7 citations / 2 dropped by the verifier. Single mode answered the medication question with **no document search at all** (from memory): multi is the safe default for small models.
App-side changes this phase (all tested): deterministic prefetch before the model's first turn (`search_docs` for docs questions and live "my ..." questions; `read_itinerary` for plan questions); explicit "add/schedule ..." requests force `write_itinerary` as the first step (`tool_choice=required`, only that tool offered with create fields required); "NOT changed" note when an answer claims an itinerary change that did not happen; same-document sibling chunks returned slightly below `conf_low` (`conf_sibling_margin`); every agent gets the traveler's itinerary in its prompt (marked as not a document, never cited) and plan wordings route to the itinerary agent; live-data answers without citations show no document-confidence badge; `LIVE_FLIGHTS` setting; `LLM_TIMEOUT_SECONDS`.

(Original plan below.)
Goal: the app works end-to-end with **no cloud LLM** (no key, no rate limits, no data leaving the machine), in multi mode, on the user's M1 Pro 16 GB.

Why: Gemini key has no credits; free tiers are slow/limited; local model fixes privacy and quota. The OpenAI-compatible adapter already supports it (`LLM_PROVIDER=openai`), so most work is install + verification + tuning.

Chosen runtime/model (from the reachability checks on 2026-11-10; **download/serve steps below are NOT yet executed or verified**):
- Runtime: **llama.cpp** (`llama-server`). `brew install llama.cpp` (formula v0.9.0, arm64 bottle exists; bottle download from ghcr.io is untested here). Alternative Ollama is a worse fit (registry blocked; GGUF import needs a hand-written Modelfile chat template for tools; cannot import split shards).
- Weights: from **ModelScope** (HF blocked). Primary: `Qwen/Qwen2.5-7B-Instruct-GGUF`, Q4_K_M = 2 shards (`qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf` 3.99 GB + `-00002-of-00002.gguf` 0.69 GB). Shard URL pattern `https://modelscope.cn/models/Qwen/Qwen2.5-7B-Instruct-GGUF/resolve/master/<file>` returned 200 for shard 1. A guessed unsharded name returns 404.
- Fallbacks if quality is too weak: `Qwen/Qwen3-8B-GGUF` (`Qwen3-8B-Q4_K_M.gguf`, 5.03 GB single file; has a thinking mode that slows answers: disable it) or `Qwen/Qwen2.5-14B-Instruct-GGUF` (Q4_K_M 3 shards, ~9 GB: tight on 16 GB RAM). `Qwen2.5-3B-Instruct-GGUF` exists but is weak at tool use.
- Disk: 96 GB free. Model dir `models/` (now in `.gitignore`).

Steps
1. `brew install llama.cpp` (user can run with `! brew install llama.cpp`). Confirm `llama-server --version`.
2. Add `modelscope` as an optional extra in `backend/pyproject.toml` (`local = ["modelscope"]`); currently only pip-installed ad hoc in `.venv`. Add `make local-model` target that runs:
   `.venv/bin/modelscope download --model Qwen/Qwen2.5-7B-Instruct-GGUF --include "qwen2.5-7b-instruct-q4_k_m*.gguf" --local_dir models/qwen2.5-7b` (the `--include` and `--local_dir` flags exist in the installed CLI). ~4.7 GB; let the user run it or run it in the background.
3. Add `make local-llm` target: `llama-server -m models/qwen2.5-7b/qwen2.5-7b-instruct-q4_k_m-00001-of-00002.gguf --alias qwen2.5-7b --jinja -c 8192 -ngl 99 --port 8080` (`--jinja` is required for tool calling; point `-m` at shard 1 with both shards in one dir). Check `curl localhost:8080/v1/models`.
4. Configure `.env` (the **user** edits it; do not read it): `LLM_PROVIDER=openai`, `LLM_BASE_URL=http://localhost:8080/v1`, `LLM_MODEL=qwen2.5-7b`, `LLM_API_KEY=local`. Verify with `scripts/llm_check.py`.
5. Verify tool calling through the adapter against llama-server (streamed `tool_calls` shapes differ per server): run the six questions (check-out+breakfast, 6 PM flight delayed, medication rules + verify badge, vegetarian places open now, add dinner 8 PM tomorrow, not-in-documents question) via `scripts/chat_cli.py` on **your own backend :8010** with real onnx embeddings and the `samples/` documents. Fix adapter issues found (argument streaming, missing ids, `finish_reason`).
6. Likely code changes (do only if the checks show a need): make the LLM request timeout configurable (`LLM_TIMEOUT`, currently 60 s read timeout in `OpenAICompatLLM`: a slow local first token may exceed it); don't send `temperature`/`reasoning_effort` if the server rejects them; tighten specialist prompts for a small model; consider per-role models (e.g. local for specialists, a stronger model only for the composer) as an optional follow-up.
7. Run `scripts/compare_modes.py <trip> --yes` (single vs multi on the local model; no API quota involved) and record LLM calls, seconds, citations kept/dropped, errors.
8. Update README (local model section), `.env.example`, this file, add an adapter test for any quirk found. Commit.

Exit criteria: the six questions give correct answers with working citations in **multi mode** on the local model; seconds per question recorded; if unusable, switch to a fallback model and record why; fresh-clone instructions (`make local-model`, `make local-llm`, three `.env` lines) work.

Risks: Homebrew/ghcr download may fail on this network; split-GGUF loading; 7B tool-calling reliability and citation discipline (verifier + multi mode help); latency on 16 GB; RAM pressure with Chrome + backend + model (7B Q4 needs about 5 GB).

### Phase 5 - Offline + installable PWA (after 4c, or before if the user prefers)
Manifest + icons, service worker app shell (vite-plugin-pwa), Dexie caches (itinerary, masked docs + chunks for keyword search, last 100 chat messages, last live responses labelled stale), offline banner. Offline write queue only if time allows (second cut). Settings "Offline storage" section currently says "not enabled yet". Install requires localhost or HTTPS (localhost fine for desktop Chrome).

### Phase 6 - Hardening + demo-ready
Playwright E2E (`e2e/`, system Chrome via `channel: "chrome"`, phone viewport) for the 5 flows using `LLM_PROVIDER=demo`; eval set (30-50 questions) + runner and confidence-threshold tuning; a11y pass; `make seed` / `make demo` reset (+ serve built web from the backend or `vite preview`); demo script, README, short recorded walkthrough. Also: re-run live Gemini checks when credits exist; real-vs-mock live data check; remove the stray test trip if the user wants.

### Backlog / open items
- **Gemini is unblocked:** re-run the 6 demo questions on `gemini-3.5-flash-lite` (own backend :8010, real onnx embeddings, `samples/`), then `compare_modes.py --yes`. Confirm tool use on the lite model for medication, places, itinerary add and not-found (not yet seen).
- ~~Rate-limit handling~~ **DONE** (see Phase 4d below). Still to verify in a browser: the amber "Waiting for the assistant's rate limit" banner in the chat UI (covered by reducer tests and a live CLI run, not yet screenshotted).
- Push to GitHub once the account issue is resolved.
- Map screen (stretch, cut), real flight provider (optional), LLM-based verifier layer (optional), router LLM fallback (optional).

---

## 5. Definition of done
- 5 demo flows (spec 9) pass end to end, in the UI, in multi mode (E2E on the demo provider; manual on a real or local LLM).
- Installable; app shell works in airplane mode.
- Every factual answer has a grounded citation or a low-confidence banner; agent writes are badged and undoable.
- Fresh clone runs with `make setup` + one LLM option (Gemini key, or local model via `make local-model`/`make local-llm`, or the demo provider).

Scope cuts, in order: map -> offline writes -> simplified Docs screen -> simplified Source Drawer. Never cut: citations, confidence/verify behaviour, itinerary agent writes with undo, the five demo flows.

---

## 6. Notes log (non-obvious learnings only)
- **Schema sanitizer bug (fixed):** `sanitize_schema` dropped every key named `title`, including a tool *parameter* named `title`, so no OpenAI-compatible model (Gemini too) could ever see `write_itinerary.title`. Parameters live under `properties`: only schema-level titles may be stripped.
- **Gemini 3 needs a thought signature on every function call in the history.** A tool call the app injects itself (the prefetch) gets the documented dummy `skip_thought_signature_validator` (Gemini only; the internal `synthetic` flag is stripped for Anthropic). Without it every following request is a 400.
- **Chat history poisons small models:** the last 20 messages go to the model, and Qwen copied its own earlier "not found" replies even when the data was now available. Prefetching the lookup and labelling the itinerary block as "read fresh, overrides earlier replies" fixes it. A new conversation also avoids it.
- Itinerary reads go through the MCP tool server, not the HTTP API, so they never appear in the backend access log. `read_itinerary` with a date-only `date_to` used to exclude that whole day (string compare): fixed.
- llama-server: a *named* `tool_choice` is not enforced; `tool_choice=required` with a single offered tool is. `--chat-template-kwargs '{"enable_thinking":false}'` turns Qwen3 thinking off.
- Docs/tools for testing and demos (2026-11-11): `docs/MANUAL_TEST_PLAN.md` (REST, MCP, RAG, Agent, UI), `docs/DEMO_PLAN.md` (scripted demo), `scripts/inspect_rag.py` (read-only HTML report of the Chroma store: chunks, embedding map, query scoring; masks sensitive values), `scripts/demo_seed.py` (trip + sample docs on a backend). The manual plan's expected results were written from code and earlier runs; only R-10, R-24 and the tool list were re-checked by hand on 2026-11-11.
- `scripts/debug_itinerary.py <trip_id>` prints what the agents see for a trip (read-only, no secrets). Reading `data/tripmate.db` for diagnosis: open with `mode=ro` or copy it to the scratchpad; never modify it.
- Multi-agent first live data (Gemini 3.5 flash-lite): single-intent questions cost the same LLM calls as single mode; compound ones cost more (6 vs 2). The citation verifier first rejected valid citations (a sentence with two facts; "6:35 PM" vs "18:35"): fixed with per-claim attribution and time normalisation; recorded real answers are regression tests (`tests/test_multi.py`).
- Relative `TRIPMATE_DATA_DIR=./data` once resolved against the cwd (backend vs scripts used different DBs): now anchored to the repo root.
- npm: web needs Node 22; `web/.npmrc` + `e2e/.npmrc` point to registry.npmjs.org; `@rolldown/binding-darwin-arm64` is an explicit optional dependency (npm optional-dependency lockfile bug); jsdom 31 needs a newer Node, so tests use happy-dom.
- Gemini via the OpenAI-compatible endpoint: tool schemas must drop `anyOf`-null/`title`/`default`; thought-signature `extra_content` must be echoed back; `reasoning_effort=low` keeps replies fast and inside `max_tokens`; 429 = rate limit; a 402 "prepayment credits are depleted" was seen once on 2026-11-10 for every model and later cleared: treat it as a billing/quota state to ask the user about, not as a code bug.
- Retrieval scores with MiniLM: relevant queries 0.43-0.83, irrelevant <=0.14 on the samples (hence the thresholds). The test-only hash embedder scores long natural-language queries lower, so demo/test assertions on confidence allow high or low.
- Mock places ignore generic query words ("vegetarian restaurant"); itinerary writes skip the confidence banner (spec 3.3); `itinerary_updated` carries `undoId`.
- Incident log: (1) a comparison run once hit the user's own backend on :8000 using their Gemini key and left a test trip in their DB: hence the agreements above and the `--yes` guard in `compare_modes.py`. (2) Twice a file/change was claimed that did not exist (`docs/ARCHITECTURE.md`, `models/` in `.gitignore`): verify before claiming.
