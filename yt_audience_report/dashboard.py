from __future__ import annotations

import argparse
import json
from html import escape
from pathlib import Path
import re
import sqlite3
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from yt_audience_report.palette import MOCK_PALETTE, palette_css_vars


def create_app(db_path: str | Path = "data/yt-audience-report.sqlite3", reports_dir: str | Path = "reports") -> FastAPI:
    app = FastAPI(title="yt-audience-report dashboard")
    state = {"db_path": Path(db_path), "reports_dir": Path(reports_dir)}
    static_dir = Path(__file__).with_name("dashboard_static")
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        channels = _list_channels(state["db_path"])
        return _dashboard_html(channels)

    @app.get("/api/channels")
    def channels() -> JSONResponse:
        return JSONResponse({"channels": _list_channels(state["db_path"])})

    @app.get("/api/report")
    def report(channel: str = Query(..., min_length=1)) -> JSONResponse:
        channel_row = _resolve_channel(state["db_path"], channel)
        if not channel_row:
            raise HTTPException(status_code=404, detail="Channel not found in SQLite.")
        report_path = _latest_report_json(state["reports_dir"], channel_row)
        if not report_path:
            return JSONResponse(
                {
                    "status": "missing_report",
                    "channel": channel_row,
                    "message": f"Run python main.py --channel @{channel_row['handle'] or channel_row['channel_id']} --no-fetch to generate the dashboard report JSON.",
                },
                status_code=404,
            )
        return JSONResponse({"status": "ok", "report": json.loads(report_path.read_text(encoding="utf-8"))})

    @app.get("/api/comment-volume")
    def comment_volume(channel: str = Query(..., min_length=1)) -> JSONResponse:
        channel_row = _resolve_channel(state["db_path"], channel)
        if not channel_row:
            raise HTTPException(status_code=404, detail="Channel not found in SQLite.")
        return JSONResponse({"channel": channel_row, "videos": _comment_volume(state["db_path"], channel_row["channel_id"])})

    return app


def _connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _list_channels(db_path: Path) -> list[dict[str, str]]:
    if not db_path.exists():
        return []
    with _connect(db_path) as conn:
        rows = conn.execute("SELECT channel_id, handle, title FROM channels ORDER BY last_fetched_at DESC").fetchall()
    return [_channel_dict(row) for row in rows]


def _resolve_channel(db_path: Path, value: str) -> dict[str, str] | None:
    if not db_path.exists():
        return None
    cleaned = _normalize_channel_input(value)
    with _connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT channel_id, handle, title
            FROM channels
            WHERE channel_id = ?
               OR handle = ?
               OR lower(handle) = lower(?)
               OR lower(title) = lower(?)
            LIMIT 1
            """,
            (cleaned, cleaned, cleaned, cleaned),
        ).fetchone()
    return _channel_dict(row) if row else None


def _comment_volume(db_path: Path, channel_id: str) -> list[dict[str, object]]:
    with _connect(db_path) as conn:
        rows = conn.execute(
            """
            SELECT v.video_id, v.title, v.published_at, COUNT(c.comment_id) AS comments
            FROM videos v
            LEFT JOIN comments c ON c.video_id = v.video_id
            WHERE v.channel_id = ?
            GROUP BY v.video_id
            ORDER BY v.published_at DESC
            LIMIT 30
            """,
            (channel_id,),
        ).fetchall()
    return [
        {
            "video_id": row["video_id"],
            "title": row["title"] or "Untitled video",
            "published_at": row["published_at"],
            "comments": int(row["comments"]),
        }
        for row in rows
    ]


def _latest_report_json(reports_dir: Path, channel: dict[str, str]) -> Path | None:
    if not reports_dir.exists():
        return None
    slugs = {_slug(channel.get("handle") or ""), _slug(channel.get("title") or ""), _slug(channel.get("channel_id") or "")}
    candidates = [
        path
        for path in reports_dir.glob("*_audience_report.json")
        if any(path.name.startswith(f"{slug}_") for slug in slugs if slug)
    ]
    return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None


def _channel_dict(row: sqlite3.Row) -> dict[str, str]:
    return {
        "channel_id": row["channel_id"],
        "handle": row["handle"] or row["channel_id"],
        "title": row["title"] or row["channel_id"],
        "slug": _slug(row["handle"] or row["title"] or row["channel_id"]),
    }


def _normalize_channel_input(value: str) -> str:
    value = value.strip()
    if value.startswith("http"):
        parts = [part for part in value.rstrip("/").split("/") if part]
        value = parts[-1] if parts else value
    return value.lstrip("@")


def _slug(value: str) -> str:
    value = value.strip().lower().lstrip("@")
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_")


def _dashboard_html(channels: list[dict[str, str]]) -> str:
    initial_channel = channels[0]["handle"] if channels else ""
    channel_options = "".join(
        f"<option value='{escape(channel['handle'])}'>{escape(channel['title'])} (@{escape(channel['handle'])})</option>"
        for channel in channels
    )
    return f"""<!doctype html>
