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
    <div class="brand-lockup">
      <div class="brand-icon"><img src="/static/research_mark.png" alt=""></div>
      <div>
        <p class="eyebrow">Mental Health Audience Research</p>
        <h1>Creator Care Map</h1>
        <p>A practical read on what viewers are carrying, where they feel stuck, and what content could help without guessing.</p>
      </div>
    </div>
    <div class="hero-side">
      <div class="controls">
        <label for="channelSelect">Channel</label>
        <select id="channelSelect">{channel_options}</select>
      </div>
      <div id="statusMetrics" class="status-metrics"></div>
    </div>
  </header>

  <main>
    <nav class="tabs" aria-label="Dashboard sections">
      <a href="#overview">Care Map</a>
      <a href="#audience">Who Needs Help</a>
      <a href="#needs">Unmet Needs</a>
      <a href="#ideas">Next Videos</a>
      <a href="#evidence">Evidence</a>
    </nav>
    <section id="emptyState" class="empty" hidden></section>
    <section id="overview" class="metric-grid"></section>
    <section class="analysis-row">
      <article class="panel chart-panel">
        <div class="section-head"><p>Audience Distress Map</p><h2>What viewers are carrying</h2></div>
        <div id="signalMix" class="category-chart"></div>
      </article>
      <article class="panel what-panel">
        <div class="section-head"><p>Psychologist's Read</p><h2>What deserves care</h2></div>
        <div id="whatThisMeans" class="meaning-copy"></div>
      </article>
    </section>
    <section class="dashboard-grid">
      <article id="audience" class="panel wide"><div class="section-head"><p>Who Needs Help</p><h2>Viewer struggle segments</h2></div><div id="segments" class="card-grid"></div></article>
      <article class="panel"><div class="section-head"><p>Emotional Temperature</p><h2>How intense it feels</h2></div><div id="emotions" class="stack-list"></div></article>
      <article class="panel"><div class="section-head"><p>Where Signals Appear</p><h2>Comment-rich videos</h2></div><div id="videoVolume" class="bar-list"></div></article>
      <article id="needs" class="panel wide"><div class="section-head"><p>Unanswered Pain Points</p><h2>Top unmet needs</h2></div><div id="needsList" class="rank-list"></div></article>
      <article class="panel"><div class="section-head"><p>Care Priority</p><h2>Blind spots to handle gently</h2></div><div id="opportunityMap" class="stack-list"></div></article>
      <article id="ideas" class="panel wide"><div class="section-head"><p>Helpful Next Content</p><h2>Evidence-grounded video ideas</h2></div><div id="ideasList" class="idea-grid"></div></article>
      <article class="panel"><div class="section-head"><p>Lived Experience</p><h2>High-signal viewer stories</h2></div><div id="stories" class="story-list"></div></article>
      <article class="panel"><div class="section-head"><p>Explicit Asks</p><h2>Direct requests inbox</h2></div><div id="requests" class="table-wrap"></div></article>
      <article id="evidence" class="panel wide"><div class="section-head"><p>Missing Support</p><h2>Content blind spots</h2></div><div id="blindSpots" class="card-grid"></div></article>
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
    html {{ scroll-behavior: smooth; }}
    body {{ margin: 0; background: var(--cream); color: var(--ink); font-family: Arial, Helvetica, sans-serif; }}
    .hero {{ align-items: center; display: grid; grid-template-columns: minmax(0, 1fr) minmax(390px, 430px); gap: 32px; margin: 24px 56px 0; padding: 24px; border: 1px solid var(--border); border-top: 10px solid var(--deep-teal); border-radius: 8px; background: var(--deep-teal); box-shadow: 0 20px 44px rgba(49,82,76,.16); }}
    .brand-lockup {{ align-items: center; display: flex; gap: 22px; min-width: 0; }}
    .brand-icon {{ background: var(--card); border: 1px solid var(--sage); border-radius: 8px; flex: 0 0 78px; height: 78px; padding: 6px; }}
    .brand-icon img {{ border-radius: 6px; display: block; height: 100%; object-fit: cover; width: 100%; }}
    .eyebrow, .section-head p, label {{ color: var(--muted); font-size: 11px; font-weight: 700; letter-spacing: .08em; text-transform: uppercase; }}
    .hero .eyebrow {{ color: var(--sage); margin: 0 0 4px; }}
    h1 {{ color: var(--card); font-size: clamp(36px, 5vw, 54px); line-height: 1; margin: 0 0 8px; }}
    .hero p:not(.eyebrow) {{ color: var(--border); font-size: 17px; line-height: 1.45; margin: 0; max-width: 760px; }}
    .hero-side {{ display: grid; gap: 14px; min-width: 0; }}
    .controls {{ align-items: center; display: flex; gap: 14px; justify-content: flex-end; }}
    .controls label {{ color: var(--border); }}
    select {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; color: var(--ink); min-width: 0; max-width: 100%; padding: 12px 14px; width: 100%; }}
    .status-metrics {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px; }}
    .status-card {{ background: rgba(255,253,248,.08); border: 1px solid rgba(217,222,214,.25); border-radius: 8px; color: var(--card); padding: 13px; }}
    .status-card span {{ color: var(--border); display: block; font-size: 11px; font-weight: 700; text-transform: uppercase; }}
    .status-card strong {{ color: var(--card); display: block; font-size: 18px; margin-top: 5px; white-space: nowrap; }}
    main {{ padding: 24px 56px 56px; }}
    .tabs {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; display: flex; gap: 8px; margin-bottom: 18px; padding: 8px; }}
    .tabs a {{ border-radius: 7px; color: var(--ink); font-weight: 700; padding: 12px 18px; text-decoration: none; }}
    .tabs a:first-child {{ background: var(--sage); color: var(--white); }}
    .metric-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 16px; margin-bottom: 20px; }}
    .metric, .panel, .signal-card, .idea-card, .story-card {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; box-shadow: 0 8px 22px rgba(49,82,76,.06); }}
    .metric {{ min-height: 150px; padding: 20px; position: relative; overflow: hidden; }}
    .metric::after {{ content: ""; position: absolute; right: 18px; top: 18px; width: 38px; height: 38px; border-radius: 8px; background: var(--soft-panel); }}
    .metric:nth-child(1)::after {{ background: var(--sage); }}
    .metric:nth-child(2)::after {{ background: var(--medium); }}
    .metric:nth-child(3)::after {{ background: var(--high); }}
    .metric:nth-child(4)::after {{ background: var(--clay); }}
    .metric span {{ color: var(--muted); display: block; font-size: 11px; font-weight: 700; letter-spacing: .07em; text-transform: uppercase; }}
    .metric strong {{ display: block; font-size: 40px; margin-top: 18px; }}
    .metric p {{ color: var(--muted); font-weight: 700; line-height: 1.4; margin: 16px 0 0; max-width: 86%; }}
    .analysis-row {{ display: grid; grid-template-columns: minmax(0, 1.08fr) minmax(360px, .72fr); gap: 18px; margin-bottom: 18px; }}
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
    .category-chart {{ display: grid; gap: 13px; padding-top: 6px; }}
    .category-row {{ align-items: center; display: grid; grid-template-columns: 190px 1fr 58px; gap: 14px; }}
    .category-row strong {{ font-size: 14px; line-height: 1.1; text-align: right; }}
    .category-row .bar {{ height: 18px; }}
    .category-row:nth-child(2n) .bar i {{ background: linear-gradient(90deg, var(--lavender), var(--blue-gray)); }}
    .category-row:nth-child(3n) .bar i {{ background: linear-gradient(90deg, var(--olive), var(--clay)); }}
    .meaning-copy {{ color: var(--muted); display: grid; gap: 18px; font-size: 17px; font-weight: 700; line-height: 1.55; }}
    .meaning-copy b {{ color: var(--ink); }}
    .action-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top: 8px; }}
    .action-button {{ background: var(--sage); border-radius: 7px; color: var(--white); display: block; font-size: 15px; font-weight: 700; padding: 14px; text-align: center; }}
    .action-button:nth-child(2) {{ background: var(--clay); }}
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
      .hero, .dashboard-grid, .metric-grid, .analysis-row {{ grid-template-columns: 1fr; }}
      main {{ padding-left: 22px; padding-right: 22px; }}
      .hero {{ margin-left: 22px; margin-right: 22px; }}
      .brand-lockup {{ align-items: flex-start; }}
      .controls, .tabs {{ overflow-x: auto; justify-content: flex-start; }}
      .card-grid {{ grid-template-columns: 1fr; }}
      .category-row {{ grid-template-columns: 1fr; }}
      .category-row strong {{ text-align: left; }}
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
      renderStatus(report);
      renderMetrics(report);
      renderSignalMix(report);
      renderMeaning(report);
      renderCards('segments', report.audience_segments || []);
      renderBars('emotions', report.emotional_temperature || []);
      renderNeeds(report.unmet_needs || []);
      renderCards('blindSpots', report.blind_spots || []);
      renderOpportunityMap(report.blind_spots || []);
      renderIdeas(report.video_ideas || []);
      renderStories(report.high_signal_stories || []);
      renderRequests(report.direct_requests || []);
      renderVideoVolume(volume || []);
    }
    function showEmpty(message) {
      const empty = document.getElementById('emptyState');
      empty.hidden = false;
      empty.innerHTML = `<h2>Dashboard data not ready</h2><p>${esc(message)}</p>`;
      document.getElementById('overview').innerHTML = '';
    }
    function countEvidence(items) {
      return (items || []).reduce((total, item) => total + evidenceCount(item), 0);
    }
    function highCount(items) {
      return (items || []).filter(item => item.severity === 'high').length;
    }
    function topByEvidence(items) {
      return [...(items || [])].sort((a, b) => evidenceCount(b) - evidenceCount(a))[0];
    }
    function renderStatus(report) {
      const metrics = report.metrics || {};
      document.getElementById('statusMetrics').innerHTML = [
        ['Evidence comments', (report.evidence_appendix || []).length],
        ['Trust + return', countEvidence(report.trust_signals || []) + countEvidence(report.loyalty_signals || [])],
        ['Sample window', `${metrics.sample_start || 'n/a'} → ${metrics.sample_end || 'n/a'}`],
      ].map(([label, value]) => `<div class="status-card"><span>${esc(label)}</span><strong>${esc(value)}</strong></div>`).join('');
    }
    function renderMetrics(report) {
      const metrics = report.metrics || {};
      const topNeed = topByEvidence(report.unmet_needs || []);
      const topSegment = topByEvidence(report.audience_segments || []);
      const trustAndLoyalty = countEvidence(report.trust_signals || []) + countEvidence(report.loyalty_signals || []);
      document.getElementById('overview').innerHTML = [
        ['Audience sample', metrics.comments_analyzed, `${metrics.videos_fetched || 0} recent videos represented. This is the evidence base, not a vanity metric.`],
        ['Care alerts', metrics.urgent_signals, `Comments with crisis-adjacent, shame-loaded, or low-support language that need gentle framing.`],
        ['Main unmet need', topNeed ? topNeed.title : 'n/a', topNeed ? `${evidenceCount(topNeed)} comments point to something viewers still need explained.` : 'No repeated need found yet.'],
        ['Trust and return', trustAndLoyalty, `Signals that viewers may be using this creator as a continuing support resource.`],
      ].map(([label, value, note]) => `<div class="metric"><span>${esc(label)}</span><strong>${esc(value)}</strong><p>${esc(note)}</p></div>`).join('');
    }
    function renderSignalMix(report) {
      const rows = [
        ...(report.audience_segments || []),
        ...(report.unmet_needs || []),
        ...(report.stigma_signals || []),
        ...(report.blind_spots || []),
        ...(report.trust_signals || []),
        ...(report.loyalty_signals || []),
      ].sort((a, b) => evidenceCount(b) - evidenceCount(a)).slice(0, 7);
      const max = Math.max(1, ...rows.map(evidenceCount));
      document.getElementById('signalMix').innerHTML = rows.map(item => `<div class="category-row"><strong>${esc(item.title)}</strong><div class="bar"><i style="width:${Math.max(6, evidenceCount(item) / max * 100)}%"></i></div><span>${evidenceCount(item)} signals</span></div>`).join('');
    }
    function renderMeaning(report) {
      const topNeed = topByEvidence(report.unmet_needs || {});
      const topBlindSpot = topByEvidence(report.blind_spots || {});
      const trust = topByEvidence(report.trust_signals || {});
      const stigma = topByEvidence(report.stigma_signals || {});
      const loyalty = topByEvidence(report.loyalty_signals || {});
      document.getElementById('whatThisMeans').innerHTML = `
        <p>${topNeed ? `The audience is showing a repeated need for <b>${esc(topNeed.title)}</b>. As a creator, I would treat this as a request for containment and practical steps, not just another topic idea.` : 'The current sample does not show a dominant unmet need yet.'}</p>
        <p>${stigma ? `<b>${esc(stigma.title)}</b> is the area to handle with the most care. The wording should reduce shame and make viewers feel less alone before offering advice.` : 'No high-confidence stigma pattern is currently visible.'}</p>
        <p>${topBlindSpot ? `<b>${esc(topBlindSpot.title)}</b> is the clearest blind spot. The audience is already revealing this gap in comments, which normal analytics would miss.` : 'No major content blind spot is currently above the evidence threshold.'}</p>
        <p>${trust ? `Trust appears connected to <b>${esc(trust.description).toLowerCase()}</b>` : ''} ${loyalty ? `Return signals suggest some viewers are using the channel as a repeat support tool, so reusable frameworks and reminders are likely valuable.` : ''}</p>
        <div class="action-row"><span class="action-button">Create a safe explainer</span><span class="action-button">Turn comments into care prompts</span></div>
      `;
    }
    function renderCards(id, items) {
      document.getElementById(id).innerHTML = items.map(item => `<article class="signal-card">${severity(item.severity)}<h3>${esc(item.title)}</h3><p>${esc(item.description)}</p>${chips(item.evidence)}</article>`).join('');
    }
    function renderBars(id, items) {
      const max = Math.max(1, ...items.map(evidenceCount));
      document.getElementById(id).innerHTML = items.map(item => `<div class="bar-row"><header><strong>${esc(item.title)}</strong><span>${evidenceCount(item)}</span></header><div class="bar"><i style="width:${Math.max(6, evidenceCount(item) / max * 100)}%"></i></div></div>`).join('');
    }
    function renderNeeds(items) {
      document.getElementById('needsList').innerHTML = items.map((item, index) => `<div class="rank-item">${severity(item.severity)}<h3>${index + 1}. ${esc(item.title)}</h3><p>${esc(item.description)}</p>${chips(item.evidence)}</div>`).join('');
    }
    function renderOpportunityMap(items) {
      const max = Math.max(1, ...items.map(evidenceCount));
      document.getElementById('opportunityMap').innerHTML = items.map(item => `<div class="bar-row"><header><strong>${esc(item.title)}</strong>${severity(item.severity)}</header><div class="bar"><i style="width:${Math.max(8, evidenceCount(item) / max * 100)}%"></i></div><small>${evidenceCount(item)} evidence items</small></div>`).join('');
    }
    function renderIdeas(items) {
      document.getElementById('ideasList').innerHTML = items.map(item => `<article class="idea-card">${severity(item.severity)}<h3>${esc(item.title)}</h3><p class="hook">${esc(item.hook)}</p><div class="need"><strong>Audience need</strong><p>${esc(item.audience_need)}</p></div>${chips(item.evidence)}</article>`).join('');
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
