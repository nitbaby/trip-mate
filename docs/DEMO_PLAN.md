# TripMate demo plan and scripts

A 10-minute main demo plus optional "behind the scenes" extras. Each scene has: what you do, what you say, what should happen, and a fallback.
Facts (check-out 11:00 AM, flight JL 44 delayed 35 minutes, ...) come from the fictional `samples/` documents and `LIVE_MODE=mock`, so the demo is repeatable.
**Say this early and plainly:** the documents are fake, live data (flight, weather, places, rates) is fixture data in the demo, and the assistant can make mistakes: that is why it cites sources and flags low confidence.

## 0. Pick a mode

| Mode | When | Pros | Watch out |
|---|---|---|---|
| **A. Local model** (Qwen3-8B via llama.cpp) | privacy story, no network or quota | nothing leaves the laptop, no rate limits | 6-20 s per answer; occasional misses: rehearse |
| **B. Gemini** (`gemini-3.5-flash-lite`) | fastest, cleanest answers | 3-5 s per answer | needs internet and key; free tier 15 requests/min, 500/day; hosted tiers may retain prompts (fake data only) |
| **C. Demo stand-in** (`LLM_PROVIDER=demo`) | emergency fallback or UI-only walkthrough | deterministic, offline | it is a rule-based stand-in, **not an AI**: say so |

**Decision (2026-11-11): the demo runs on A, the local Qwen3-8B** (nothing leaves the laptop, no quota). B (Gemini) is the backup if a question misbehaves live; C is the last-resort fallback. On the 45-question eval set Qwen3-8B passes 42; known weak spots to avoid on stage: asking one question that needs both the hotel check-out and the medication rules, and visa fees.

## 1. Setup (do this 30 minutes before)

Use a dedicated data directory so the demo starts clean and never touches your own trips.

```bash
cd /Users/A-7878/Learning/trip-mate
export DEMO=/tmp/tm-demo && rm -rf $DEMO
```
**Terminal 1: LLM (mode A only)**
```bash
make local-llm            # wait for "server is listening"; leave it running
```
**Terminal 2: backend** (mode B: your `.env` has `LLM_PROVIDER=gemini`; mode A: `.env` points at `localhost:8080`; mode C: add `LLM_PROVIDER=demo`)
```bash
cd backend && TRIPMATE_DATA_DIR=$DEMO LIVE_MODE=mock ../.venv/bin/uvicorn app.main:app --port 8010
```
**Terminal 3: web**
```bash
cd web && PATH=$HOME/.nvm/versions/node/v22.22.2/bin:$PATH VITE_API_TARGET=http://localhost:8010 npx vite --port 5180
```
**Terminal 4: check and seed**
```bash
.venv/bin/python scripts/llm_check.py                 # (LLM_* from the same env as the backend) expect OK
curl -s localhost:8010/api/health                     # llm_configured: true, live_mode: mock
```
Two ways to start the show:
- **Live build-up (recommended):** open `http://localhost:5180`, create the trip and upload the documents on stage (scene 2).
- **Pre-seeded (if short on time):** `.venv/bin/python scripts/demo_seed.py` prints the trip URL; skip scene 2 and mention it.

**Warm-up:** ask one throwaway question in a *second trip* (or run `scripts/chat_cli.py <trip> "hello" --url http://localhost:8010`) so the model and embeddings are loaded; the first answer is the slowest. Do **not** warm up inside the demo trip: it adds chat history.

**Pre-flight checklist**
- [ ] Browser at 375 px phone emulation (DevTools device toolbar), zoom 100%, light mode (dark mode shown at the end if you want)
- [ ] Tabs closed, notifications off, screen sharing the browser window only
- [ ] `rm -rf $DEMO` was run: no old trips; backend started **after** it
- [ ] Wi-Fi on for mode B; for mode A you can optionally switch it off later
- [ ] `docs/DEMO_PLAN.md` open on a second screen; the RAG report pre-generated (scene 10)

## 2. Main demo script (about 10 minutes)

### Scene 1: The problem (30 s)
**Say:** "When you travel, your plans are scattered across a hotel PDF, a flight email, a visa page. TripMate keeps them in one place and answers questions about *your* trip, with sources, and it tells you when it doesn't know."

