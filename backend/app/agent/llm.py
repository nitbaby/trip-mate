"""LLM adapters. The agent loop only needs: an async generator of ("text", str) chunks followed by one
("final", {"content": [blocks], "stop_reason": str}). Blocks use the Anthropic shape (text / tool_use /
tool_result) as the canonical format; each adapter translates to its provider's wire format.
Tests substitute a scripted fake with the same shape."""
import json
import uuid
from collections.abc import AsyncIterator

import anthropic
import httpx
import openai

from ..config import Settings


class LLMError(Exception):
    """Provider-independent failure, already phrased for the end user."""

    def __init__(self, message: str, retryable: bool):
        super().__init__(message)
        self.message, self.retryable = message, retryable


# ---------- OpenAI-compatible (Gemini default, Groq, OpenRouter, Ollama, ...) ----------

def sanitize_schema(node):
    """Gemini's function schema is a strict OpenAPI subset: drop title/default/additionalProperties and
    collapse Optional[...] (anyOf with null) to the non-null type."""
    if isinstance(node, list):
        return [sanitize_schema(x) for x in node]
    if not isinstance(node, dict):
        return node
    node = {k: v for k, v in node.items() if k not in ("title", "default", "additionalProperties", "$schema")}
    if "anyOf" in node:
        options = [o for o in node["anyOf"] if o.get("type") != "null"]
        rest = {k: v for k, v in node.items() if k != "anyOf"}
        if len(options) == 1:
            return sanitize_schema({**options[0], **rest})
        node = {**rest, "anyOf": options}
    return {k: sanitize_schema(v) for k, v in node.items()}


def to_openai_tools(tools: list[dict]) -> list[dict]:
    return [{"type": "function", "function": {"name": t["name"], "description": t["description"],
                                              "parameters": sanitize_schema(t["input_schema"])}} for t in tools]


def to_openai_messages(system: str, messages: list[dict]) -> list[dict]:
    out = [{"role": "system", "content": system}]
    for m in messages:
        c = m["content"]
        if isinstance(c, str):
            out.append({"role": m["role"], "content": c})
        elif m["role"] == "assistant":
            text = "".join(b["text"] for b in c if b["type"] == "text")
            calls = []
            for b in c:
                if b["type"] == "tool_use":
                    call = {"id": b["id"], "type": "function",
                            "function": {"name": b["name"], "arguments": json.dumps(b["input"])}}
                    if b.get("extra_content"):  # e.g. Gemini thought signatures must be echoed back
                        call["extra_content"] = b["extra_content"]
                    calls.append(call)
            msg = {"role": "assistant", "content": text or None}
            if calls:
                msg["tool_calls"] = calls
            out.append(msg)
        else:  # user turn made of tool_result blocks
            for b in c:
                out.append({"role": "tool", "tool_call_id": b["tool_use_id"], "content": b["content"]})
    return out


