"""Check that the configured LLM provider/key/model works, and list available models.

  .venv/bin/python scripts/llm_check.py          # test a tiny completion with the configured model
  .venv/bin/python scripts/llm_check.py --models # also list model names the key can use
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.agent.llm import LLMError, build_llm, missing_key_message
from app.config import get_settings


async def main():
    s = get_settings()
    print(f"provider: {s.llm_provider}")
    llm = build_llm(s)
    if llm is None:
        raise SystemExit(missing_key_message(s))
    print(f"model:    {llm.model}")
    if "--models" in sys.argv and hasattr(llm, "client") and hasattr(llm.client, "models"):
        try:
            ids = sorted(m.id for m in (await llm.client.models.list()).data)
            print("available:", ", ".join(i.removeprefix("models/") for i in ids))
        except Exception as e:  # noqa: BLE001
            print("could not list models:", type(e).__name__)
    try:
        text = ""
        async for kind, payload in llm.turn("Reply with the single word: pong", [], [{"role": "user", "content": "ping"}]):
            if kind == "text":
                text += payload
        print("reply:   ", text.strip()[:80] or "(empty)", "\nOK")
    except LLMError as e:
        raise SystemExit(f"FAILED: {e.message}")


asyncio.run(main())
