import os

import pytest

os.environ["EMBEDDINGS"] = "hash"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TRIPMATE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("EMBEDDINGS", "hash")
    monkeypatch.setenv("AGENT_MODE", "single")  # the original suite covers single mode; multi has its own tests
    monkeypatch.setenv("VERIFIER_LLM_RESCUE", "false")  # same: the rescue has its own tests
    monkeypatch.setenv("ROUTER_LLM_FALLBACK", "false")  # existing tests script exact LLM turns; the fallback has its own tests
    monkeypatch.setenv("LIVE_MODE", "mock")  # never hit the network from tests, whatever .env says
    from app import config

    config.get_settings.cache_clear()
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c
    config.get_settings.cache_clear()
