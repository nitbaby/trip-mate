from datetime import datetime

import pytest
from app.tools import fx, impl, places

TRIP = {"name": "J", "destinations": ["Tokyo"], "start_date": "2026-11-30", "end_date": "2026-12-06",
        "timezone": "Asia/Tokyo"}


@pytest.fixture
def tid(client):
    return client.post("/api/trips", json=TRIP).json()["id"]


def test_flight_mock_and_cache(tid):
    r = impl.get_flight_status("JL 44", "2026-11-30")
    assert r["status"] == "delayed" and r["delay_minutes"] == 35 and r["estimated_departure"].endswith("18:35:00")
    assert r["cached"] is False and r["last_updated"]
    assert impl.get_flight_status("jl44", "2026-11-30")["cached"] is True
    assert impl.get_flight_status("JL43", "2026-12-06")["status"] == "on_time"
    with pytest.raises(ValueError):
        impl.get_flight_status("banana", "2026-11-30")


def test_weather_and_fx(tid):
    w = impl.get_weather("Tokyo", 3)
    assert len(w["daily"]) == 3 and w["last_updated"]
    r = fx.convert_currency(100, "usd", "jpy")
    assert r["converted"] == 15100.0 and r["last_updated"]
    assert fx.convert_currency(5, "GBP", "GBP")["converted"] == 5
    with pytest.raises(ValueError):
        fx.convert_currency(1, "USD", "XXX")


def test_places_vegetarian_open_now_and_distance(tid):
    noon = datetime.fromisoformat("2026-12-01T20:00:00")
    r = places.search_places("Shinjuku Granbell Hotel", "", vegetarian=True, open_now=True, now=noon)
    names = [p["name"] for p in r["results"]]
    assert "Ain Soph. Journey Shinjuku" in names and "Kabukicho 24h Ramen" not in names
    assert "Daigo Shojin Ryori" not in names  # closed at 20:00
    assert all(p["open_now"] and p["vegetarian_friendly"] for p in r["results"])
    assert r["results"] == sorted(r["results"], key=lambda p: p["distance_m"])
    # past-midnight hours: yakitori open at 01:00
    late = places.search_places("shinjuku", "yakitori", now=datetime.fromisoformat("2026-12-02T01:00:00"))
    assert late["results"][0]["open_now"] is True
    with pytest.raises(ValueError):
        places.search_places("Atlantis")


def test_places_rest_and_status(client, tid):
    r = client.get(f"/api/trips/{tid}/places", params={"location": "shinjuku", "vegetarian": True}).json()
    assert r["results"] and "open_now" in r["results"][0]
    s = client.get(f"/api/trips/{tid}/status").json()
    assert {i["name"] for i in s["integrations"]} == {"flight", "weather", "places", "fx"}
    assert next(i for i in s["integrations"] if i["name"] == "places")["last_contacted"]


def test_agent_write_and_undo(client, tid):
    base = f"/api/trips/{tid}"
    r = impl.write_itinerary(tid, "create", type="reservation", title="Dinner", start_at="2026-12-02T20:00:00",
                             end_at="2026-12-02T21:30:00")
    assert r["item"]["source"] == "agent" and r["undo_id"]
    items = client.get(f"{base}/itinerary").json()
    assert len(items) == 1 and items[0]["source"] == "agent"
    # update then undo restores the title
    u = impl.write_itinerary(tid, "update", item_id=r["item_id"], title="Dinner at Ain Soph")
    assert client.get(f"{base}/itinerary").json()[0]["title"] == "Dinner at Ain Soph"
    client.post(f"{base}/undo/{u['undo_id']}")
    assert client.get(f"{base}/itinerary").json()[0]["title"] == "Dinner"
    # delete then undo restores the item
    d = impl.write_itinerary(tid, "delete", item_id=r["item_id"])
    assert client.get(f"{base}/itinerary").json() == []
    client.post(f"{base}/undo/{d['undo_id']}")
    assert len(client.get(f"{base}/itinerary").json()) == 1
    # undo create removes it; second undo is rejected
    client.post(f"{base}/undo/{r['undo_id']}")
    assert client.get(f"{base}/itinerary").json() == []
    assert client.post(f"{base}/undo/{r['undo_id']}").status_code == 409
    assert client.post(f"{base}/undo/nope").status_code == 404


def test_agent_write_conflict_and_validation(client, tid):
    impl.write_itinerary(tid, "create", type="activity", title="A", start_at="2026-12-02T20:00:00")
    r = impl.write_itinerary(tid, "create", type="reservation", title="B", start_at="2026-12-02T20:00:00")
    assert len(r["conflicts_with"]) == 1
    with pytest.raises(Exception):
        impl.write_itinerary(tid, "create", type="bogus", title="x", start_at="2026-12-02T20:00:00")
    with pytest.raises(Exception):
        impl.write_itinerary(tid, "update", title="no id")
