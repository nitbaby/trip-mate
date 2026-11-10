import itertools

_ids = itertools.count(1)


class ScriptedLLM:
    """Stands in for AnthropicLLM. Each turn is a dict {text, tools:[(name,input)], raise} or a callable
    (system, tools, messages) -> dict."""

    def __init__(self, turns):
        self.turns, self.calls = list(turns), []

    async def turn(self, system, tools, messages):
        self.calls.append({"system": system, "tools": tools, "messages": [dict(m) for m in messages]})
        t = self.turns.pop(0)
        if callable(t):
            t = t(system, tools, messages)
        text = t.get("text", "")
        if text:
            mid = len(text) // 2
            yield "text", text[:mid]
            if t.get("raise"):
                raise t["raise"]
            yield "text", text[mid:]
        elif t.get("raise"):
            raise t["raise"]
        blocks = [{"type": "text", "text": text}] if text else []
        for name, inp in t.get("tools", []):
            blocks.append({"type": "tool_use", "id": f"tu_{next(_ids)}", "name": name, "input": inp})
        yield "final", {"content": blocks, "stop_reason": "tool_use" if t.get("tools") else "end_turn"}