### Scene 2: Create the trip and add documents (1 min)
**Do:** *New trip* -> name `Tokyo Dec 2026`, destination `Tokyo`, `2026-11-30` to `2026-12-06`, timezone `Asia/Tokyo` -> *Create trip* (lands on Docs). Choose files: `hotel_confirmation.txt`, `flight_itinerary.txt`, `japan_entry_rules.txt`, `tokyo_guide.md` (from `samples/`).
**Say:** "These are fake documents. Each is read, split into small passages and indexed for search."
**Expect:** rows go Queued -> Reading -> Ready, each with a type (confirmation, itinerary, rules, guide). The passport, booking reference and card number are **masked**.
**Do:** tap *Reveal* on Passport number.
**Say:** "Sensitive values are masked everywhere, including what the AI sees. Revealing is deliberate and temporary: 30 seconds."
**Fallback:** a document stuck on Reading > 30 s: reload; if still stuck, use the pre-seeded trip (`demo_seed.py`).

### Scene 3: Ask about the hotel, with sources (1.5 min)
**Do:** Chat tab. Type: `What time is check-out, and does the hotel include breakfast?`
**Say:** "It searches my documents first, not the internet."
**Expect:** a "Searching your documents" card, then: check-out **11:00 AM**, breakfast included for up to 2 guests, 6:30-10:00 AM, with `[1]`-style source chips and a high-confidence mark.
**Do:** tap a source chip.
**Say:** "Every statement is traceable: this is the exact passage, with the text around it. If a citation didn't actually support the claim, a verifier removes it and lowers the confidence."
**Fallback:** if it says 1:00 PM, that is the *late* check-out fee line: point at the chip and say "this is why sources matter", then re-ask: `What is the check-out time?`

### Scene 4: Live information (1 min)
**Do:** `Is my 6 PM flight delayed?`
**Say:** "It found my flight in the documents, then asked a live flight tool."
**Expect:** JL 44, **delayed 35 minutes**, new departure about 6:35 PM, Gate 114, Terminal 3, with a "last updated" time.
**Say:** "In this demo the flight data is a fixture; weather, currency and places can run on real free services."

### Scene 5: Rules, with a safety flag (1 min)
**Do:** `What are the rules for bringing my medication into Japan?`
**Expect:** a summary (one-month supply for most prescriptions, stimulants such as some ADHD medication prohibited, import certificate for larger quantities), citations, and a **verify** badge.
**Say:** "For things like medication, visas or customs it always reminds you to confirm with the official source."

### Scene 6: Places (optional, 1 min; the riskiest scene: rehearse it)
**Do:** `Find a vegetarian restaurant open now near my hotel.`
**Expect:** it resolves the hotel address from the documents and searches nearby. With fixture places it may return few or no vegetarian matches.
**Say (if few results):** "It would rather say it found nothing than invent a restaurant."
**Fallback (safer question):** `What vegetarian options does the Tokyo guide mention?` -> answers from the guide (shojin ryori, "niku nashi", fish-stock warning) with citations.

### Scene 7: It can act: itinerary with undo (1.5 min)
**Do:** `Add dinner at 8 PM tomorrow to my itinerary.`
**Expect:** a "Updating your itinerary" card, a confirmation, and an **Undo** toast.
**Do:** open the Itinerary tab: the dinner is there with an "assistant" badge. Back in chat ask `What's on my itinerary?`, then tap **Undo** on the toast (or in the itinerary) and show it disappears.
**Say:** "Anything the assistant changes is labelled and reversible. And if it claims it changed something but didn't, the app says so."
**Fallback:** if the model replies without creating anything, you will see "The itinerary was NOT changed": say "that safety net is exactly for this", then add the item with *Add itinerary item* and continue.

### Scene 8: Honesty (30 s)
**Do:** `What is the wifi password at the airport lounge?`
**Expect:** "I could not find it in your documents", suggests an official source, **low-confidence** banner, no invented answer.
**Say:** "This is the behaviour I care about most: no confident guesses."

### Scene 9: Several agents at once (1 min)
**Do:** `What's the weather in Tokyo and what's the check-out time?`
**Expect:** agent headers (Documents agent, Live info agent, then Composing the answer); one merged answer with the check-out citation and a forecast.
**Say:** "A small router sends each part to a specialist; a composer merges them; a verifier checks the citations."

### Scene 10: Wrap up (30 s)
**Say:** "Documents in, grounded answers out, live data when needed, actions you can undo, and honest uncertainty. It runs on a hosted model or fully on this laptop."

## 3. Optional extras (pick 1-3, 2-3 minutes each)

**E1. Local-model privacy.** Mode A running. Settings tab shows the assistant provider (`openai` here means your own local server on :8080). Say: "No account, no key, no quota: the model runs on this machine." Optionally switch Wi-Fi off and ask a document question: it still answers (embeddings and model are local; live tools are fixtures).

