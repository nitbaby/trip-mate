# Model comparison plan: Qwen3-8B vs Gemma 4 12B vs Gemini

Status (2026-11-12): Gemma 4 12B is measured (below). Qwen3-8B and Gemini have **not** been run on the current 56-question eval set, so no like-for-like comparison exists yet. Read `docs/PLAN.md` section 2 first (never read `.env`; test on :8010/:5180; don't touch `data/`; say exactly what was verified). Related: `docs/GEMMA_PLAN.md`, `docs/EVAL.md`.

## Gemma 4 12B results so far (own backend :8010, multi mode, mock live data, llama.cpp build 12110)
- Raw server check: structured `tool_calls` work streamed and non-streamed; `tool_choice: "required"` with one tool works. Gemma 4 **thinks by default** (`reasoning_content`, very slow): `--chat-template-kwargs '{"enable_thinking":false}'` fixes it (now in the Makefile `gemma4` branch).
- Six demo questions: 5 of 6 good (the miss = mock places returns 0, same as Qwen).
- Eval, 56 questions: **run 1 51/56, mean 47.0 s, max 508 s; run 2 51/56, mean 26.9 s, max 71 s.** Same 5 failures both runs (so accuracy is stable; only speed varied with memory pressure: swap was 10-13 GB used during both runs).
- Failures: `hotel-latecheckout`, `flight-depart`, `flight-terminal` (no citation), `multi-checkout-otc`, `para-vacate` (answer says check-out time not found; misses "11:00").
- RAM: about 8 GB resident when not paged out. On the 16 GB machine run it with Chrome/Teams closed for clean timings.

## Why the eval counts are not comparable yet
Qwen3-8B's 34/35/39/42 were on the older **45**-question set; `eval/questions.json` now has **56**. Compare only runs on the same file. (`eval/results/` is git-ignored: result JSONs stay local.)

## Known issues to handle first (they distort every comparison)
1. **Citation parser ignores grouped markers.** `backend/app/agent/verify.py:43,73,95` only match `[N]`; Gemma writes `[1, 5]` / `[1, 3]`, so valid citations are dropped (`cites` empty -> eval "no citation", and the "Not found in your documents as written" note is wrongly appended). Fix: accept `[1, 5]` / `[1,5]` (split into separate markers or normalise to `[1][5]` before verifying), with a test using a recorded answer. Expect +3 on Gemma (the three citation failures). Do this before any final model comparison, then re-run Gemma.
2. **Chroma "Error finding id" on the second trip.** Seen twice on :8010: the first trip on a fresh backend works; creating a second trip (seed trip then eval, or two evals in a row) makes `search_docs` fail with `chromadb.errors.InternalError: Error finding id` (see `backend/app/vectors.py:36`). Workaround used: `make demo-reset`, restart the backend, then run one eval. Investigate with a minimal repro (two trips, same documents, query the second) before trusting multi-trip use; it may affect the real app on :8000.
3. `chat_cli.py` defaults to `--url http://localhost:8000` (the user's backend). Always pass `--url http://localhost:8010`. `eval.py` defaults to :8010 and refuses :8000.

## Runs to do (one at a time; each on a freshly reset :8010 backend until issue 2 is fixed)
Per run: `make demo-reset`, start the model server, start the backend, `make eval EVAL_LABEL=<label>`; record score, mean/max seconds, LLM calls, failures. Do two runs per model when time allows (noise is about +-2 and speed varies with memory).

### A. Qwen3-8B (same 56 questions)
1. Stop any other llama-server (RAM). `make local-llm` (port 8080, alias `qwen3-8b`).
2. `make demo-reset`, then `make demo-backend` (defaults to Qwen), then `make eval EVAL_LABEL=qwen3-8b-56`.
3. Repeat once (`qwen3-8b-56-run2`).

### B. Gemma 4 12B (after fix 1)
`make local-llm LOCAL_MODEL=gemma4 PORT=8082`; `make demo-backend LOCAL_MODEL=gemma4 PORT=8082`; `make eval EVAL_LABEL=gemma4-12b-fixed`.

### C. Gemini (`gemini-3.5-flash-lite`, the user's key)
- Limits: 15 requests/min, 500/day; the app throttles at 12/min. One 56-question run is about 130 LLM calls (about 10-15 min with the limiter), so two runs fit in a day. **Ask the user before spending quota.**
- The key lives in `.env`, which must not be read. Add a `DEMO_LLM=gemini` branch to the Makefile `DEMO_ENV` that sets only `LLM_PROVIDER=gemini` (the backend loads the key from `.env` itself; check it starts with the model in `/api/health`). Quota counter is per this app's database: the throwaway data dir starts at 0, so also watch usage in the Google console.
- First `scripts/llm_check.py` against :8010 settings, then `make eval EVAL_LABEL=gemini-3.5-flash-lite`. Also run the paraphrase router check and `compare_modes.py <trip> --yes` only if the user asks.
- If HTTP 402/429 appears, see PLAN.md notes (billing/quota state: ask the user).

## Record and decide
Add a table to `docs/EVAL.md`: model, set size, score, per-category, mean/max seconds, LLM calls, RAM, quirks. Update `PLAN.md` Phase 4c with a short paragraph. Keep **Qwen3-8B as the local default** unless Gemma is clearly better on the same set (say >= 54/56 after fix 1, at comparable speed). Gemini remains the fast/hosted option; local models are the private option.

## Don'ts
- Don't start anything on :8000/:5173; stop only processes you started (llama-server, :8010 backend, eval).
- Don't commit `.env`, `models/`, or `eval/results/` (git-ignored).
- Don't claim a model is better from runs on different question sets or from one run.
