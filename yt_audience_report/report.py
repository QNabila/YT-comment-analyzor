from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from html import escape
import json
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Iterable
from xml.sax.saxutils import escape as xml_escape
from zipfile import ZIP_DEFLATED, ZipFile

from yt_audience_report.palette import MOCK_PALETTE, palette_css_vars


@dataclass(frozen=True)
class CommentEvidence:
    comment_id: str
    video_title: str
    published_at: str | None
    text: str
    is_reply: bool
    tags: tuple[str, ...]


@dataclass(frozen=True)
class Signal:
    title: str
    description: str
    severity: str
    evidence: tuple[CommentEvidence, ...]


@dataclass(frozen=True)
class VideoIdea:
    title: str
    hook: str
    audience_need: str
    severity: str
    evidence: tuple[CommentEvidence, ...]


@dataclass(frozen=True)
class ReportMetrics:
    total_comments_stored: int
    comments_analyzed: int
    videos_fetched: int
    replies_stored: int
    urgent_signals: int
    sample_start: str
    sample_end: str


@dataclass(frozen=True)
class AudienceReport:
    channel_id: str
    channel_title: str
    channel_handle: str
    channel_slug: str
    generated_date: str
    metrics: ReportMetrics
    core_profile: tuple[Signal, ...]
    audience_segments: tuple[Signal, ...]
    emotional_temperature: tuple[Signal, ...]
    trust_signals: tuple[Signal, ...]
    unmet_needs: tuple[Signal, ...]
    direct_requests: tuple[Signal, ...]
    stigma_signals: tuple[Signal, ...]
    high_signal_stories: tuple[Signal, ...]
    loyalty_signals: tuple[Signal, ...]
    blind_spots: tuple[Signal, ...]
    video_ideas: tuple[VideoIdea, ...]
    evidence_appendix: tuple[CommentEvidence, ...]
    video_counts: tuple[tuple[str, int], ...]


SIGNAL_RULES: dict[str, tuple[str, tuple[str, ...]]] = {
    "anxiety and fear": ("Anxiety/fear viewers", ("anxiety", "fear", "panic", "worry", "spiral", "overwhelming")),
    "emotional regulation": ("Regulation seekers", ("regulate", "coregulate", "co-regulate", "nervous system", "reset", "ground")),
    "neurodivergence": ("Neurodivergent or trauma-aware viewers", ("neurodivergent", "neuro typical", "neurotypical", "adhd", "autistic", "trauma")),
    "fatigue and low capacity": ("Low-energy/freeze viewers", ("fatigue", "tired", "freeze", "no desire", "too hard", "wired", "rest")),
    "sleep and safety": ("Sleep and safety viewers", ("sleep", "safe", "safety")),
    "self-worth and shame": ("Self-worth and shame viewers", ("stupid", "incapable", "not enough", "shame", "mistake", "dark thoughts")),
    "limited support": ("Limited-support viewers", ("no support", "support system", "family", "friends", "no one", "alone")),
}

TRUST_TERMS = ("clear", "clarity", "concise", "simple", "accessible", "approachable", "visual", "post it", "post-it", "no fluff", "favorite", "hope", "unlike", "average joe", "direct")
LOYALTY_TERMS = ("your videos", "your content", "helped me so much", "favorite", "fan", "keep going", "reminder every day", "screenshot", "pdf", "poster", "wall", "save")
REQUEST_TERMS = ("can you", "could you", "please", "pls", "advice", "tips", "examples", "explain", "what do you mean", "what does", "how do you", "pdf", "poster")
STIGMA_TERMS = ("stupid", "incapable", "dark thoughts", "no support", "never feel safe", "not enough", "ashamed", "shame", "no desire", "family", "friends")
URGENT_TERMS = ("dark thoughts", "no support", "panic", "never feel safe", "not safe", "crisis", "no desire", "overwhelming")


def build_report(conn: sqlite3.Connection, channel_id: str | None, max_comments: int = 200) -> AudienceReport:
    conn.row_factory = sqlite3.Row
    channel = _get_channel(conn, channel_id)
    comments = _get_recent_comments(conn, channel["channel_id"], max_comments)
    video_counts = _get_video_counts(conn, channel["channel_id"])
    tagged = tuple(_tag_comment(row) for row in comments)

    audience_segments = tuple(_signal_from_tag(tagged, key, label, "medium") for key, (label, _) in SIGNAL_RULES.items())
    audience_segments = tuple(signal for signal in audience_segments if signal.evidence)

    trust = _keyword_signal(tagged, "Why viewers trust this creator", "Viewers describe clear, concise, practical, visual, or credible delivery.", TRUST_TERMS, "medium")
    loyalty = _keyword_signal(tagged, "Loyalty and return signals", "Viewers save, revisit, request reusable assets, or describe the channel as an ongoing resource.", LOYALTY_TERMS, "medium")
    direct = _keyword_signal(tagged, "Direct content requests", "Viewers explicitly ask for explanations, examples, tips, PDFs, or follow-up topics.", REQUEST_TERMS, "medium")
    stigma = _keyword_signal(tagged, "Stigma and shame signals", "Viewers reveal shame-loaded, isolating, or socially risky struggles.", STIGMA_TERMS, "high")

    unmet_needs = _build_unmet_needs(tagged)
    blind_spots = _build_blind_spots(tagged)
    high_signal = _build_high_signal_stories(tagged)
    video_ideas = _build_video_ideas(tagged)
    urgent_count = _count_urgent_comments(tagged)

    metrics = ReportMetrics(
        total_comments_stored=_count(conn, "comments"),
        comments_analyzed=len(tagged),
        videos_fetched=_count_channel_videos(conn, channel["channel_id"]),
        replies_stored=_count_replies(conn, channel["channel_id"]),
        urgent_signals=urgent_count,
        sample_start=_min_date(tagged),
        sample_end=_max_date(tagged),
    )

    core_profile = _build_core_profile(tagged, trust.evidence if trust else ())
    emotional = _build_emotional_temperature(tagged)
    appendix = _collect_appendix(
        core_profile,
        audience_segments,
        emotional,
        (trust,) if trust else (),
        unmet_needs,
        direct.evidence and (direct,) or (),
        (stigma,) if stigma else (),
        high_signal,
        (loyalty,) if loyalty else (),
        blind_spots,
        video_ideas,
    )

    return AudienceReport(
        channel_id=channel["channel_id"],
        channel_title=channel["title"] or channel["channel_id"],
        channel_handle=channel["handle"] or channel["channel_id"],
        channel_slug=_slug(channel["handle"] or channel["title"] or channel["channel_id"]),
        generated_date=datetime.now().strftime("%Y-%m-%d"),
        metrics=metrics,
        core_profile=core_profile,
        audience_segments=audience_segments,
        emotional_temperature=emotional,
        trust_signals=(trust,) if trust else (),
        unmet_needs=unmet_needs,
        direct_requests=(direct,) if direct else (),
        stigma_signals=(stigma,) if stigma else (),
        high_signal_stories=high_signal,
        loyalty_signals=(loyalty,) if loyalty else (),
        blind_spots=blind_spots,
        video_ideas=video_ideas,
        evidence_appendix=appendix,
        video_counts=video_counts,
    )


def render_report_pdf(report: AudienceReport, output_path: str | Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    html = render_report_html(report)
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 1600})
            page.set_content(html, wait_until="load")
            page.pdf(
                path=str(output_path),
                format="A4",
                print_background=True,
                margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
            )
            browser.close()
    except Exception:
        pdf = _SimplePdf()
        _draw_pdf_report(pdf, report)
        pdf.write(output_path)


