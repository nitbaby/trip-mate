# TripMate

Mobile-first travel assistant (PWA + FastAPI + RAG + MCP tools). See `docs/` for the spec and overview.

## Layout
`backend/` API, ingestion, RAG, agent · `mcp-server/` tool server · `web/` React PWA · `samples/` demo docs · `eval/` · `e2e/` · `scripts/`

## Quickstart
```
make setup          # venv + deps, creates .env (add GEMINI_API_KEY; free key at aistudio.google.com/apikey)
.venv/bin/python scripts/llm_check.py --models   # verify key + model
make dev-backend    # http://localhost:8000/docs
make web-install && make dev-web   # PWA at http://localhost:5173 (needs Node 22; proxies /api to :8000)
make dev-backend-demo   # chat without any API key: deterministic stand-in model (not an AI), for demos/tests
make test && make test-web
.venv/bin/python scripts/compare_modes.py <trip_id>   # single vs multi-agent (use a demo backend, or --yes for real LLM)
```

## Run with a local model (no cloud LLM)
Runs Qwen3-8B (Q4_K_M, ~5 GB, about 6 GB of RAM) with llama.cpp on an Apple-silicon or similar machine with 16 GB RAM. Nothing leaves your machine and there are no rate limits.
```
brew install llama.cpp && .venv/bin/pip install -e "backend[local]"
make local-model      # downloads from ModelScope (~5 GB). Behind a TLS-inspecting proxy: make local-model CA_BUNDLE=/path/to/ca.pem
make local-llm        # serves http://localhost:8080/v1 (leave it running)
```
Then set these in `.env` and restart the backend:
```
LLM_PROVIDER=openai
LLM_BASE_URL=http://localhost:8080/v1
LLM_MODEL=qwen3-8b
LLM_API_KEY=local
```
Expect roughly 6-20 s per answer. Tool calling works in multi-agent mode (the default). Single-agent mode is less reliable on a small model (it can skip the document search), so keep `AGENT_MODE=multi`.

## Live data
`LIVE_MODE=mock` (default) uses fixtures. `LIVE_MODE=real` uses Open-Meteo (weather), Frankfurter (exchange rates) and OpenStreetMap Nominatim (places, without hours or ratings). Flights have no real provider: they stay mock (`LIVE_FLIGHTS=mock`).

## Status
- [x] Phase 0 scaffold
- [x] Phase 1 backend core (trips, documents ingestion, itinerary)
- [x] Phase 3 MCP + live tools · [x] Phase 2 RAG + agent (live Claude test pending a valid API key) · [x] Phase 4 PWA UI (offline + install = Phase 5) · [ ] Phase 5 offline · [ ] Phase 6 hardening
