"""Poke the TripMate MCP server from the command line.

  .venv/bin/python scripts/mcp_call.py                       # list tools
  .venv/bin/python scripts/mcp_call.py get_flight_status '{"flight_number":"JL44","date":"2026-11-30"}'
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.mcp_client import McpToolClient  # noqa: E402


async def main():
    async with McpToolClient() as mcp:
        if len(sys.argv) < 2:
            for t in await mcp.list_tools():
                props = ", ".join(t["input_schema"].get("properties", {}))
                print(f"{t['name']}({props})\n    {t['description'].splitlines()[0]}")
            return
        args = json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}
        print(json.dumps(await mcp.call(sys.argv[1], args), indent=2))


asyncio.run(main())