def render_report_xlsx(report: AudienceReport, output_path: str | Path) -> None:
    workbook = _SimpleXlsx()
    workbook.add_sheet(
        "Cover Summary",
        [
            ["Audience Insight Report", report.channel_title],
            ["Generated date", report.generated_date],
            ["Comments analyzed", report.metrics.comments_analyzed],
            ["Urgent signals", report.metrics.urgent_signals],
            ["Video ideas", len(report.video_ideas)],
            ["Sample range", f"{report.metrics.sample_start} to {report.metrics.sample_end}"],
            [],
            ["Recent video", "Comments stored"],
            *[[title, count] for title, count in report.video_counts],
        ],
        widths=[44, 18],
    )
    workbook.add_sheet(
        "Audience Segments",
        _signals_rows(
            ("Core Audience Profile", report.core_profile),
            ("Who Is Actually Watching", report.audience_segments),
            ("Emotional Temperature", report.emotional_temperature),
            ("Why They Trust This Creator", report.trust_signals),
        ),
        widths=[28, 18, 34, 70, 58],
    )
    workbook.add_sheet(
        "Audience Voice",
        _signals_rows(
            ("Top Unmet Needs", report.unmet_needs),
            ("Direct Requests Inbox", report.direct_requests),
            ("Stigma And Shame Signals", report.stigma_signals),
        ),
        widths=[28, 18, 34, 70, 58],
    )
    workbook.add_sheet(
        "Patterns",
        _signals_rows(
            ("High-Signal Viewer Stories", report.high_signal_stories),
            ("Loyalty and Return Signals", report.loyalty_signals),
            ("Content Blind Spots", report.blind_spots),
        ),
        widths=[28, 18, 34, 70, 58],
    )
    workbook.add_sheet(
        "Video Ideas",
        [
            ["Title", "Severity", "Hook", "Audience need", "Evidence comment IDs"],
            *[
                [
                    idea.title,
                    idea.severity.upper(),
                    idea.hook,
                    idea.audience_need,
                    ", ".join(item.comment_id for item in idea.evidence),
                ]
                for idea in report.video_ideas
            ],
        ],
        widths=[42, 12, 72, 48, 70],
    )
    workbook.add_sheet(
        "Evidence Appendix",
        [
            ["Comment ID", "Tags", "Video", "Published", "Evidence note"],
            *[
                [
                    item.comment_id,
                    ", ".join(item.tags),
                    item.video_title,
                    item.published_at or "",
                    item.text,
                ]
                for item in report.evidence_appendix
            ],
        ],
        widths=[38, 34, 54, 22, 90],
    )
    workbook.write(output_path)


def render_report_json(report: AudienceReport, output_path: str | Path) -> None:
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report_to_dict(report), ensure_ascii=False, indent=2), encoding="utf-8")


def report_to_dict(report: AudienceReport) -> dict[str, object]:
    return {
        "channel": {
            "id": report.channel_id,
            "title": report.channel_title,
            "handle": report.channel_handle,
            "slug": report.channel_slug,
        },
        "generated_date": report.generated_date,
        "metrics": {
            "total_comments_stored": report.metrics.total_comments_stored,
            "comments_analyzed": report.metrics.comments_analyzed,
            "videos_fetched": report.metrics.videos_fetched,
            "replies_stored": report.metrics.replies_stored,
            "urgent_signals": report.metrics.urgent_signals,
            "sample_start": report.metrics.sample_start,
            "sample_end": report.metrics.sample_end,
        },
        "core_profile": [_signal_to_dict(signal) for signal in report.core_profile],
        "audience_segments": [_signal_to_dict(signal) for signal in report.audience_segments],
        "emotional_temperature": [_signal_to_dict(signal) for signal in report.emotional_temperature],
        "trust_signals": [_signal_to_dict(signal) for signal in report.trust_signals],
        "unmet_needs": [_signal_to_dict(signal) for signal in report.unmet_needs],
        "direct_requests": [_signal_to_dict(signal) for signal in report.direct_requests],
        "stigma_signals": [_signal_to_dict(signal) for signal in report.stigma_signals],
        "high_signal_stories": [_signal_to_dict(signal) for signal in report.high_signal_stories],
        "loyalty_signals": [_signal_to_dict(signal) for signal in report.loyalty_signals],
        "blind_spots": [_signal_to_dict(signal) for signal in report.blind_spots],
        "video_ideas": [_video_idea_to_dict(idea) for idea in report.video_ideas],
        "evidence_appendix": [_evidence_to_dict(item) for item in report.evidence_appendix],
        "video_counts": [{"title": title, "comments": count} for title, count in report.video_counts],
    }


def render_report_html(report: AudienceReport) -> str:
    return f"""<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>{escape(report.channel_title)} Audience Report</title>
<style>{_css()}</style>
</head>
<body>
{_cover_page_html(report)}
{_section("Who’s Watching: Segment Breakdown", _dataset_html(report) + _section_block("Core Audience Profile", _signals_html(report.core_profile, True, "profile-grid")) + _section_block("Who Is Actually Watching", _signals_html(report.audience_segments, True, "segment-grid")), "Audience mental health profiles & interests", page_number="02")}
{_section("Audience Voice: Asks & Questions", _section_block("Emotional Temperature", _signals_html(report.emotional_temperature, True, "segment-grid")) + _section_block("Why They Trust This Creator", _signals_html(report.trust_signals, False, "trust-grid")) + _section_block("Top Unmet Needs", _signals_html(report.unmet_needs, True, "segment-grid")) + _section_block("Direct Requests Inbox", _signals_html(report.direct_requests, True, "trust-grid")) + _section_block("Stigma And Shame Signals", _signals_html(report.stigma_signals, True, "trust-grid")), "Top community demands and emotional undercurrents", page_number="03")}
{_section("Patterns & Surprises", _theme_heatmap_html(report) + _section_block("High-Signal Viewer Stories", _signals_html(report.high_signal_stories, True, "story-grid")) + _section_block("Loyalty and Return Signals", _signals_html(report.loyalty_signals, False, "trust-grid")) + _section_block("Content Blind Spots", _signals_html(report.blind_spots, True, "segment-grid")), "Repeated patterns worth building around", page_number="04")}
{_section("Next Video Strategy", _video_ideas_html(report.video_ideas), "Evidence-grounded concepts", page_number="05", klass="strategy-page")}
{_section("Evidence Appendix", _appendix_html(report.evidence_appendix), "Compact traceability table", compact=True, page_number="06")}
</body>
</html>"""


def _get_channel(conn: sqlite3.Connection, channel_id: str | None) -> sqlite3.Row:
    if channel_id:
        row = conn.execute("SELECT * FROM channels WHERE channel_id = ?", (channel_id,)).fetchone()
        if row:
            return row
    row = conn.execute("SELECT * FROM channels ORDER BY last_fetched_at DESC LIMIT 1").fetchone()
    if not row:
        raise ValueError("No channel data found. Run the fetch step first.")
    return row


