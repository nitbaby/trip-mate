# TripMate architecture

## System

```mermaid
flowchart TB
  subgraph Browser["Browser: React PWA"]
    UI["Chat / Itinerary / Docs / Settings"]
  end
  subgraph Backend["FastAPI backend"]
    API["REST + SSE"]
    Agents["Agent runtime (single or multi)"]
    Guard["Guardrails: trip_id injection, budgets, redaction, verify"]
    MCPC["MCP client (long-lived)"]
    Ingest["Ingestion: parse, chunk, classify, mask, embed"]
  end
  subgraph Tools["MCP tool server (stdio subprocess)"]
    T1["search_docs"]
    T2["read/write_itinerary"]
    T3["flight, weather, places, fx"]
  end
  subgraph Store["Local storage (data/)"]
    SQL[("SQLite: trips, docs, chunks, itinerary, chat")]
    VEC[("Chroma: chunk embeddings")]
    FILES[("uploads/")]
  end
  LLM["LLM: Gemini (default) / OpenAI-compatible / Claude / demo stand-in"]
  UI -->|"REST"| API
  UI <-->|"SSE events"| API
  API --> Agents --> LLM
  Agents --> Guard --> MCPC --> Tools
  API --> Ingest --> SQL
  Ingest --> VEC
  Ingest --> FILES
  T1 --> VEC
  T1 --> SQL
  T2 --> SQL
  T3 -->|"mock fixtures or Open-Meteo / Nominatim / Frankfurter"| EXT["External services"]
```

## One chat turn: multi-agent mode (`AGENT_MODE=multi`, default)

```mermaid
flowchart TD
  Q["User question"] --> R["Router (deterministic, no LLM call)"]
  R -->|"one intent"| S1["Specialist answers the user directly (streams tokens)"]
  R -->|"several intents"| P["Specialists run in parallel (no streaming)"]
  P --> C["Composer (1 LLM call, no tools) merges answers, streams tokens"]
  subgraph Specialists
    D["Documents agent: search_docs"]
    L["Live info agent: search_docs, flight, weather, places, fx"]
    I["Itinerary agent: read/write itinerary"]
  end
  S1 --- Specialists
  P --- Specialists
  S1 --> V
  C --> V["Verifier (deterministic): is each [n] claim supported by its passage or live tool result?"]
  V --> E["Events: citation (supported only), verified, confidence, verify badge, done"]
```

- Router intents: `docs`, `live`, `itinerary`. Unmatched questions go to the documents agent.
- Each specialist has its own prompt and a tool allowlist; calls outside the list are rejected.
- Budgets (6 tools per turn, 30 external calls per conversation) and `trip_id` injection are turn-wide and enforced by the backend, not the model.
- `AGENT_MODE=single` keeps the original one-agent loop (all tools). A request can override with `agentMode`.
- `scripts/compare_modes.py` runs both modes on the same questions (LLM calls, time, citations, dropped citations).

## RAG

```mermaid
flowchart LR
  subgraph Upload
    F["file"] --> Pa["parse"] --> Ch["chunk ~450 chars"] --> Cl["classify + key facts + mask"]
    Cl --> Em["embed (ONNX MiniLM, local)"] --> Ch2[("Chroma")]
    Ch --> Sq[("SQLite chunks")]
  end
  subgraph Ask
    Qe["query"] --> Eq["embed"] --> Kn["top-k in Chroma, filtered by trip"] --> Cf["confidence: high / low / none"]
    Cf --> Rd["redact sensitive values"] --> Nm["number passages [1] [2]"] --> Ag["agent writes answer with [n]"]
  end
```
