# TripMate

Mobile-first travel assistant (PWA + FastAPI + RAG + MCP tools). See `docs/` for the spec and overview.

## Layout
`backend/` API, ingestion, RAG, agent · `mcp-server/` tool server · `web/` React PWA · `samples/` demo docs · `eval/` · `e2e/` · `scripts/`

## Quickstart
```
make setup          # venv + deps, creates .env (add ANTHROPIC_API_KEY)
make dev-backend    # http://localhost:8000/docs
make test
```

## Status
- [x] Phase 0 scaffold
- [x] Phase 1 backend core (trips, documents ingestion, itinerary)
- [ ] Phase 2 RAG + agent · [ ] Phase 3 MCP + live tools · [ ] Phase 4 PWA · [ ] Phase 5 offline · [ ] Phase 6 hardening