def _get_recent_comments(conn: sqlite3.Connection, channel_id: str, limit: int) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT c.*, v.title AS video_title
            FROM comments c
            JOIN videos v ON v.video_id = c.video_id
            WHERE v.channel_id = ?
            ORDER BY c.published_at DESC
            LIMIT ?
            """,
            (channel_id, limit),
        )
    )


def _get_video_counts(conn: sqlite3.Connection, channel_id: str) -> tuple[tuple[str, int], ...]:
    rows = conn.execute(
        """
        SELECT v.title, COUNT(c.comment_id) AS comments
        FROM videos v
        LEFT JOIN comments c ON c.video_id = v.video_id
        WHERE v.channel_id = ?
        GROUP BY v.video_id
        ORDER BY v.published_at DESC
        LIMIT 12
        """,
        (channel_id,),
    ).fetchall()
    return tuple((row["title"] or "Untitled video", int(row["comments"])) for row in rows)


def _tag_comment(row: sqlite3.Row) -> CommentEvidence:
    text = row["text"] or ""
    normalized = text.lower()
    tags: list[str] = []
    for key, (_, terms) in SIGNAL_RULES.items():
        if any(term in normalized for term in terms):
            tags.append(key)
    if any(term in normalized for term in TRUST_TERMS):
        tags.append("trust")
    if any(term in normalized for term in LOYALTY_TERMS):
        tags.append("loyalty")
    if any(term in normalized for term in REQUEST_TERMS):
        tags.append("direct request")
    if any(term in normalized for term in STIGMA_TERMS):
        tags.append("stigma")
    if any(term in normalized for term in URGENT_TERMS):
        tags.append("urgent")
    return CommentEvidence(
        comment_id=row["comment_id"],
        video_title=row["video_title"] or "Untitled video",
        published_at=row["published_at"],
        text=text,
        is_reply=bool(row["parent_comment_id"]),
        tags=tuple(dict.fromkeys(tags)),
    )


def _build_core_profile(comments: tuple[CommentEvidence, ...], trust_evidence: tuple[CommentEvidence, ...]) -> tuple[Signal, ...]:
    return (
        Signal("Primary audience", "Adults seeking practical mental health tools for anxiety, regulation, habits, fatigue, self-worth, and support gaps. Life-stage conclusions should be treated as evidence signals, not demographics.", "medium", _pick_by_tags(comments, ("self-worth and shame", "limited support", "fatigue and low capacity"), 5)),
        Signal("Life-stage signals", "The clearest signals come from work, parenting/caregiving, therapy-adjacent language, limited support, and chronic health constraints.", "medium", _pick_by_keywords(comments, ("work", "sons", "10-year-old", "therapy", "psychologist", "fatigue", "support"), 5)),
        Signal("Why they choose this creator", "The audience appears to value concise visuals, direct language, practical tools, and professional credibility.", "medium", trust_evidence[:5]),
    )


def _build_emotional_temperature(comments: tuple[CommentEvidence, ...]) -> tuple[Signal, ...]:
    return tuple(
        signal for signal in (
            Signal("Relief and gratitude", "Viewers describe the content as helpful, hopeful, clear, or life-changing.", "low", _pick_by_keywords(comments, ("thank", "helped", "hope", "life changing", "helpful"), 5)),
            Signal("Confusion and need for examples", "Viewers ask what terms mean or request concrete examples.", "medium", _pick_by_keywords(comments, ("examples", "what do you mean", "what does", "i don't understand", "refer to"), 5)),
            Signal("Overwhelm", "Some viewers report too much information or difficulty absorbing dense shorts.", "medium", _pick_by_keywords(comments, ("too much", "overwhelming", "nothing sticks", "chunks", "difficult"), 5)),
            Signal("Isolation and crisis-adjacent distress", "A smaller but important group mentions no support, dark thoughts, panic, or not feeling safe.", "high", _pick_by_tags(comments, ("urgent", "limited support"), 5)),
        )
        if signal.evidence
    )


def _build_unmet_needs(comments: tuple[CommentEvidence, ...]) -> tuple[Signal, ...]:
    return tuple(
        signal for signal in (
            Signal("Concrete examples of abstract tools", "Framework videos should be followed by applied examples.", "high", _pick_by_keywords(comments, ("examples", "what do you mean", "what does", "i don't understand"), 5)),
            Signal("Breaking bad habits", "Habit content triggers explicit requests for bad-habit support.", "medium", _pick_by_keywords(comments, ("bad habits", "break bad", "breaking bad"), 5)),
            Signal("Neurodivergent habit-building", "Some viewers say standard habit advice does not fit neurodivergent minds.", "high", _pick_by_tags(comments, ("neurodivergence",), 5)),
            Signal("Co-regulation without support", "Viewers need regulation tools when no safe person is available.", "high", _pick_by_keywords(comments, ("coregulate", "co-regulate", "support system", "no one"), 5)),
            Signal("Low-capacity reset tools", "Some viewers need alternatives when small actions still feel impossible.", "high", _pick_by_keywords(comments, ("no desire", "dark thoughts", "fatigue", "too tired", "too wired"), 5)),
        )
        if signal.evidence
    )


def _build_blind_spots(comments: tuple[CommentEvidence, ...]) -> tuple[Signal, ...]:
    return tuple(
        signal for signal in (
            Signal("Neurodivergent and trauma-aware adaptations", "Existing frameworks need versions for viewers who do not fit standard advice.", "high", _pick_by_tags(comments, ("neurodivergence",), 5)),
            Signal("No-support regulation", "Relational advice needs solo alternatives.", "high", _pick_by_tags(comments, ("limited support",), 5)),
            Signal("Workplace shame and mistakes", "Work-related self-worth fears appear as a targeted content opportunity.", "medium", _pick_by_keywords(comments, ("work", "mistake", "stupid", "incapable"), 5)),
            Signal("Doomscrolling as low-energy regulation", "Doomscrolling appears as a nervous-system/capacity issue, not only a habit issue.", "medium", _pick_by_keywords(comments, ("doomscroll", "scrolling", "stimulation", "too tired", "too wired"), 5)),
        )
        if signal.evidence
    )


def _build_high_signal_stories(comments: tuple[CommentEvidence, ...]) -> tuple[Signal, ...]:
    candidates = [comment for comment in comments if len(comment.text.split()) >= 18 and ("urgent" in comment.tags or "direct request" in comment.tags or "neurodivergence" in comment.tags or "limited support" in comment.tags)]
    return tuple(
        Signal(
            _short_title(comment.text),
            _truncate(comment.text, 220),
            "high" if "urgent" in comment.tags else "medium",
            (comment,),
        )
        for comment in candidates[:6]
    )


def _build_video_ideas(comments: tuple[CommentEvidence, ...]) -> tuple[VideoIdea, ...]:
    candidates = (
        VideoIdea("How to regulate when you have no one to co-regulate with", "If everyone tells you to reach out, but no one is safe or available, start here.", "Isolation-aware regulation tools.", "high", _pick_by_keywords(comments, ("coregulate", "co-regulate", "support system", "no one", "family", "friends"), 4)),
        VideoIdea("Why habits do not stick for neurodivergent brains", "If you did the same thing for a year and it still never became automatic, you are not broken.", "Neurodivergent habit-building adaptations.", "high", _pick_by_tags(comments, ("neurodivergence",), 4)),
        VideoIdea("What to do when even the tiniest step feels impossible", "When one small step triggers dark thoughts, the advice needs to change.", "Low-capacity, crisis-adjacent activation.", "high", _pick_by_keywords(comments, ("no desire", "dark thoughts", "fatigue", "too hard"), 4)),
        VideoIdea("How to stop fearing mistakes at work", "If one mistake makes you feel stupid, incapable, or exposed, this is the loop to work with.", "Workplace shame and self-worth repair.", "medium", _pick_by_keywords(comments, ("work", "mistake", "stupid", "incapable"), 4)),
        VideoIdea("Doomscrolling is not always laziness", "Sometimes you scroll because you are too wired to rest and too tired to do anything active.", "Shame-free explanation of scrolling as stimulation/regulation.", "medium", _pick_by_keywords(comments, ("doomscroll", "scrolling", "stimulation", "too tired", "too wired"), 4)),
    )
    return tuple(idea for idea in candidates if idea.evidence)[:5]


def _keyword_signal(comments: tuple[CommentEvidence, ...], title: str, description: str, terms: tuple[str, ...], severity: str) -> Signal | None:
    evidence = _pick_by_keywords(comments, terms, 8)
    if not evidence:
        return None
    return Signal(title, description, severity, evidence)


def _signal_from_tag(comments: tuple[CommentEvidence, ...], tag: str, title: str, severity: str) -> Signal:
    return Signal(title, f"Comments reveal signals related to {tag}.", severity, _pick_by_tags(comments, (tag,), 5))


def _pick_by_tags(comments: tuple[CommentEvidence, ...], tags: tuple[str, ...], limit: int) -> tuple[CommentEvidence, ...]:
    return tuple(comment for comment in comments if any(tag in comment.tags for tag in tags))[:limit]


def _pick_by_keywords(comments: tuple[CommentEvidence, ...], terms: tuple[str, ...], limit: int) -> tuple[CommentEvidence, ...]:
    picked: list[CommentEvidence] = []
    for comment in comments:
        text = comment.text.lower()
        if any(term in text for term in terms):
            picked.append(comment)
            if len(picked) >= limit:
                break
    return tuple(picked)


def _count_urgent_comments(comments: tuple[CommentEvidence, ...]) -> int:
    return sum(1 for comment in comments if "urgent" in comment.tags)


def _collect_appendix(*groups: Iterable[Signal] | Iterable[VideoIdea]) -> tuple[CommentEvidence, ...]:
    seen: set[str] = set()
    appendix: list[CommentEvidence] = []
    for group in groups:
        for item in group:
            for evidence in item.evidence:
                if evidence.comment_id not in seen:
                    seen.add(evidence.comment_id)
                    appendix.append(evidence)
    return tuple(appendix)


def _dataset_html(report: AudienceReport) -> str:
    max_comments = max((count for _, count in report.video_counts), default=1)
    bars = "".join(
        f"<div class='bar-row'><span>{escape(_truncate(title, 62))}</span><div class='bar'><i style='width:{max(4, count / max_comments * 100):.0f}%'></i></div><b>{count}</b></div>"
        for title, count in report.video_counts
    )
    return f"""
    <div class="dataset-grid">
      <div class="coverage-card">
        <p class="kicker">Dataset Coverage</p>
        <h3>Source sample</h3>
        <table class="tight">
          <tr><td>Channel</td><td>{escape(report.channel_handle)}</td></tr>
          <tr><td>Videos fetched</td><td>{report.metrics.videos_fetched}</td></tr>
          <tr><td>Comments analyzed</td><td>{report.metrics.comments_analyzed}</td></tr>
          <tr><td>Total comments stored</td><td>{report.metrics.total_comments_stored}</td></tr>
          <tr><td>Replies stored</td><td>{report.metrics.replies_stored}</td></tr>
          <tr><td>Sample range</td><td>{escape(report.metrics.sample_start)} to {escape(report.metrics.sample_end)}</td></tr>
        </table>
      </div>
      <div class="coverage-card">
        <p class="kicker">Recent Video Spread</p>
        <h3>Comment distribution</h3>
        <div class="bars">{bars}</div>
      </div>
    </div>
    """


def _cover_page_html(report: AudienceReport) -> str:
    return f"""
