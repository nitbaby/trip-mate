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
```

## Status
- [x] Phase 0 scaffold
- [x] Phase 1 backend core (trips, documents ingestion, itinerary)
- [x] Phase 3 MCP + live tools · [x] Phase 2 RAG + agent (live Claude test pending a valid API key) · [x] Phase 4 PWA UI (offline + install = Phase 5) · [ ] Phase 5 offline · [ ] Phase 6 hardening
