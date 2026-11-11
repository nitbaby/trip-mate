TRIP = {"name": "Japan", "destinations": ["Tokyo"], "start_date": "2026-12-01",
        "end_date": "2026-12-10", "timezone": "Asia/Tokyo"}


def mk(client):
    return client.post("/api/trips", json=TRIP).json()["id"]


def test_trip_crud_and_validation(client):
    tid = mk(client)
    assert client.get("/api/trips").json()[0]["destinations"] == ["Tokyo"]
    assert client.get(f"/api/trips/{tid}").json()["itinerary"] == []
    bad = client.post("/api/trips", json={**TRIP, "end_date": "2026-11-01"})
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "VALIDATION_FAILED"
    nf = client.get("/api/trips/nope")
    assert nf.status_code == 404 and nf.json()["error"]["code"] == "NOT_FOUND"


def test_itinerary_crud_and_conflicts(client):
    tid = mk(client)
    base = f"/api/trips/{tid}/itinerary"
    a = client.post(base, json={"type": "reservation", "title": "Dinner", "start_at": "2026-12-02T20:00:00",
                                "end_at": "2026-12-02T21:30:00"}).json()
    client.post(base, json={"type": "activity", "title": "Show", "start_at": "2026-12-02T21:00:00",
                            "end_at": "2026-12-02T22:00:00"})
    client.post(base, json={"type": "activity", "title": "Later", "start_at": "2026-12-03T10:00:00"})
    items = client.get(base).json()
    assert len(items) == 3
    assert len(items[0]["conflicts_with"]) == 1 and items[2]["conflicts_with"] == []
    r = client.patch(f"{base}/{a['id']}", json={"title": "Dinner at Sushi Dai"})
    assert r.json()["title"] == "Dinner at Sushi Dai"
    assert client.delete(f"{base}/{a['id']}").status_code == 204
    assert client.delete(f"{base}/{a['id']}").status_code == 404
    assert client.post(base, json={"type": "bogus", "title": "x", "start_at": "2026-12-02T20:00:00"}).status_code == 422


def test_agent_source_persisted(client):
    tid = mk(client)
    r = client.post(f"/api/trips/{tid}/itinerary", json={
        "type": "reservation", "title": "Dinner", "start_at": "2026-12-02T20:00:00", "source": "agent"})
    assert r.json()["source"] == "agent"


def test_date_only_range_includes_the_whole_end_day(client):
    from app.tools import impl
    tid = mk(client)
    base = f"/api/trips/{tid}/itinerary"
    client.post(base, json={"type": "activity", "title": "Garden", "start_at": "2026-12-01T10:00:00"})
    client.post(base, json={"type": "activity", "title": "Late", "start_at": "2026-12-01T23:30:00"})
    client.post(base, json={"type": "activity", "title": "Next day", "start_at": "2026-12-02T09:00:00"})
    names = lambda a, b: [i["title"] for i in impl.read_itinerary(tid, a, b)["items"]]  # noqa: E731
    assert names("2026-12-01", "2026-12-01") == ["Garden", "Late"]
    assert names("2026-12-01T00:00:00", "2026-12-01T12:00:00") == ["Garden"]  # full datetimes still exact
    assert len(names(None, None)) == 3
