"""Keeps one MCP tool-server subprocess alive for the whole app. A dedicated task owns the stdio
context so it is entered and exited from the same task (anyio requirement)."""
import asyncio

from ..mcp_client import McpToolClient


class McpHub:
    def __init__(self):
        self._task: asyncio.Task | None = None
        self._ready = asyncio.Event()
        self._stop = asyncio.Event()
        self._lock = asyncio.Lock()
        self._error: Exception | None = None
        self._client: McpToolClient | None = None
        self._tools: list[dict] = []

    async def _run(self):
        try:
            async with McpToolClient() as c:
                self._client, self._tools = c, await c.list_tools()
                self._ready.set()
                await self._stop.wait()
        except Exception as e:  # noqa: BLE001
            self._error = e
            self._ready.set()
        finally:
            self._client = None

    async def ensure(self):
        async with self._lock:
            if self._task is None or self._task.done():
                self._ready, self._stop, self._error = asyncio.Event(), asyncio.Event(), None
                self._task = asyncio.create_task(self._run())
            await self._ready.wait()
            if self._error:
                raise RuntimeError(f"MCP tool server failed to start: {self._error}")

    async def tools(self) -> list[dict]:
        await self.ensure()
        return self._tools

    async def call(self, name: str, args: dict) -> dict:
        await self.ensure()
        return await self._client.call(name, args)

    async def aclose(self):
        if self._task and not self._task.done():
            self._stop.set()
            await self._task