<html>
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>yt-audience-report dashboard</title>
  <style>{_dashboard_css()}</style>
</head>
<body data-initial-channel="{escape(initial_channel)}">
  <header class="hero">
    <div class="hero-copy">
      <p class="eyebrow">Psychology Niche Analysis Suite</p>
      <h1>Audience Intelligence Dashboard</h1>
      <p>Evidence-backed audience signals from YouTube comments, designed for mental health creators.</p>
      <div class="controls">
        <label for="channelSelect">Channel</label>
        <select id="channelSelect">{channel_options}</select>
      </div>
    </div>
    <div class="hero-visual"><img src="/static/research_mark.png" alt=""></div>
  </header>

  <main>
    <section id="emptyState" class="empty" hidden></section>
    <section id="metrics" class="metric-grid"></section>
    <section class="dashboard-grid">
      <article class="panel wide"><div class="section-head"><p>Audience</p><h2>Segment breakdown</h2></div><div id="segments" class="card-grid"></div></article>
      <article class="panel"><div class="section-head"><p>Emotional Temperature</p><h2>Emotional states</h2></div><div id="emotions" class="stack-list"></div></article>
      <article class="panel"><div class="section-head"><p>Volume</p><h2>Comment-rich videos</h2></div><div id="videoVolume" class="bar-list"></div></article>
      <article class="panel wide"><div class="section-head"><p>Needs</p><h2>Top unmet needs</h2></div><div id="needs" class="rank-list"></div></article>
      <article class="panel wide"><div class="section-head"><p>Strategy</p><h2>Evidence-grounded video ideas</h2></div><div id="ideas" class="idea-grid"></div></article>
      <article class="panel"><div class="section-head"><p>Stories</p><h2>High-signal viewers</h2></div><div id="stories" class="story-list"></div></article>
      <article class="panel"><div class="section-head"><p>Inbox</p><h2>Direct requests</h2></div><div id="requests" class="table-wrap"></div></article>
      <article class="panel wide"><div class="section-head"><p>Blind Spots</p><h2>Content gaps to address</h2></div><div id="blindSpots" class="card-grid"></div></article>
    </section>
  </main>
  <script>{_dashboard_js()}</script>
