"""Backend-side MCP client: spawns the local TripMate MCP server over stdio and calls its tools."""
import json
import sys
from contextlib import AsyncExitStack

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .config import get_settings


class McpToolClient:
    def __init__(self):
        self._stack = AsyncExitStack()
        self.session: ClientSession | None = None

    async def __aenter__(self):
        st = get_settings()  # the SDK passes only a minimal env, so forward what the tools need (never the API key)
        env = {"TRIPMATE_DATA_DIR": str(st.tripmate_data_dir), "LIVE_MODE": st.live_mode, "EMBEDDINGS": st.embeddings}
        params = StdioServerParameters(command=sys.executable, args=["-m", "tripmate_mcp.server"], env=env)
        read, write = await self._stack.enter_async_context(stdio_client(params))
        self.session = await self._stack.enter_async_context(ClientSession(read, write))
        await self.session.initialize()
        return self

    async def __aexit__(self, *exc):
        await self._stack.aclose()

    async def list_tools(self) -> list[dict]:
        """Tool definitions in Anthropic tool-use format."""
        res = await self.session.list_tools()
        return [{"name": t.name, "description": t.description or "", "input_schema": t.inputSchema} for t in res.tools]

    async def call(self, name: str, args: dict) -> dict:
        res = await self.session.call_tool(name, args)
        text = "".join(c.text for c in res.content if getattr(c, "text", None))
        if res.isError:
            return {"error": {"code": "AGENT_FAILED", "message": text[:200]}}
        return json.loads(text)
