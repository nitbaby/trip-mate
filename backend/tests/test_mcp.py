import time

from app.mcp_client import McpToolClient

HOTEL = b"Hotel: Shinjuku Granbell Hotel\nCheck-in: 3:00 PM\nCheck-out: 11:00 AM\nBreakfast is included for 2 guests.\n"


async def test_mcp_end_to_end(client):
    tid = client.post("/api/trips", json={"name": "J", "destinations": ["Tokyo"], "start_date": "2026-11-30",
                                          "end_date": "2026-12-06", "timezone": "Asia/Tokyo"}).json()["id"]
    did = client.post(f"/api/trips/{tid}/documents", files={"file": ("hotel.txt", HOTEL)}).json()["id"]
    for _ in range(50):
        if client.get(f"/api/trips/{tid}/documents/{did}/status").json()["status"] == "ready":
            break
        time.sleep(0.1)

    async with McpToolClient() as mcp:
        tools = {t["name"]: t for t in await mcp.list_tools()}
        assert set(tools) == {"search_docs", "read_itinerary", "write_itinerary", "get_flight_status",
                              "get_weather", "search_places", "convert_currency"}
        assert tools["get_flight_status"]["input_schema"]["required"] == ["flight_number", "date"]

        docs = await mcp.call("search_docs", {"trip_id": tid, "query": "what time is check-out"})
        assert "Check-out" in docs["results"][0]["text"] and docs["results"][0]["document_name"] == "hotel.txt"

        f = await mcp.call("get_flight_status", {"flight_number": "JL44", "date": "2026-11-30"})
        assert f["status"] == "delayed" and f["last_updated"]

        p = await mcp.call("search_places", {"location": "Shinjuku Granbell Hotel", "vegetarian": True, "trip_id": tid})
        assert p["results"]

        w = await mcp.call("write_itinerary", {"trip_id": tid, "action": "create", "type": "reservation",
                                               "title": "Dinner", "start_at": "2026-12-01T20:00:00"})
        assert w["item"]["source"] == "agent" and w["undo_id"]
        assert len((await mcp.call("read_itinerary", {"trip_id": tid}))["items"]) == 1

        bad = await mcp.call("get_flight_status", {"flight_number": "nope", "date": "2026-11-30"})
        assert bad["error"]["code"] == "VALIDATION_FAILED"
        miss = await mcp.call("read_itinerary", {"trip_id": "missing"})
        assert miss["error"]["code"] == "NOT_FOUND"
