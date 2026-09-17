"""End-to-end API test with fetching mocked (no network)."""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(sample_html, monkeypatch, tmp_path):
    # Isolate DB to a temp file for this test module.
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path/'api.db'}")
    # Import inside the fixture so the env var is picked up by settings/engine.
    from app.config import get_settings

    get_settings.cache_clear()
    import importlib

    from app import db as db_module

    importlib.reload(db_module)
    from app.web import deps as deps_module

    importlib.reload(deps_module)
    from app import main as main_module

    importlib.reload(main_module)

    # Patch the network fetch to return our fixture HTML.
    from app.services import collector

    monkeypatch.setattr(collector, "fetch_channel_html", lambda username, client=None: sample_html)

    with TestClient(main_module.app) as c:
        yield c


def test_add_channel_and_list(client):
    resp = client.post("/api/channels", json={"username": "@sample"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["username"] == "sample"
    assert data["status"] == "active"
    assert data["post_count"] == 3

    # Adding the same channel again is rejected (natural key / no duplicates).
    dup = client.post("/api/channels", json={"username": "sample"})
    assert dup.status_code == 409

    # Dashboard renders.
    page = client.get("/")
    assert page.status_code == 200
    assert "Sample Channel" in page.text


def test_invalid_username_rejected(client):
    resp = client.post("/api/channels", json={"username": "!!"})
    assert resp.status_code == 422


def test_healthz(client):
    resp = client.get("/api/healthz")
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
