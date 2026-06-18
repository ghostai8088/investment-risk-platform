"""Placeholder tests proving backend wiring. No domain logic."""

from __future__ import annotations

from fastapi.testclient import TestClient

from irp_backend.main import app

client = TestClient(app)


def test_health() -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_version() -> None:
    resp = client.get("/version")
    assert resp.status_code == 200
    body = resp.json()
    assert "version" in body
    assert "env" in body