<section class="page cover-page">
  <div class="cover-shell">
    <div class="cover-copy">
      <p class="eyebrow">Psychology Niche Analysis Suite / Report Date: {escape(report.generated_date)}</p>
      <h1>Audience Intelligence Report</h1>
      <h2>Psychological Analysis & Content Strategy</h2>
      <p class="subtitle">Evidence-backed audience insight for a mental health creator: who is watching, what they need, what they trust, and what to make next.</p>
      <div class="creator-card">
        <span>Creator analyzed</span>
        <strong>{escape(report.channel_title)}</strong>
        <code>@{escape(report.channel_handle.lstrip("@"))}</code>
      </div>
    </div>
    <aside class="cover-panel">
      <div class="suite-mark">YT</div>
      <p class="panel-label">Audience Research Suite</p>
      <h3>Comment evidence converted into strategy.</h3>
      <div class="cover-evidence">
        <span>Evidence standard</span>
        <b>Every major insight cites comment IDs.</b>
      </div>
    </aside>
  </div>
  <div class="metric-grid cover-metrics">
    {_metric_card("Comments analyzed", str(report.metrics.comments_analyzed))}
    {_metric_card("Urgent signals", str(report.metrics.urgent_signals))}
    {_metric_card("Video ideas", str(len(report.video_ideas)))}
    {_metric_card("Report date", report.generated_date)}
  </div>