**E2. Look inside the search index.**
```bash
TRIPMATE_DATA_DIR=$DEMO .venv/bin/python scripts/inspect_rag.py --out /tmp/rag_report.html --query "What time is check-out at the hotel?"
open /tmp/rag_report.html
```
Show: chunk table (12 chunks, 4 documents), the **embedding map** (documents cluster), and the query table: scores per chunk and which were returned or dropped. Say: "This is how it decides whether it knows the answer: below a similarity threshold it says it doesn't." Sensitive values are masked in this view.

**E3. The tools directly (no AI).**
```bash
TRIPMATE_DATA_DIR=$DEMO .venv/bin/python scripts/mcp_call.py get_flight_status '{"flight_number":"JL 44","date":"2026-11-30"}'
TRIPMATE_DATA_DIR=$DEMO LIVE_MODE=real .venv/bin/python scripts/mcp_call.py convert_currency '{"amount":100,"from_currency":"USD","to_currency":"JPY"}'
```
Say: "The assistant uses these same seven tools over the Model Context Protocol; here is one with fixture data and one with a real rate."

**E4. Plans you typed yourself.** Add "Japanese Garden Visit" on 1 Dec at 10:00 in the Itinerary tab, then ask `What are my travel plans?` -> it lists it (the itinerary is not a document, and is never cited as one).

**E5. Single vs multi agent.** `scripts/compare_modes.py <trip> --url http://localhost:8010 --yes` (about 2-3 minutes on the local model; uses LLM quota on Gemini). Shows seconds, LLM calls, citations and verifier drops per mode.

**E6. Dark mode and phone size.** Toggle OS dark mode; resize between 375 px and desktop.

## 4. Timing

| Scene | Minutes | Cumulative |
|---|---|---|
| 1 Problem | 0.5 | 0.5 |
| 2 Trip + documents | 1 | 1.5 |
| 3 Check-out with sources | 1.5 | 3 |
| 4 Flight | 1 | 4 |
| 5 Medication | 1 | 5 |
| 6 Places (optional) | 1 | 6 |
| 7 Itinerary + undo | 1.5 | 7.5 |
| 8 Honesty | 0.5 | 8 |
| 9 Multi-agent | 1 | 9 |
| 10 Wrap up | 0.5 | 9.5 |

With a local model add about 15 s per question: drop scene 6 and E-segments, or narrate while it streams.

## 5. If something goes wrong

| Symptom | Likely cause | Quick recovery |
|---|---|---|
| Chat says the assistant is not configured | missing key or model server down | check `curl localhost:8010/api/health`; start `make local-llm`; or restart the backend with `LLM_PROVIDER=demo` and say it is the stand-in |
| "rate limit" amber banner (Gemini) | 15 requests/min | wait; it resumes by itself; avoid asking two compound questions back to back |
| Very slow first answer | model loading | warm up before the demo (section 1) |
| Wrong value in an answer | small-model error | click the source chip and show the passage: it demonstrates why citations exist; re-ask once |
| Answer says "not found" for something in the documents | retrieval miss | re-ask with the document's words (e.g. "check-out"); in a pinch show the Source Drawer from another answer |
| A document stuck on Reading | embedding model not ready | reload; use `demo_seed.py` pre-seeded trip |
| Itinerary add not created | model skipped the tool | the "NOT changed" note appears: say so, add manually, move on |
| Backend crashed | n/a | restart with the same `TRIPMATE_DATA_DIR`; data persists |

## 6. Likely questions (honest answers)
- **Is it real AI?** Yes in modes A and B (hosted Gemini, or open-weight Qwen3-8B locally). Mode C is a scripted stand-in and is labelled as such.
- **Is live data real?** Flights are fixture data (no real provider); weather (Open-Meteo), exchange rates (Frankfurter) and places (OpenStreetMap, without opening hours or ratings) have a real mode (`LIVE_MODE=real`).
- **What if the model is wrong?** Answers carry citations, a verifier drops unsupported ones, and low-confidence or verify banners appear; the local 8B model is weaker than the hosted one.
- **Where is my data?** SQLite and a local Chroma folder on the machine. With a hosted model, the question and the retrieved passages go to the provider (with passport, booking reference and card values redacted first).
- **Offline?** Not in this version (the offline PWA was dropped from scope).
- **Accessibility?** Basics only (keyboard, labels); a full pass was dropped from scope.

## 7. Rehearsal
Run the whole script twice with the exact mode you will present, timing each scene. Record which questions needed a re-ask and keep the fallback line for those. Reset between runs with `rm -rf $DEMO` and a backend restart.
