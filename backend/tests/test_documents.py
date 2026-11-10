import time

HOTEL = b"""Hotel: Shinjuku Granbell Hotel
Confirmation number: ABC12345
Check-in: 3:00 PM
Check-out: 11:00 AM
Breakfast is included for all guests.
Passport: X1234567
"""


def mk(client):
    return client.post("/api/trips", json={"name": "J", "destinations": ["Tokyo"], "start_date": "2026-12-01",
                                           "end_date": "2026-12-10"}).json()["id"]


def wait_ready(client, tid, did):
    for _ in range(50):
        s = client.get(f"/api/trips/{tid}/documents/{did}/status").json()
        if s["status"] in ("ready", "failed"):
            return s
        time.sleep(0.1)
    raise AssertionError("ingestion timed out")


def test_upload_ingest_masking_and_reveal(client):
    tid = mk(client)
    r = client.post(f"/api/trips/{tid}/documents", files={"file": ("hotel.txt", HOTEL, "text/plain")})
    assert r.status_code == 202
    did = r.json()["id"]
    assert wait_ready(client, tid, did)["doc_type"] == "confirmation"
    doc = client.get(f"/api/trips/{tid}").json()["documents"][0]
    facts = {f["label"]: f for f in doc["key_facts"]}
    assert facts["Check-out"]["value"].startswith("11:00")
    assert "ABC12345" not in str(doc) and "X1234567" not in str(doc)
    assert facts["Booking reference"]["sensitive"] and facts["Booking reference"]["value"].endswith("45")
    rev = client.get(f"/api/documents/{did}/facts/{facts['Passport number']['index']}/reveal").json()
    assert rev == {"value": "X1234567", "reveal_seconds": 30}
    assert client.get(f"/api/documents/{did}/facts/{facts['Check-out']['index']}/reveal").status_code == 404


def test_chunk_endpoint_and_vector_search(client):
    from app import vectors

    tid = mk(client)
    did = client.post(f"/api/trips/{tid}/documents", files={"file": ("hotel.txt", HOTEL, "text/plain")}).json()["id"]
    wait_ready(client, tid, did)
    hits = vectors.query(tid, "what time is check-out", k=3)
    assert hits and "Check-out" in hits[0]["text"]
    c = client.get(f"/api/documents/{did}/chunks/{hits[0]['chunk_id']}").json()
    assert c["document_name"] == "hotel.txt" and c["page"] == 1
    assert vectors.query("other-trip", "check-out") == []


def test_rejects_bad_type_and_missing_trip_and_failed_ingest(client):
    tid = mk(client)
    assert client.post(f"/api/trips/{tid}/documents", files={"file": ("a.exe", b"x")}).status_code == 422
    assert client.post("/api/trips/nope/documents", files={"file": ("a.txt", b"x")}).status_code == 404
    did = client.post(f"/api/trips/{tid}/documents", files={"file": ("empty.txt", b"   ")}).json()["id"]
    s = wait_ready(client, tid, did)
    assert s["status"] == "failed" and "No extractable" in s["error"]


def test_delete_document(client):
    tid = mk(client)
    did = client.post(f"/api/trips/{tid}/documents", files={"file": ("hotel.txt", HOTEL)}).json()["id"]
    wait_ready(client, tid, did)
    assert client.delete(f"/api/trips/{tid}/documents/{did}").status_code == 204
    assert client.get(f"/api/trips/{tid}").json()["documents"] == []


def test_chunk_and_search_text_are_redacted(client):
    from app.tools import impl

    tid = mk(client)
    did = client.post(f"/api/trips/{tid}/documents", files={"file": ("hotel.txt", HOTEL)}).json()["id"]
    wait_ready(client, tid, did)
    hit = impl.search_docs(tid, "confirmation passport")["results"][0]
    assert "ABC12345" not in hit["text"] and "X1234567" not in hit["text"] and "Check-out" in hit["text"]
    c = client.get(f"/api/documents/{did}/chunks/{hit['chunk_id']}").json()
    assert "X1234567" not in str(c) and "ABC12345" not in str(c)


def test_relative_data_dir_is_anchored_to_repo_root(monkeypatch):
    from app import config

    monkeypatch.setenv("TRIPMATE_DATA_DIR", "./data-reltest")
    monkeypatch.chdir("/")
    config.get_settings.cache_clear()
    try:
        assert config.get_settings().tripmate_data_dir == (config.REPO_ROOT / "data-reltest").resolve()
    finally:
        import shutil

        shutil.rmtree(config.REPO_ROOT / "data-reltest", ignore_errors=True)
        config.get_settings.cache_clear()
