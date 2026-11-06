import os

import pytest

os.environ["EMBEDDINGS"] = "hash"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("TRIPMATE_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("EMBEDDINGS", "hash")
    from app import config

    config.get_settings.cache_clear()
    from app.main import app
    from fastapi.testclient import TestClient

    with TestClient(app) as c:
        yield c
    config.get_settings.cache_clear()
