# TripMate eval set

45 questions with automatic checks, to measure answer quality and to re-tune thresholds or compare models with numbers instead of a few hand-run questions. Everything is based on the fictional `samples/` documents and `LIVE_MODE=mock`, so results are repeatable. Questions and checks: `eval/questions.json`. Runner: `scripts/eval.py`.

## Run it
Use a throwaway backend with its own data dir (never `data/`, never :8000):
```bash
make local-llm                       # terminal 1 (Qwen3-8B on :8080)
make demo-reset demo-backend         # terminal 2 (backend :8010, data in /tmp/tm-demo, mock live data)
make eval EVAL_LABEL=qwen3-8b        # terminal 3: creates its own trip, ~10-15 minutes on Qwen3-8B
```
Options: `--only hotel` (id or category substring), `--agent-mode single|multi`, `--trip ID` (reuse a trip), `--url`. A cloud LLM needs `--yes` (the full set uses about 100 requests; Gemini's free tier is 12/min and 500/day). Results are written to `eval/results/<label>-<time>.json` (git-ignored) with the answer text, tools, citations and failure reasons for every question.

## What is checked (no LLM judge, plain rules)
| Check | Meaning |
|---|---|
| `all` | each entry (`a\|b` = alternatives) appears in the answer, case-insensitive |
| `none` | forbidden strings, used for sensitive values (passport, card, booking reference) |
| `cite` | a citation label contains this document name |
| `tools_any` / `tools_all` | the agent really called the live or document tool |
| `refuse` | answer says the information is not available (questions the documents cannot answer) |
| `write` | exactly the expected new agent itinerary item exists (title, start time) |
| every other case | the itinerary must not change |
| `mock_only` | value checks skipped when `LIVE_MODE=real` |

Categories: `doc_fact` (24), `doc_multi` (2), `not_in_docs` (5), `sensitive` (4), `live` (6), `itinerary` (2), `itinerary_write` (2). The checks are strict on purpose: a failure is either an app/model problem or a check that is too narrow. Read the reason before deciding which; fix the check if the answer is actually right.

## Limits
- One run per question. Local models are not deterministic: expect ±2 questions between runs.
- Only the sample documents. Thresholds tuned here may not hold for other real documents.
- String matching can reject a correct answer worded unexpectedly and cannot judge fluency or completeness.

## Results so far (Qwen3-8B via llama.cpp, multi mode, mock live data, 2026-11-11)
| Run | Change before the run | Passed |
|---|---|---|
| 1 | baseline | 34/45 |
| 2 | router word boundaries + guide/flight docs routing, `conf_high` 0.40 | 35/45 |
| 3 | verifier (attribution sentence, ISO dates), "my hotel" prefetch | 39/45 |
| 4 | `conf_low` 0.18 | 42/45 |

Remaining failures: the two-fact check-out + medicine question, the visa fee (model answers from memory; the app now appends a "Not found in your documents as written" note, after run 4), a correct answer citing the wrong passage. `gemini-3.5-flash-lite` on 10 of the questions (before run 4's threshold change) failed the same retrieval-limited ones.