class OpenAICompatLLM:
    def __init__(self, api_key: str, model: str, base_url: str, max_tokens: int = 2048,
                 http_client: httpx.AsyncClient | None = None, provider_name: str = "LLM",
                 reasoning_effort: str | None = None):
        # default SDK timeout is 10 minutes; a stalled free-tier request must not freeze the chat
        self.client = openai.AsyncOpenAI(api_key=api_key, base_url=base_url, http_client=http_client, max_retries=1,
                                         timeout=httpx.Timeout(60.0, connect=10.0))
        self.model, self.max_tokens, self.provider = model, max_tokens, provider_name
        self.reasoning_effort = reasoning_effort

    def _wrap(self, e: Exception) -> LLMError:
        p = self.provider
        if isinstance(e, (openai.AuthenticationError, openai.PermissionDeniedError)):
            return LLMError(f"{p} rejected the API key. Check the key in .env.", False)
        if isinstance(e, openai.NotFoundError):
            return LLMError(f"{p} does not know the model '{self.model}'. Set a valid model name in .env.", False)
        if isinstance(e, openai.RateLimitError):
            return LLMError(f"{p} rate limit reached (free tiers are limited). Wait a minute and retry.", True)
        if isinstance(e, openai.APITimeoutError):
            return LLMError(f"{p} took too long to answer. Please retry, or try a lighter model.", True)
        if isinstance(e, openai.APIConnectionError):
            return LLMError(f"Could not reach {p}. Check your connection and retry.", True)
        if isinstance(e, openai.APIStatusError) and e.status_code >= 500:
            return LLMError(f"{p} is having problems. Please retry.", True)
        if isinstance(e, openai.APIStatusError):
            return LLMError(f"{p} rejected the request ({e.status_code}).", False)
        return LLMError("The assistant hit an unexpected error.", True)

    async def turn(self, system: str, tools: list[dict], messages: list[dict]) -> AsyncIterator[tuple[str, object]]:
        text = ""
        calls: list[dict] = []  # {id, name, args, extra}
        finish = None
        try:
            stream = await self.client.chat.completions.create(
                model=self.model, max_tokens=self.max_tokens, temperature=0.2, stream=True,
                messages=to_openai_messages(system, messages), tools=to_openai_tools(tools) or openai.NOT_GIVEN,
                reasoning_effort=self.reasoning_effort or openai.NOT_GIVEN)
            async for chunk in stream:
                if not chunk.choices:
                    continue
                ch = chunk.choices[0]
                d = ch.delta
                if d.content:
                    text += d.content
                    yield "text", d.content
                for tc in d.tool_calls or []:
                    fn = tc.function
                    if fn and fn.name:  # a name only ever appears on the first fragment of a call
                        calls.append({"id": tc.id or f"call_{uuid.uuid4().hex[:10]}", "name": fn.name, "args": "",
                                      "index": tc.index, "extra": (tc.model_extra or {}).get("extra_content")})
                    if fn and fn.arguments is not None and calls:
                        target = next((c for c in reversed(calls) if c["index"] == tc.index), calls[-1])
                        target["args"] += fn.arguments
                if ch.finish_reason:
                    finish = ch.finish_reason
        except openai.OpenAIError as e:
            raise self._wrap(e) from e
        blocks = [{"type": "text", "text": text}] if text else []
        for c in calls:
            try:
                args = json.loads(c["args"] or "{}")
            except json.JSONDecodeError:
                args = {}
            block = {"type": "tool_use", "id": c["id"], "name": c["name"], "input": args if isinstance(args, dict) else {}}
            if c["extra"]:
                block["extra_content"] = c["extra"]
            blocks.append(block)
        yield "final", {"content": blocks, "stop_reason": "tool_use" if calls else (finish or "end_turn")}


# ---------- Anthropic ----------

class AnthropicLLM:
    def __init__(self, api_key: str, model: str, max_tokens: int = 2048):
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model, self.max_tokens = model, max_tokens

    async def turn(self, system: str, tools: list[dict], messages: list[dict]) -> AsyncIterator[tuple[str, object]]:
        try:
            async with self.client.messages.stream(model=self.model, max_tokens=self.max_tokens, system=system,
                                                   tools=tools, messages=messages) as stream:
                async for text in stream.text_stream:
                    yield "text", text
                final = await stream.get_final_message()
        except anthropic.AuthenticationError as e:
            raise LLMError("Anthropic rejected the API key. Check ANTHROPIC_API_KEY.", False) from e
        except (anthropic.RateLimitError, anthropic.APIConnectionError) as e:
            raise LLMError("The assistant is busy or unreachable. Please retry.", True) from e
        except anthropic.APIStatusError as e:
            raise LLMError("Anthropic had a problem with this request.", e.status_code >= 500) from e
        blocks = []
        for b in final.content:
            if b.type == "text":
                blocks.append({"type": "text", "text": b.text})
            elif b.type == "tool_use":
                blocks.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
        yield "final", {"content": blocks, "stop_reason": final.stop_reason}


# ---------- factory ----------

def missing_key_message(s: Settings) -> str:
    name = {"gemini": "GEMINI_API_KEY", "openai": "LLM_API_KEY (and LLM_MODEL, LLM_BASE_URL)",
            "anthropic": "ANTHROPIC_API_KEY"}.get(s.llm_provider, "LLM_PROVIDER (gemini, openai or anthropic)")
    return f"{name} is not set. Add it to .env and restart."


def build_llm(s: Settings):
    """Return the configured LLM adapter, or None when it is not configured."""
    if s.llm_provider == "gemini" and s.gemini_api_key:
        return OpenAICompatLLM(s.gemini_api_key, s.gemini_model, s.gemini_base_url, provider_name="Gemini",
                               reasoning_effort=s.gemini_reasoning_effort or None)
    if s.llm_provider == "openai" and s.llm_api_key and s.llm_model and s.llm_base_url:
        return OpenAICompatLLM(s.llm_api_key, s.llm_model, s.llm_base_url, provider_name="The LLM provider")
    if s.llm_provider == "anthropic" and s.anthropic_api_key:
        return AnthropicLLM(s.anthropic_api_key, s.anthropic_model)
    return None