</section>"""


def _signals_html(signals: tuple[Signal, ...], show_severity: bool, grid_class: str = "card-grid") -> str:
    if not signals:
        return "<p class='muted'>No strong evidence-backed signals found in this sample.</p>"
    cards = []
    for signal in signals:
        severity = _severity(signal.severity) if show_severity else ""
        evidence = _evidence_chips(signal.evidence)
        cards.append(f"<article class='signal-card'>{severity}<h3>{escape(signal.title)}</h3><p>{escape(signal.description)}</p>{evidence}</article>")
    return f"<div class='card-grid {escape(grid_class)}'>" + "".join(cards) + "</div>"


def _video_ideas_html(ideas: tuple[VideoIdea, ...]) -> str:
    if not ideas:
        return "<p class='muted'>No evidence-backed video ideas found in this sample.</p>"
    return "<div class='strategy-intro'><div><p class='kicker'>Recommended Concepts</p><h3>Build the next batch around the strongest pain signals.</h3></div><p>Each card ties the hook and audience need back to comment evidence, so the creator can see why the idea exists.</p></div><div class='idea-grid'>" + "".join(
        f"""
        <article class="idea-card">
          <div class="idea-head">{_severity(idea.severity)}<span>{len(idea.evidence)} evidence items</span></div>
          <h3>{escape(idea.title)}</h3>
          <p class="hook">{escape(idea.hook)}</p>
          <div class="need-box"><span>Audience need</span><p>{escape(idea.audience_need)}</p></div>
          {_evidence_chips(idea.evidence)}
        </article>
        """
        for idea in ideas
    ) + "</div>"


def _appendix_html(evidence: tuple[CommentEvidence, ...]) -> str:
    rows = "".join(
        f"<tr><td><code>{escape(item.comment_id)}</code></td><td>{escape(_truncate(', '.join(item.tags) or 'evidence', 40))}</td><td>{escape(_truncate(item.video_title, 48))}</td><td>{escape(_truncate(item.text, 118))}</td></tr>"
        for item in evidence
    )
    return f"<table class='appendix'><thead><tr><th>Comment ID</th><th>Tags</th><th>Video</th><th>Evidence note</th></tr></thead><tbody>{rows}</tbody></table>"


def _theme_heatmap_html(report: AudienceReport) -> str:
    rows = []
    groups: tuple[tuple[str, tuple[Signal, ...]], ...] = (
        ("Unmet Needs", report.unmet_needs),
        ("Stigma Signals", report.stigma_signals),
        ("Blind Spots", report.blind_spots),
        ("Trust Signals", report.trust_signals),
        ("Loyalty Signals", report.loyalty_signals),
    )
    for group, signals in groups:
        for signal in signals[:3]:
            rows.append(
                f"<tr><td>{escape(group)}</td><td>{_severity(signal.severity)}</td><td>{escape(signal.title)}</td><td>{len(signal.evidence)}</td><td>{_evidence_chips(signal.evidence[:3])}</td></tr>"
            )
    return f"""
    <div class="heatmap">
      <div class="heatmap-copy">
        <p class="kicker">Theme Heatmap</p>
        <h3>Signals that deserve creator attention</h3>
        <p>Severity is based on emotional risk, repeated need, and actionability for future content.</p>
      </div>
      <table>
        <thead><tr><th>Area</th><th>Severity</th><th>Signal</th><th>Evidence</th><th>Comment IDs</th></tr></thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </div>
    """


def _section(title: str, body: str, eyebrow: str = "", compact: bool = False, page_number: str = "", klass: str = "") -> str:
    classes = ["page"]
    if compact:
        classes.append("compact")
    if klass:
        classes.append(klass)
    eyebrow_html = f"<p class='page-eyebrow'>{escape(eyebrow)}</p>" if eyebrow else ""
    number_html = f"<span>{escape(page_number)}</span>" if page_number else ""
    return f"<section class='{' '.join(classes)}'><header class='page-header'><div>{eyebrow_html}<h2>{escape(title)}</h2></div>{number_html}</header>{body}</section>"


def _section_block(title: str, body: str) -> str:
    return f"<div class='section-block'><h3>{escape(title)}</h3>{body}</div>"


def _metric_card(label: str, value: str) -> str:
    return f"<div class='metric-card'><span>{escape(label)}</span><strong>{escape(value)}</strong></div>"


def _severity(value: str) -> str:
    return f"<span class='severity severity-{escape(value.lower())}'>{escape(value.upper())}</span>"


def _evidence_chips(evidence: tuple[CommentEvidence, ...]) -> str:
    chips = "".join(f"<code>{escape(item.comment_id)}</code>" for item in evidence[:6])
    return f"<div class='evidence'><span>Evidence</span>{chips}</div>"


def _count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _count_channel_videos(conn: sqlite3.Connection, channel_id: str) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM videos WHERE channel_id = ?", (channel_id,)).fetchone()[0])


def _count_replies(conn: sqlite3.Connection, channel_id: str) -> int:
    return int(conn.execute("SELECT COUNT(*) FROM comments c JOIN videos v ON v.video_id = c.video_id WHERE v.channel_id = ? AND c.parent_comment_id IS NOT NULL", (channel_id,)).fetchone()[0])


def _min_date(comments: tuple[CommentEvidence, ...]) -> str:
    dates = [comment.published_at for comment in comments if comment.published_at]
    return min(dates)[:10] if dates else "n/a"


def _max_date(comments: tuple[CommentEvidence, ...]) -> str:
    dates = [comment.published_at for comment in comments if comment.published_at]
    return max(dates)[:10] if dates else "n/a"


def _slug(value: str) -> str:
    value = value.strip().lower().lstrip("@")
    value = re.sub(r"[^a-z0-9]+", "_", value)
    return value.strip("_") or "youtube_channel"


def _truncate(value: str, length: int) -> str:
    value = " ".join((value or "").split())
    return value if len(value) <= length else value[: length - 3].rstrip() + "..."


def _short_title(value: str) -> str:
    return _truncate(value, 68)


def _css() -> str:
    return """
    @page { size: A4; margin: 0; }
    * { box-sizing: border-box; }
    :root {
__PALETTE_VARS__
    }
    body {{ margin: 0; color: var(--ink); font-family: Arial, Helvetica, sans-serif; font-size: 10.5px; line-height: 1.38; background: var(--cream); }}
    h1, h2, h3, p { margin: 0; }
    .page { width: 210mm; min-height: 297mm; padding: 14mm 15mm 13mm; page-break-after: always; background: var(--cream); position: relative; }
    .page::before { content: ""; position: absolute; left: 0; right: 0; top: 0; height: 5mm; background: linear-gradient(90deg, var(--deep-teal), var(--sage) 50%, var(--clay)); }
    .cover-page { padding: 0; background: var(--cream); }
    .cover-shell { min-height: 226mm; display: grid; grid-template-columns: 1.22fr .78fr; gap: 11mm; padding: 18mm 16mm 12mm; background: linear-gradient(135deg, var(--soft-panel) 0%, var(--cream) 52%, var(--border) 100%); }
    .cover-copy { padding-top: 14mm; }
    .eyebrow, .page-eyebrow, .kicker { color: var(--muted); font-size: 8px; font-weight: 700; letter-spacing: .07em; text-transform: uppercase; margin-bottom: 3mm; }
    .cover-page h1 { color: var(--deep-teal); font-size: 17px; text-transform: uppercase; margin-top: 24mm; }
    .cover-page h2 { color: var(--ink); font-size: 40px; line-height: 1.03; max-width: 119mm; margin-top: 9mm; }
    .subtitle { color: var(--muted); font-size: 13px; line-height: 1.55; max-width: 112mm; margin-top: 7mm; }
    .creator-card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; margin-top: 25mm; padding: 6mm; width: 96mm; }
    .creator-card span, .cover-evidence span { color: var(--muted); display: block; font-size: 8px; font-weight: 700; text-transform: uppercase; }
    .creator-card strong { color: var(--ink); display: block; font-size: 18px; margin: 2mm 0; }
    .creator-card code { font-size: 8px; }
    .cover-panel { align-self: stretch; background: var(--deep-teal); color: var(--card); border-radius: 8px; padding: 8mm; display: flex; flex-direction: column; justify-content: space-between; box-shadow: 0 18px 38px rgba(49,82,76,.18); }
    .suite-mark { width: 22mm; height: 22mm; border: 1px solid var(--sage); display: grid; place-items: center; color: var(--clay); font-weight: 700; font-size: 22px; }
    .panel-label { color: var(--border); font-size: 9px; text-transform: uppercase; font-weight: 700; margin-top: 16mm; }
    .cover-panel h3 { color: var(--card); font-size: 25px; line-height: 1.12; margin-top: 4mm; }
    .cover-evidence { border-top: 1px solid rgba(255,255,255,.18); padding-top: 5mm; }
    .cover-evidence b { display: block; font-size: 12px; line-height: 1.35; margin-top: 2mm; }
    .cover-metrics { padding: 13mm 15mm; margin: 0; }
    .metric-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 4mm; }
    .metric-card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 5mm; min-height: 24mm; box-shadow: 0 5px 18px rgba(49,82,76,.08); }
    .metric-card span { display: block; color: var(--muted); font-size: 7.5px; font-weight: 700; letter-spacing: .06em; text-transform: uppercase; }
    .metric-card strong { color: var(--ink); display: block; font-size: 20px; margin-top: 4mm; }
    .page-header { align-items: flex-start; display: flex; justify-content: space-between; margin-bottom: 7mm; position: relative; z-index: 1; }
    .page-header > span { color: var(--border); font-size: 28px; font-weight: 700; }
    .page h2 { color: var(--ink); font-size: 25px; line-height: 1.12; }
    .page h2::after { content: ""; display: block; width: 34mm; height: 2px; background: var(--clay); margin-top: 3.2mm; }
    .dataset-grid { display: grid; grid-template-columns: .88fr 1.12fr; gap: 5mm; margin-bottom: 6mm; }
    .coverage-card, .heatmap, .strategy-intro { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 5mm; break-inside: avoid; }
    .coverage-card h3, .section-block > h3, .heatmap h3, .strategy-intro h3 { color: var(--ink); font-size: 14px; margin-bottom: 3mm; }
    .section-block { margin-top: 6mm; break-inside: avoid; }
    .section-block:first-of-type { margin-top: 0; }
    .card-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 3.7mm; }
    .profile-grid { grid-template-columns: repeat(3, 1fr); }
    .story-grid { grid-template-columns: repeat(2, 1fr); }
    .signal-card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 4.2mm; min-height: 31mm; break-inside: avoid; box-shadow: 0 4px 14px rgba(49,82,76,.055); }
    .signal-card h3, .idea-card h3 { color: var(--ink); font-size: 12.5px; line-height: 1.2; margin-bottom: 2.2mm; }
    .signal-card p { color: var(--muted); font-size: 9.2px; }
    .heatmap { display: grid; grid-template-columns: 44mm 1fr; gap: 5mm; margin-bottom: 6mm; }
    .heatmap-copy p:last-child, .strategy-intro p { color: var(--muted); font-size: 9.5px; }
    .idea-grid { display: grid; grid-template-columns: 1fr; gap: 4.5mm; }
    .idea-card { background: var(--card); border: 1px solid var(--border); border-left: 7px solid var(--low); border-radius: 8px; padding: 5mm 6mm; break-inside: avoid; box-shadow: 0 7px 20px rgba(49,82,76,.08); }
    .idea-card:nth-child(2) { border-left-color: var(--olive); }
    .idea-card:nth-child(3) { border-left-color: var(--clay); }
    .idea-card:nth-child(4) { border-left-color: var(--lavender); }
    .idea-card:nth-child(5) { border-left-color: var(--blue-gray); }
    .idea-head { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 1mm; }
    .idea-head > span:not(.severity) { color: var(--muted); font-size: 8px; font-weight: 700; text-transform: uppercase; margin-top: 2mm; }
    .hook { color: var(--deep-teal); font-size: 12px; font-weight: 700; margin-bottom: 3mm; }
    .need-box { background: var(--soft-panel); border-radius: 7px; padding: 3mm; margin-bottom: 2mm; }
    .need-box span { color: var(--muted); font-size: 7.5px; font-weight: 700; text-transform: uppercase; }
    .need-box p { color: var(--ink); font-size: 10px; margin-top: 1mm; }
    .severity { display: inline-block; border-radius: 99px; color: var(--white); font-size: 7.3px; font-weight: 700; letter-spacing: .04em; padding: 1.7mm 2.6mm; margin-bottom: 2.4mm; }
    .severity-high { background: var(--high); }
    .severity-medium { background: var(--medium); }
    .severity-low { background: var(--low); }
    .evidence { margin-top: 2.7mm; }
    .evidence span { color: var(--muted); display: block; font-size: 7px; font-weight: 700; letter-spacing: .06em; margin-bottom: 1.2mm; text-transform: uppercase; }
    code { background: var(--soft-panel); border-radius: 4px; color: var(--deep-teal); display: inline-block; font-size: 6.7px; margin: 1px 2px 1px 0; padding: 1.2px 3px; overflow-wrap: anywhere; }
    table { border-collapse: collapse; width: 100%; }
    td, th { border-bottom: 1px solid var(--border); padding: 1.9mm 1.8mm; text-align: left; vertical-align: top; }
    th { color: var(--deep-teal); font-size: 7.2px; text-transform: uppercase; background: var(--soft-panel); }
    .tight td:first-child { color: var(--muted); font-weight: 700; width: 42%; }
    .bars { margin-top: 1mm; }
    .bar-row { align-items: center; display: grid; grid-template-columns: 1.7fr 1fr 24px; gap: 2mm; margin: 1.8mm 0; font-size: 8.3px; }
    .bar { background: var(--soft-panel); border-radius: 999px; height: 5.5px; overflow: hidden; }
    .bar i { background: linear-gradient(90deg, var(--low), var(--clay)); display: block; height: 100%; }
    .appendix { font-size: 7.4px; }
    .appendix td, .appendix th { padding: 1.25mm; }
    .compact { padding-top: 12mm; }
    .strategy-intro { display: grid; grid-template-columns: 72mm 1fr; gap: 7mm; margin-bottom: 5mm; }
    .muted { color: var(--muted); }
    """.replace("__PALETTE_VARS__", palette_css_vars())


def _signals_rows(*groups: tuple[str, tuple[Signal, ...]]) -> list[list[object]]:
    rows: list[list[object]] = [["Section", "Severity", "Signal", "Description", "Evidence comment IDs"]]
    for section, signals in groups:
        for signal in signals:
            rows.append(
                [
                    section,
                    signal.severity.upper(),
                    signal.title,
                    signal.description,
                    ", ".join(item.comment_id for item in signal.evidence),
                ]
            )
    return rows


def _signal_to_dict(signal: Signal) -> dict[str, object]:
    return {
        "title": signal.title,
        "description": signal.description,
        "severity": signal.severity,
        "evidence_count": len(signal.evidence),
        "evidence": [_evidence_to_dict(item) for item in signal.evidence],
    }


def _video_idea_to_dict(idea: VideoIdea) -> dict[str, object]:
    return {
        "title": idea.title,
        "hook": idea.hook,
        "audience_need": idea.audience_need,
        "severity": idea.severity,
        "evidence_count": len(idea.evidence),
        "evidence": [_evidence_to_dict(item) for item in idea.evidence],
    }


def _evidence_to_dict(item: CommentEvidence) -> dict[str, object]:
    return {
        "comment_id": item.comment_id,
        "video_title": item.video_title,
        "published_at": item.published_at,
        "text": item.text,
        "is_reply": item.is_reply,
        "tags": list(item.tags),
    }


class _SimpleXlsx:
    def __init__(self) -> None:
        self.sheets: list[tuple[str, list[list[object]], list[int]]] = []

    def add_sheet(self, name: str, rows: list[list[object]], widths: list[int]) -> None:
        self.sheets.append((name[:31], rows, widths))

    def write(self, output_path: str | Path) -> None:
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with ZipFile(output_path, "w", ZIP_DEFLATED) as zf:
            zf.writestr("[Content_Types].xml", self._content_types())
            zf.writestr("_rels/.rels", self._root_rels())
            zf.writestr("xl/workbook.xml", self._workbook_xml())
            zf.writestr("xl/_rels/workbook.xml.rels", self._workbook_rels())
            zf.writestr("xl/styles.xml", self._styles_xml())
            for index, (name, rows, widths) in enumerate(self.sheets, 1):
                zf.writestr(f"xl/worksheets/sheet{index}.xml", self._worksheet_xml(rows, widths))

    def _content_types(self) -> str:
        sheet_overrides = "".join(
            f'<Override PartName="/xl/worksheets/sheet{index}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            for index in range(1, len(self.sheets) + 1)
        )
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>
  {sheet_overrides}
</Types>"""

    def _root_rels(self) -> str:
        return """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>"""

    def _workbook_xml(self) -> str:
        sheets = "".join(
            f'<sheet name="{xml_escape(name)}" sheetId="{index}" r:id="rId{index}"/>'
            for index, (name, _, _) in enumerate(self.sheets, 1)
        )
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets>{sheets}</sheets>
</workbook>"""

    def _workbook_rels(self) -> str:
        rels = "".join(
            f'<Relationship Id="rId{index}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{index}.xml"/>'
            for index in range(1, len(self.sheets) + 1)
        )
        rels += f'<Relationship Id="rId{len(self.sheets) + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rels}</Relationships>"""

    def _styles_xml(self) -> str:
        ink = MOCK_PALETTE["ink"].lstrip("#")
        white = MOCK_PALETTE["white"].lstrip("#")
        sage = MOCK_PALETTE["sage"].lstrip("#")
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <fonts count="2">
    <font><sz val="10"/><color rgb="FF{ink}"/><name val="Arial"/></font>
    <font><b/><sz val="10"/><color rgb="FF{white}"/><name val="Arial"/></font>
  </fonts>
  <fills count="3">
    <fill><patternFill patternType="none"/></fill>
    <fill><patternFill patternType="gray125"/></fill>
    <fill><patternFill patternType="solid"><fgColor rgb="FF{sage}"/><bgColor indexed="64"/></patternFill></fill>
  </fills>
  <borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>
  <cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
  <cellXfs count="3">
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>
    <xf numFmtId="0" fontId="1" fillId="2" borderId="0" xfId="0" applyFont="1" applyFill="1"/>
    <xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf>
  </cellXfs>
  <cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""

    def _worksheet_xml(self, rows: list[list[object]], widths: list[int]) -> str:
        cols = "".join(
            f'<col min="{index}" max="{index}" width="{width}" customWidth="1"/>'
            for index, width in enumerate(widths, 1)
        )
        row_xml = []
        for row_index, row in enumerate(rows, 1):
            cells = []
            for col_index, value in enumerate(row, 1):
                ref = f"{_xlsx_col(col_index)}{row_index}"
                style = "1" if row_index == 1 or (col_index == 1 and len(row) == 2 and row_index == 1) else "2"
                cells.append(_xlsx_cell(ref, value, style))
            row_xml.append(f'<row r="{row_index}">{"".join(cells)}</row>')
        autofilter = ""
        if rows and len(rows[0]) > 1:
            last_col = _xlsx_col(len(rows[0]))
            autofilter = f'<autoFilter ref="A1:{last_col}{max(1, len(rows))}"/>'
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>
  <cols>{cols}</cols>
  <sheetData>{''.join(row_xml)}</sheetData>
  {autofilter}
