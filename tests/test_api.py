"""
tests/test_api.py — Integration tests for FastAPI endpoints.
Uses TestClient (synchronous) to test all critical routes.
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    """Set up test DB and return a FastAPI test client."""
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///./data/vizag_test.db"
    os.environ["AQICN_TOKEN"] = "demo"
    os.environ["POLL_INTERVAL_SECONDS"] = "9999"  # Disable auto-polling

    from api.main import app
    import asyncio
    from ingestion.database import init_db

    asyncio.run(init_db())
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c

    # Cleanup test DB
    try:
        if Path("data/vizag_test.db").exists():
            Path("data/vizag_test.db").unlink()
    except PermissionError:
        pass


class TestHealthEndpoints:
    def test_root_ok(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


class TestLiveEndpoints:
    def test_live_aqi_no_data(self, client):
        """Without data, /api/live/aqi should return 503."""
        r = client.get("/api/live/aqi")
        assert r.status_code == 503

    def test_live_traffic_no_data(self, client):
        r = client.get("/api/live/traffic")
        assert r.status_code == 503

    def test_stats_empty_db(self, client):
        r = client.get("/api/live/stats?hours=24")
        assert r.status_code == 200


class TestPredictEndpoints:
    def test_predict_next_hour(self, client):
        """Should return 200 with fallback prediction even without model."""
        r = client.get("/api/predict/next-hour")
        assert r.status_code == 200
        data = r.json()
        assert "predicted_aqi" in data
        assert "model_used" in data

    def test_predict_invalid_n(self, client):
        r = client.get("/api/predict/next/25")
        assert r.status_code == 400

    def test_predict_valid_n(self, client):
        r = client.get("/api/predict/next/6")
        assert r.status_code == 200


class TestHistoryEndpoints:
    def test_aqi_history_empty(self, client):
        r = client.get("/api/history/aqi?hours=24")
        assert r.status_code == 200
        assert r.json()["count"] == 0

    def test_export_csv_no_data(self, client):
        r = client.get("/api/history/export/csv")
        assert r.status_code == 404


class TestAlertsEndpoints:
    def test_subscribe_valid(self, client):
        r = client.post("/api/alerts/subscribe", json={
            "email": "test@example.com",
            "name": "Test User",
            "threshold_aqi": 100,
        })
        assert r.status_code == 200
        assert r.json()["email"] == "test@example.com"

    def test_subscribe_invalid_email(self, client):
        r = client.post("/api/alerts/subscribe", json={
            "email": "not-an-email",
            "name": "Test",
            "threshold_aqi": 100,
        })
        assert r.status_code == 422

    def test_unsubscribe_existing(self, client):
        # First subscribe
        client.post("/api/alerts/subscribe", json={
            "email": "unsub@example.com",
            "name": "Unsub User",
            "threshold_aqi": 100,
        })
        # Then unsubscribe
        r = client.delete("/api/alerts/unsubscribe?email=unsub@example.com")
        assert r.status_code == 200

    def test_unsubscribe_unknown_email(self, client):
        r = client.delete("/api/alerts/unsubscribe?email=nobody@example.com")
        assert r.status_code == 404

class TestReportsEndpoints:
    def test_submit_report(self, client):
        report_data = {
            "latitude": 17.729,
            "longitude": 83.308,
            "issue_type": "Heavy Traffic",
            "description": "Traffic is completely jammed here",
            "severity": 4
        }
        response = client.post("/api/reports/", json=report_data)
        assert response.status_code == 200
        data = response.json()
        assert data["id"] is not None
        assert data["issue_type"] == "Heavy Traffic"

    def test_get_reports(self, client):
        response = client.get("/api/reports/")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 1
