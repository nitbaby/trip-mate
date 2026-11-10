"""LLM adapter. The agent loop only needs: an async generator of ("text", str) chunks followed by one
("final", {"content": [blocks], "stop_reason": str}). Tests substitute a scripted fake with the same shape."""
from collections.abc import AsyncIterator

import anthropic


class AnthropicLLM:
    def __init__(self, api_key: str, model: str, max_tokens: int = 2048):
        self.client = anthropic.AsyncAnthropic(api_key=api_key)
        self.model, self.max_tokens = model, max_tokens

    async def turn(self, system: str, tools: list[dict], messages: list[dict]) -> AsyncIterator[tuple[str, object]]:
        async with self.client.messages.stream(model=self.model, max_tokens=self.max_tokens, system=system,
                                               tools=tools, messages=messages) as stream:
            async for text in stream.text_stream:
                yield "text", text
            final = await stream.get_final_message()
        blocks = []
        for b in final.content:
            if b.type == "text":
                blocks.append({"type": "text", "text": b.text})
            elif b.type == "tool_use":
                blocks.append({"type": "tool_use", "id": b.id, "name": b.name, "input": b.input})
        yield "final", {"content": blocks, "stop_reason": final.stop_reason}