</worksheet>"""


def _xlsx_cell(ref: str, value: object, style: str) -> str:
    if value is None:
        value = ""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return f'<c r="{ref}" s="{style}"><v>{value}</v></c>'
    text = xml_escape(str(value))
    return f'<c r="{ref}" s="{style}" t="inlineStr"><is><t>{text}</t></is></c>'


def _xlsx_col(index: int) -> str:
    result = ""
    while index:
        index, remainder = divmod(index - 1, 26)
        result = chr(65 + remainder) + result
    return result


class _SimplePdf:
    width = 595
    height = 842

    def __init__(self) -> None:
        self.pages: list[list[str]] = []
        self.add_page()

    def add_page(self) -> None:
        self.pages.append([])

    def rect(self, x: float, y: float, w: float, h: float, fill: str = "FFFFFF", stroke: str | None = None) -> None:
        self._set_color(fill, fill=True)
        if stroke:
            self._set_color(stroke, fill=False)
            op = "B"
        else:
            op = "f"
        self._cmd(f"{x:.2f} {self.height - y - h:.2f} {w:.2f} {h:.2f} re {op}")

    def text(self, x: float, y: float, value: str, size: int = 10, color: str = "24312F", bold: bool = False) -> None:
        self._set_color(color, fill=True)
        font = "F2" if bold else "F1"
        escaped = _pdf_escape(_pdf_text(value))
        self._cmd(f"BT /{font} {size} Tf {x:.2f} {self.height - y:.2f} Td ({escaped}) Tj ET")

    def line(self, x1: float, y1: float, x2: float, y2: float, color: str = "D9DED6") -> None:
        self._set_color(color, fill=False)
        self._cmd(f"{x1:.2f} {self.height - y1:.2f} m {x2:.2f} {self.height - y2:.2f} l S")

    def _cmd(self, command: str) -> None:
        self.pages[-1].append(command)

    def _set_color(self, color: str, fill: bool) -> None:
        r, g, b = _hex_to_rgb(color)
        op = "rg" if fill else "RG"
        self._cmd(f"{r:.3f} {g:.3f} {b:.3f} {op}")

    def write(self, output_path: str | Path) -> None:
        objects: list[bytes] = []
        page_refs: list[int] = []
        font_regular_id = 3
        font_bold_id = 4
        objects.append(b"<< /Type /Catalog /Pages 2 0 R >>")
        objects.append(b"")
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")
        objects.append(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>")

        for page in self.pages:
            stream = "\n".join(page).encode("latin-1", "replace")
            content_id = len(objects) + 2
            page_id = len(objects) + 1
            page_refs.append(page_id)
            objects.append(
                f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {self.width} {self.height}] "
                f"/Resources << /Font << /F1 {font_regular_id} 0 R /F2 {font_bold_id} 0 R >> >> "
                f"/Contents {content_id} 0 R >>".encode("latin-1")
            )
            objects.append(b"<< /Length " + str(len(stream)).encode("ascii") + b" >>\nstream\n" + stream + b"\nendstream")

        kids = " ".join(f"{page_id} 0 R" for page_id in page_refs)
        objects[1] = f"<< /Type /Pages /Kids [{kids}] /Count {len(page_refs)} >>".encode("latin-1")

        output = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0]
        for object_id, body in enumerate(objects, 1):
            offsets.append(len(output))
            output.extend(f"{object_id} 0 obj\n".encode("ascii"))
            output.extend(body)
            output.extend(b"\nendobj\n")
        xref_pos = len(output)
        output.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
        output.extend(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            output.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
        output.extend(
            f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode("ascii")
        )
        Path(output_path).write_bytes(output)


def _draw_pdf_report(pdf: _SimplePdf, report: AudienceReport) -> None:
    _draw_cover_page(pdf, report)
    _draw_segments_page(pdf, report)
    _draw_audience_voice_page(pdf, report)
    _draw_patterns_page(pdf, report)
    _draw_video_strategy_page(pdf, report)
    _draw_appendix(pdf, report.evidence_appendix)


def _draw_cover_page(pdf: _SimplePdf, report: AudienceReport) -> None:
    y = 54
    pdf.rect(0, 0, pdf.width, pdf.height, "F6F3EE")
    pdf.rect(0, 0, pdf.width, 230, "DDE8E2")
    pdf.text(48, y, f"Psychology Niche Analysis Suite  |  Report Date: {report.generated_date}", 9, "6F897F", bold=True)
    y += 58
    pdf.text(48, y, "AUDIENCE INTELLIGENCE REPORT", 18, "203B38", bold=True)
    y += 38
    y = _draw_wrapped(pdf, 48, y, "Psychological Analysis & Content Strategy", 30, 430, "203B38", bold=True, leading=34)
    y += 14
    y = _draw_wrapped(pdf, 48, y, "A data-driven deep dive into the audience segments, emotional undercurrents, unmet needs, and evidence-backed content opportunities in your community's comment section.", 12, 440, "51635F", leading=16)
    y += 48
    pdf.text(48, y, report.channel_title, 17, "203B38", bold=True)
    y += 16
    pdf.text(48, y, f"@{report.channel_handle.lstrip('@')} • {report.channel_id}", 9, "6F897F")
    y += 36
    metrics = (
        ("Comments analyzed", str(report.metrics.comments_analyzed)),
        ("Urgent signals", str(report.metrics.urgent_signals)),
        ("Video ideas", str(len(report.video_ideas))),
        ("Date", report.generated_date),
    )
    for index, (label, value) in enumerate(metrics):
        x = 48 + index * 124
        pdf.rect(x, y, 112, 62, "FFFDF8", "D9DED6")
        pdf.text(x + 10, y + 18, label, 8, "61726E", bold=True)
        pdf.text(x + 10, y + 43, value, 17, "21413D", bold=True)


def _draw_segments_page(pdf: _SimplePdf, report: AudienceReport) -> None:
    pdf.add_page()
    pdf.rect(0, 0, pdf.width, pdf.height, "F6F3EE")
    y = _draw_page_title(pdf, "Who's Watching: Segment Breakdown", report, 2)
    pdf.text(42, y, "AUDIENCE MENTAL HEALTH PROFILES & INTERESTS", 9, "6F897F", bold=True)
    y += 22
    y = _draw_segment_bars(pdf, y, report.audience_segments)
    y += 14
    y = _draw_section_header(pdf, y, "Dataset Coverage")
    y = _draw_dataset(pdf, y, report)
    y = _draw_signal_section(pdf, y, "Core Audience Profile", report.core_profile)
    y = _draw_signal_section(pdf, y, "Who Is Actually Watching", report.audience_segments)
    y = _draw_signal_section(pdf, y, "Emotional Temperature", report.emotional_temperature)
    y = _draw_signal_section(pdf, y, "Why They Trust This Creator", report.trust_signals, show_severity=False)


def _draw_audience_voice_page(pdf: _SimplePdf, report: AudienceReport) -> None:
    pdf.add_page()
    pdf.rect(0, 0, pdf.width, pdf.height, "F6F3EE")
    y = _draw_page_title(pdf, "Audience Voice: Asks & Questions", report, 3)
    y = _draw_signal_section(pdf, y, "Top Community Demands", report.unmet_needs[:3])
    y = _draw_signal_section(pdf, y, "Direct Requests Inbox", report.direct_requests)
    y = _draw_signal_section(pdf, y, "Stigma And Shame Signals", report.stigma_signals)


def _draw_patterns_page(pdf: _SimplePdf, report: AudienceReport) -> None:
    pdf.add_page()
    pdf.rect(0, 0, pdf.width, pdf.height, "F6F3EE")
    y = _draw_page_title(pdf, "Patterns & Surprises", report, 4)
    y = _draw_section_header(pdf, y, "Theme Heatmap")
    y = _draw_theme_heatmap(pdf, y, report)
    y = _draw_signal_section(pdf, y, "High-Signal Viewers Worth Replying To", report.high_signal_stories)
    y = _draw_signal_section(pdf, y, "Loyalty and Return Signals", report.loyalty_signals, show_severity=False)
    y = _draw_signal_section(pdf, y, "Content Blind Spots", report.blind_spots)


def _draw_video_strategy_page(pdf: _SimplePdf, report: AudienceReport) -> None:
    pdf.add_page()
    pdf.rect(0, 0, pdf.width, pdf.height, "F6F3EE")
    y = _draw_page_title(pdf, "Next Video Strategy", report, 5)
    y = _draw_video_ideas(pdf, y, report.video_ideas)
    if report.video_ideas:
        y = _draw_section_header(pdf, y, '"Address In Next Video" Hook Bank')
        for idea in report.video_ideas[:2]:
            y = _new_page_if_needed(pdf, y, 58)
            pdf.rect(42, y, 510, 48, "FFFDF8", "D9DED6")
            pdf.text(56, y + 17, f"TARGET PROBLEM: {idea.audience_need.upper()[:62]}", 8, "6F897F", bold=True)
            _draw_wrapped(pdf, 56, y + 34, idea.hook, 8, 470, "24312F", leading=10)
            y += 58


def _draw_dataset(pdf: _SimplePdf, y: float, report: AudienceReport) -> float:
    rows = (
        ("Channel", report.channel_handle),
        ("Videos fetched", str(report.metrics.videos_fetched)),
        ("Total comments stored", str(report.metrics.total_comments_stored)),
        ("Replies stored", str(report.metrics.replies_stored)),
        ("Sample range", f"{report.metrics.sample_start} to {report.metrics.sample_end}"),
    )
    pdf.rect(42, y, 510, 100, "FFFDF8", "D9DED6")
    yy = y + 18
    for label, value in rows:
        pdf.text(56, yy, label, 8, "61726E", bold=True)
        pdf.text(180, yy, value, 9, "24312F")
        yy += 16
    y += 116
    max_count = max((count for _, count in report.video_counts), default=1)
    for title, count in report.video_counts[:8]:
        _ensure_room(pdf, y, 18)
        pdf.text(48, y, _truncate(title, 52), 8, "51635F")
        pdf.rect(310, y - 8, 160, 7, "E8ECE6")
        pdf.rect(310, y - 8, max(4, count / max_count * 160), 7, "6F9F92")
        pdf.text(482, y, str(count), 8, "24312F", bold=True)
        y += 15
    return y + 8


def _draw_page_title(pdf: _SimplePdf, title: str, report: AudienceReport, page_number: int) -> float:
    pdf.text(42, 36, f"PAGE {page_number}", 8, "6F897F", bold=True)
    pdf.text(42, 60, title, 20, "203B38", bold=True)
    pdf.text(42, 78, report.channel_title, 9, "6F897F")
    pdf.line(42, 90, 552, 90)
    return 112


def _draw_segment_bars(pdf: _SimplePdf, y: float, signals: tuple[Signal, ...]) -> float:
    if not signals:
        return y
    max_count = max(len(signal.evidence) for signal in signals) or 1
    for signal in signals[:6]:
        count = len(signal.evidence)
        pct = max(8, count / max_count * 100)
        pdf.text(54, y, signal.title, 9, "24312F", bold=True)
        pdf.rect(260, y - 9, 220, 10, "E8ECE6")
        pdf.rect(260, y - 9, 220 * pct / 100, 10, _severity_color(signal.severity))
        pdf.text(492, y, f"{count} refs", 8, "61726E", bold=True)
        y += 22
    return y


def _draw_theme_heatmap(pdf: _SimplePdf, y: float, report: AudienceReport) -> float:
    rows = [
        ("Concrete examples", _signal_by_title(report.unmet_needs, "Concrete examples"), "Requests for examples and definitions after framework videos."),
        ("Neurodivergent fit", _signal_by_title(report.blind_spots, "Neurodivergent"), "Standard habit advice needs adaptations."),
        ("Support absence", _signal_by_title(report.blind_spots, "No-support"), "Co-regulation advice needs solo alternatives."),
        ("Shame / stigma", report.stigma_signals[0] if report.stigma_signals else None, "Work shame, dark thoughts, safety, and support gaps."),
        ("Creator trust", report.trust_signals[0] if report.trust_signals else None, "Clear visual teaching creates trust and repeat use."),
    ]
    pdf.rect(42, y, 510, 26, "DDE8E2", "D9DED6")
    pdf.text(52, y + 17, "THEME", 8, "203B38", bold=True)
    pdf.text(214, y + 17, "SIGNAL STRENGTH", 8, "203B38", bold=True)
    pdf.text(336, y + 17, "MANIFESTATION", 8, "203B38", bold=True)
    y += 28
    for theme, signal, note in rows:
        severity = signal.severity if signal else "low"
        refs = len(signal.evidence) if signal else 0
        pdf.rect(42, y, 510, 38, "FFFDF8", "E2E4DD")
        pdf.text(52, y + 16, theme, 9, "24312F", bold=True)
        pdf.rect(214, y + 8, 54, 14, _severity_color(severity))
        pdf.text(225, y + 18, severity.upper(), 7, "FFFFFF", bold=True)
        pdf.text(276, y + 18, f"{refs} refs", 8, "61726E")
        _draw_wrapped(pdf, 336, y + 14, note, 8, 200, "51635F", leading=10)
        y += 40
    return y + 8


def _signal_by_title(signals: tuple[Signal, ...], title_part: str) -> Signal | None:
    title_part = title_part.lower()
    for signal in signals:
        if title_part in signal.title.lower():
            return signal
    return None


def _draw_signal_section(pdf: _SimplePdf, y: float, title: str, signals: tuple[Signal, ...], show_severity: bool = True) -> float:
    if not signals:
        return y
    y = _new_page_if_needed(pdf, y, 120)
    y = _draw_section_header(pdf, y, title)
    for signal in signals:
        y = _new_page_if_needed(pdf, y, 96)
        card_height = 74
        pdf.rect(42, y, 510, card_height, "FFFDF8", "D9DED6")
        xx = 56
        if show_severity:
            pdf.rect(xx, y + 12, 48, 15, _severity_color(signal.severity))
            pdf.text(xx + 8, y + 23, signal.severity.upper(), 7, "FFFFFF", bold=True)
            xx += 62
        pdf.text(xx, y + 23, signal.title, 11, "203B38", bold=True)
        _draw_wrapped(pdf, 56, y + 40, signal.description, 8, 476, "51635F", leading=10)
        chips = " ".join(item.comment_id for item in signal.evidence[:4])
        _draw_wrapped(pdf, 56, y + 63, f"Evidence: {chips}", 7, 476, "294D48", leading=9)
        y += card_height + 9
    return y + 4


def _draw_video_ideas(pdf: _SimplePdf, y: float, ideas: tuple[VideoIdea, ...]) -> float:
    if not ideas:
        return y
    y = _new_page_if_needed(pdf, y, 140)
    y = _draw_section_header(pdf, y, "Evidence-Grounded Video Ideas")
    colors = ("6F9F92", "8DA56A", "D09B6B", "9F8FB4", "6D95AD")
    for index, idea in enumerate(ideas):
        y = _new_page_if_needed(pdf, y, 122)
        pdf.rect(42, y, 510, 116, "FFFDF8", "D9DED6")
        pdf.rect(42, y, 8, 116, colors[index % len(colors)])
        pdf.rect(60, y + 12, 48, 15, _severity_color(idea.severity))
        pdf.text(68, y + 23, idea.severity.upper(), 7, "FFFFFF", bold=True)
        pdf.text(118, y + 23, idea.title, 12, "203B38", bold=True)
        _draw_wrapped(pdf, 60, y + 45, f"Hook: {idea.hook}", 9, 470, "355753", bold=True, leading=12)
        _draw_wrapped(pdf, 60, y + 71, f"Audience need: {idea.audience_need}", 8, 470, "51635F", leading=11)
        chips = " ".join(item.comment_id for item in idea.evidence[:4])
        _draw_wrapped(pdf, 60, y + 94, f"Evidence: {chips}", 7, 470, "294D48", leading=9)
        y += 127
    return y


def _draw_appendix(pdf: _SimplePdf, evidence: tuple[CommentEvidence, ...]) -> None:
    pdf.add_page()
    pdf.rect(0, 0, pdf.width, pdf.height, "F6F3EE")
    y = 42
    y = _draw_section_header(pdf, y, "Evidence Appendix")
    headers = ("Comment ID", "Tags", "Evidence note")
    widths = (150, 110, 250)
    x_positions = (42, 192, 302)
    pdf.rect(42, y, 510, 20, "E8ECE6")
    for x, header in zip(x_positions, headers):
        pdf.text(x + 4, y + 14, header, 7, "4B625D", bold=True)
    y += 22
    for item in evidence[:70]:
        y = _new_page_if_needed(pdf, y, 24)
        pdf.rect(42, y - 2, 510, 23, "FFFDF8", "E2E4DD")
        pdf.text(46, y + 11, _truncate(item.comment_id, 28), 6, "294D48")
        pdf.text(196, y + 11, _truncate(", ".join(item.tags) or "evidence", 24), 6, "51635F")
        _draw_wrapped(pdf, 306, y + 9, _truncate(item.text, 100), 6, 238, "24312F", leading=7)
        y += 24


def _draw_section_header(pdf: _SimplePdf, y: float, title: str) -> float:
    y = _new_page_if_needed(pdf, y, 48)
    pdf.text(42, y, title, 17, "203B38", bold=True)
    pdf.line(42, y + 10, 552, y + 10)
    return y + 28


def _draw_wrapped(pdf: _SimplePdf, x: float, y: float, value: str, size: int, width: float, color: str, bold: bool = False, leading: int = 12) -> float:
    chars_per_line = max(12, int(width / (size * 0.52)))
    for line in _wrap_text(value, chars_per_line):
        pdf.text(x, y, line, size, color, bold=bold)
        y += leading
    return y


def _wrap_text(value: str, chars_per_line: int) -> list[str]:
    words = _pdf_text(value).split()
    lines: list[str] = []
    current = ""
    for word in words:
        if len(current) + len(word) + 1 > chars_per_line:
            if current:
                lines.append(current)
            current = word
        else:
            current = f"{current} {word}".strip()
    if current:
        lines.append(current)
    return lines or [""]


def _new_page_if_needed(pdf: _SimplePdf, y: float, needed: float) -> float:
    if y + needed <= 800:
        return y
    pdf.add_page()
    pdf.rect(0, 0, pdf.width, pdf.height, "F6F3EE")
    return 42


def _ensure_room(pdf: _SimplePdf, y: float, needed: float) -> None:
    if y + needed > 800:
        pdf.add_page()
        pdf.rect(0, 0, pdf.width, pdf.height, "F6F3EE")


def _severity_color(severity: str) -> str:
    return {"high": "B35C4B", "medium": "B58A45", "low": "5F8F83"}.get(severity.lower(), "5F8F83")


def _hex_to_rgb(color: str) -> tuple[float, float, float]:
    color = color.lstrip("#")
    return tuple(int(color[index:index + 2], 16) / 255 for index in (0, 2, 4))  # type: ignore[return-value]


def _pdf_text(value: str) -> str:
    replacements = {
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        "…": "...",
        "→": "->",
    }
    for source, target in replacements.items():
        value = value.replace(source, target)
    return value.encode("latin-1", "replace").decode("latin-1")


def _pdf_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
