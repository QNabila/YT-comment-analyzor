from __future__ import annotations

import json

from fastapi.testclient import TestClient

from yt_audience_report.dashboard import create_app
from yt_audience_report.report import build_report, render_report_json
from yt_audience_report.storage.sqlite import SQLiteStore


def _seed_store(tmp_path):
    store = SQLiteStore(tmp_path / "dashboard.sqlite3")
    store.upsert_channel(
        {
            "id": "UC123",
            "snippet": {"title": "Pocket Psych", "customUrl": "@pocketpsych"},
            "contentDetails": {"relatedPlaylists": {"uploads": "UU123"}},
        }
    )
    store.upsert_video({"id": "v1", "snippet": {"title": "Habits", "publishedAt": "2026-01-01T00:00:00Z"}, "statistics": {}}, "UC123")
    store.upsert_comment({"id": "c1", "snippet": {"textDisplay": "Your videos are clear and concise.", "publishedAt": "2026-01-02T00:00:00Z"}}, "v1")
    store.upsert_comment({"id": "c2", "snippet": {"textDisplay": "How do you coregulate with no support system?", "publishedAt": "2026-01-03T00:00:00Z"}}, "v1")
    return store


def test_dashboard_channels_and_missing_report_empty_state(tmp_path):
    store = _seed_store(tmp_path)
    app = create_app(store.db_path, tmp_path / "reports")
    client = TestClient(app)

    channels = client.get("/api/channels")
    assert channels.status_code == 200
    assert channels.json()["channels"][0]["handle"] == "pocketpsych"

    missing = client.get("/api/report?channel=@pocketpsych")
    assert missing.status_code == 404
    assert "python main.py --channel @pocketpsych --no-fetch" in missing.json()["message"]
    store.close()


def test_dashboard_report_and_comment_volume(tmp_path):
    store = _seed_store(tmp_path)
    report = build_report(store.conn, "UC123", max_comments=20)
    reports_dir = tmp_path / "reports"
    render_report_json(report, reports_dir / "pocketpsych_2026-05-25_audience_report.json")

    app = create_app(store.db_path, reports_dir)
    client = TestClient(app)

    html = client.get("/")
    assert html.status_code == 200
    assert "Audience Intelligence Dashboard" in html.text

    report_response = client.get("/api/report?channel=pocketpsych")
    assert report_response.status_code == 200
    data = report_response.json()["report"]
    assert data["channel"]["id"] == "UC123"
    assert data["evidence_appendix"][0]["comment_id"]

    volume = client.get("/api/comment-volume?channel=UC123")
    assert volume.status_code == 200
    assert volume.json()["videos"][0]["comments"] == 2
    store.close()
