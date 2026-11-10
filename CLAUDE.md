# TripMate

**Read `docs/PLAN.md` first.** It is the handoff: current state, how to run things, working agreements, decisions, and the next step (Phase 4c: local open-weight model). Requirements: `docs/tripmate_spec.md`. Architecture: `docs/ARCHITECTURE.md`.

Hard rules (details in PLAN.md section 2): never read or commit `.env`; the user's own servers run on :8000/:5173, so test on :8010/:5180 with `LLM_PROVIDER=demo`; don't touch the user's data; share a plan before big changes; say exactly what was verified.
Python venv is `.venv` at the repo root; web/e2e need Node 22 (`make` handles it).