</body>
</html>"""


def _dashboard_css() -> str:
    return f"""
    :root {{
{palette_css_vars()}
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--cream); color: var(--ink); font-family: Arial, Helvetica, sans-serif; }}
    .hero {{ display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(280px, .85fr); gap: 32px; padding: 44px 56px 32px; border-top: 10px solid var(--deep-teal); background: linear-gradient(135deg, var(--soft-panel), var(--cream)); }}
    .eyebrow, .section-head p, label {{ color: var(--muted); font-size: 11px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }}
    h1 {{ font-size: clamp(36px, 5vw, 64px); line-height: 1; max-width: 780px; margin: 20px 0 16px; }}
    .hero p:not(.eyebrow) {{ color: var(--muted); font-size: 18px; line-height: 1.55; max-width: 700px; }}
    .controls {{ align-items: center; display: flex; gap: 14px; margin-top: 34px; }}
    select {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; color: var(--ink); min-width: 310px; padding: 12px 14px; }}
    .hero-visual {{ background: var(--deep-teal); border-radius: 8px; min-height: 260px; padding: 18px; box-shadow: 0 18px 36px rgba(49,82,76,.14); }}
    .hero-visual img {{ border-radius: 6px; display: block; height: 100%; object-fit: cover; width: 100%; }}
    main {{ padding: 28px 56px 56px; }}
    .metric-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin-bottom: 20px; }}
    .metric, .panel, .signal-card, .idea-card, .story-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; box-shadow: 0 8px 22px rgba(49,82,76,.06); }}
    .metric {{ padding: 20px; }}
    .metric span {{ color: var(--muted); display: block; font-size: 11px; font-weight: 700; letter-spacing: .07em; text-transform: uppercase; }}
    .metric strong {{ display: block; font-size: 30px; margin-top: 10px; }}
    .dashboard-grid {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(320px, .72fr); gap: 18px; }}
    .panel {{ padding: 22px; min-width: 0; }}
    .wide {{ grid-column: span 1; }}
    .section-head {{ align-items: start; border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; gap: 18px; margin-bottom: 18px; padding-bottom: 14px; }}
    .section-head h2 {{ font-size: 22px; margin: 0; }}
    .card-grid {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; }}
    .signal-card {{ padding: 16px; }}
    .signal-card h3, .idea-card h3, .story-card h3 {{ font-size: 17px; margin: 10px 0 8px; }}
    .signal-card p, .story-card p, .idea-card p {{ color: var(--muted); line-height: 1.45; margin: 0; }}
    .severity {{ border-radius: 999px; color: var(--white); display: inline-block; font-size: 10px; font-weight: 700; letter-spacing: .05em; padding: 7px 10px; text-transform: uppercase; }}
    .severity-high {{ background: var(--high); }}
    .severity-medium {{ background: var(--medium); }}
    .severity-low {{ background: var(--low); }}
    .evidence {{ margin-top: 12px; }}
    code {{ background: var(--soft-panel); border-radius: 4px; color: var(--deep-teal); display: inline-block; font-size: 10px; margin: 2px 3px 2px 0; padding: 3px 5px; }}
    .stack-list, .bar-list, .rank-list, .story-list {{ display: grid; gap: 12px; }}
    .bar-row {{ display: grid; gap: 7px; }}
    .bar-row header {{ display: flex; justify-content: space-between; gap: 12px; font-size: 13px; }}
    .bar {{ background: var(--soft-panel); border-radius: 999px; height: 9px; overflow: hidden; }}
    .bar i {{ background: linear-gradient(90deg, var(--sage), var(--clay)); display: block; height: 100%; }}
    .rank-item {{ border-left: 5px solid var(--clay); padding: 13px 0 13px 14px; }}
    .idea-grid {{ display: grid; gap: 16px; }}
    .idea-card {{ border-left: 8px solid var(--sage); padding: 20px; }}
    .idea-card:nth-child(2) {{ border-left-color: var(--olive); }}
    .idea-card:nth-child(3) {{ border-left-color: var(--clay); }}
    .idea-card:nth-child(4) {{ border-left-color: var(--lavender); }}
    .idea-card:nth-child(5) {{ border-left-color: var(--blue-gray); }}
    .hook {{ color: var(--deep-teal) !important; font-size: 16px; font-weight: 700; margin-bottom: 12px !important; }}
    .need {{ background: var(--soft-panel); border-radius: 8px; margin: 12px 0; padding: 12px; }}
    .story-card {{ padding: 16px; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid var(--border); padding: 10px 8px; text-align: left; vertical-align: top; }}
    th {{ background: var(--soft-panel); color: var(--deep-teal); font-size: 11px; text-transform: uppercase; }}
    .empty {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; margin-bottom: 20px; padding: 24px; }}
    @media (max-width: 980px) {{
      .hero, .dashboard-grid, .metric-grid {{ grid-template-columns: 1fr; }}
      main, .hero {{ padding-left: 22px; padding-right: 22px; }}
      .card-grid {{ grid-template-columns: 1fr; }}
    }}
    """


def _dashboard_js() -> str:
    return """
    const select = document.getElementById('channelSelect');
    const initial = document.body.dataset.initialChannel;
    const esc = value => String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
    const chips = evidence => `<div class="evidence">${(evidence || []).slice(0, 4).map(item => `<code>${esc(item.comment_id)}</code>`).join('')}</div>`;
    const severity = value => `<span class="severity severity-${esc(value || 'low')}">${esc(value || 'low')}</span>`;
    const evidenceCount = item => item.evidence_count || (item.evidence ? item.evidence.length : 0);
    async function loadDashboard(channel) {
      if (!channel) {
        showEmpty('No channels found in SQLite yet.');
        return;
      }
      const [reportRes, volumeRes] = await Promise.all([
        fetch(`/api/report?channel=${encodeURIComponent(channel)}`),
        fetch(`/api/comment-volume?channel=${encodeURIComponent(channel)}`)
      ]);
      if (!reportRes.ok) {
        const data = await reportRes.json();
        showEmpty(data.message || 'Report JSON missing.');
        return;
      }
      document.getElementById('emptyState').hidden = true;
      const report = (await reportRes.json()).report;
      const volume = volumeRes.ok ? (await volumeRes.json()).videos : report.video_counts || [];
      renderMetrics(report);
      renderCards('segments', report.audience_segments || []);
      renderBars('emotions', report.emotional_temperature || []);
      renderNeeds(report.unmet_needs || []);
      renderCards('blindSpots', report.blind_spots || []);
      renderIdeas(report.video_ideas || []);
      renderStories(report.high_signal_stories || []);
      renderRequests(report.direct_requests || []);
      renderVideoVolume(volume || []);
    }
    function showEmpty(message) {
      const empty = document.getElementById('emptyState');
      empty.hidden = false;
      empty.innerHTML = `<h2>Dashboard data not ready</h2><p>${esc(message)}</p>`;
      document.getElementById('metrics').innerHTML = '';
    }
    function renderMetrics(report) {
      const metrics = report.metrics || {};
      document.getElementById('metrics').innerHTML = [
        ['Comments analyzed', metrics.comments_analyzed],
        ['Urgent signals', metrics.urgent_signals],
        ['Videos fetched', metrics.videos_fetched],
        ['Video ideas', (report.video_ideas || []).length],
      ].map(([label, value]) => `<div class="metric"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join('');
    }
    function renderCards(id, items) {
      document.getElementById(id).innerHTML = items.map(item => `<article class="signal-card">${severity(item.severity)}<h3>${esc(item.title)}</h3><p>${esc(item.description)}</p>${chips(item.evidence)}</article>`).join('');
    }
    function renderBars(id, items) {
      const max = Math.max(1, ...items.map(evidenceCount));
      document.getElementById(id).innerHTML = items.map(item => `<div class="bar-row"><header><strong>${esc(item.title)}</strong><span>${evidenceCount(item)}</span></header><div class="bar"><i style="width:${Math.max(6, evidenceCount(item) / max * 100)}%"></i></div></div>`).join('');
    }
    function renderNeeds(items) {
      document.getElementById('needs').innerHTML = items.map((item, index) => `<div class="rank-item">${severity(item.severity)}<h3>${index + 1}. ${esc(item.title)}</h3><p>${esc(item.description)}</p>${chips(item.evidence)}</div>`).join('');
    }
    function renderIdeas(items) {
      document.getElementById('ideas').innerHTML = items.map(item => `<article class="idea-card">${severity(item.severity)}<h3>${esc(item.title)}</h3><p class="hook">${esc(item.hook)}</p><div class="need"><strong>Audience need</strong><p>${esc(item.audience_need)}</p></div>${chips(item.evidence)}</article>`).join('');
    }
    function renderStories(items) {
      document.getElementById('stories').innerHTML = items.map(item => `<article class="story-card">${severity(item.severity)}<h3>${esc(item.title)}</h3><p>${esc(item.description)}</p>${chips(item.evidence)}</article>`).join('');
    }
    function renderRequests(items) {
      const rows = items.flatMap(item => (item.evidence || []).map(ev => `<tr><td><code>${esc(ev.comment_id)}</code></td><td>${esc(ev.video_title)}</td><td>${esc(ev.text).slice(0, 180)}</td></tr>`));
      document.getElementById('requests').innerHTML = `<table><thead><tr><th>Comment</th><th>Video</th><th>Request</th></tr></thead><tbody>${rows.join('')}</tbody></table>`;
    }
    function renderVideoVolume(items) {
      const max = Math.max(1, ...items.map(item => item.comments || 0));
      document.getElementById('videoVolume').innerHTML = items.slice(0, 12).map(item => `<div class="bar-row"><header><strong>${esc(item.title).slice(0, 58)}</strong><span>${item.comments || 0}</span></header><div class="bar"><i style="width:${Math.max(4, (item.comments || 0) / max * 100)}%"></i></div></div>`).join('');
    }
    select?.addEventListener('change', event => loadDashboard(event.target.value));
    loadDashboard(select?.value || initial);
    """


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local yt-audience-report dashboard.")
    parser.add_argument("--db-path", default="data/yt-audience-report.sqlite3")
    parser.add_argument("--reports-dir", default="reports")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(create_app(args.db_path, args.reports_dir), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
