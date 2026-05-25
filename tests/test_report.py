from zipfile import ZipFile

import json

from yt_audience_report.report import build_report, render_report_html, render_report_json, render_report_pdf, render_report_xlsx
from yt_audience_report.storage.sqlite import SQLiteStore


def test_build_report_requires_evidence_and_video_ideas(tmp_path):
    store = SQLiteStore(tmp_path / "report.sqlite3")
    store.upsert_channel(
        {
            "id": "UC123",
            "snippet": {"title": "Pocket Psych", "customUrl": "@pocketpsych"},
            "contentDetails": {"relatedPlaylists": {"uploads": "UU123"}},
        }
    )
    store.upsert_video({"id": "v1", "snippet": {"title": "Habits", "publishedAt": "2026-01-01T00:00:00Z"}, "statistics": {}}, "UC123")
    comments = [
        ("c1", "This applies only to neurotypical minds. Please discuss neurodivergent behaviour building."),
        ("c2", "How do you coregulate when you have no one and no support system?"),
        ("c3", "Do you have any advice about fear making mistakes at work and seeming stupid/incapable?"),
        ("c4", "Your videos are so clear and concise. I screenshot this to save it."),
        ("c5", "Any advice for not having any desire and tiny steps triggering dark thoughts?"),
    ]
    for comment_id, text in comments:
        store.upsert_comment({"id": comment_id, "snippet": {"textDisplay": text, "publishedAt": "2026-01-02T00:00:00Z"}}, "v1")

    report = build_report(store.conn, "UC123", max_comments=20)
    html = render_report_html(report)

    assert report.metrics.comments_analyzed == 5
    assert report.metrics.urgent_signals >= 2
    assert report.video_ideas
    assert "Core Audience Profile" in html
    assert "Why They Trust This Creator" in html
    assert "Loyalty and Return Signals" in html
    assert "Evidence Appendix" in html
    assert "#a95449" not in html.lower()
    assert ".idea-head > span:not(.severity)" in html
    store.close()


def test_render_report_pdf_and_xlsx(tmp_path):
    store = SQLiteStore(tmp_path / "report.sqlite3")
    store.upsert_channel(
        {
            "id": "UC123",
            "snippet": {"title": "Pocket Psych", "customUrl": "@pocketpsych"},
            "contentDetails": {"relatedPlaylists": {"uploads": "UU123"}},
        }
    )
    store.upsert_video({"id": "v1", "snippet": {"title": "Habits", "publishedAt": "2026-01-01T00:00:00Z"}, "statistics": {}}, "UC123")
    store.upsert_comment({"id": "c1", "snippet": {"textDisplay": "Your videos are clear and I need this reminder every day.", "publishedAt": "2026-01-02T00:00:00Z"}}, "v1")
    store.upsert_comment({"id": "c2", "snippet": {"textDisplay": "How do you coregulate when you have no support system?", "publishedAt": "2026-01-03T00:00:00Z"}}, "v1")
    report = build_report(store.conn, "UC123", max_comments=20)

    pdf_path = tmp_path / "report.pdf"
    xlsx_path = tmp_path / "report.xlsx"
    json_path = tmp_path / "report.json"
    render_report_pdf(report, pdf_path)
    render_report_xlsx(report, xlsx_path)
    render_report_json(report, json_path)

    assert pdf_path.read_bytes().startswith(b"%PDF-1.4")
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["channel"]["id"] == "UC123"
    assert data["video_ideas"]
    assert data["evidence_appendix"][0]["comment_id"]
    with ZipFile(xlsx_path) as workbook:
        names = set(workbook.namelist())
        assert "xl/workbook.xml" in names
        assert "xl/worksheets/sheet1.xml" in names
        assert "xl/worksheets/sheet4.xml" in names
    store.close()
