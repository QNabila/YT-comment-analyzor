---
name: yt-audience-report
description: Use this skill when the user provides a psychology or mental health YouTube channel handle or URL and wants the complete yt-audience-report pipeline run: fetch recent videos and comments, analyze audience signals, generate an evidence-backed PDF report and Excel workbook, and save them with the channel name and date.
---

# yt-audience-report

Run the local YouTube audience insight pipeline for psychology and mental health creators.

## Trigger Pattern

Use the project entrypoint:

```bash
python main.py --channel @channelhandle
```

The channel handle or URL is the only required input. Examples:

```bash
python main.py --channel @the.pocket.psychologist
python main.py --channel https://www.youtube.com/@the.pocket.psychologist
```

## Workflow

1. Confirm the working directory is the `yt-audience-report` project.
2. Ensure `.env` contains `YOUTUBE_API_KEY`.
3. Run `python main.py --channel <handle-or-url>`.
4. Confirm the generated PDF, Excel workbook, and JSON paths in `reports/`.
5. If asked to validate, run `python3 -m pytest`.

If the user explicitly says not to fetch again, use:

```bash
python main.py --channel @channelhandle --no-fetch
```

## Report Requirements

The PDF and Excel workbook must remain the final deliverables. Do not replace them with a dashboard.

The report must include:

- Executive Insight Snapshot.
- Dataset Coverage.
- Core Audience Profile.
- Who Is Actually Watching.
- Emotional Temperature with a "Why They Trust This Creator" subsection.
- Top Unmet Needs.
- Direct Requests Inbox.
- Stigma And Shame Signals.
- High-Signal Viewer Stories with a "Loyalty and Return Signals" note.
- Content Blind Spots.
- Evidence-Grounded Video Ideas.
- Evidence Appendix.
- Companion Excel workbook with Summary, Audience Signals, Video Ideas, and Evidence Appendix tabs.
- Companion JSON artifact with the same evidence-backed report structure for dashboard use.

## Evidence Rules

- Every substantive insight must cite real comment IDs.
- Do not produce vibe-based conclusions.
- Do not infer demographics beyond what comments support.
- Label age and life-stage conclusions as weak, moderate, or strong evidence.
- Separate direct viewer statements from inferred creator positioning.
- Video ideas must include comment-ID evidence.

## Design Rules

- Page 1 must show total comments analyzed, urgent signals, video idea count, and date.
- Follow the polished suite structure: cover, audience segment breakdown, audience voice, patterns and surprises, next video strategy, and evidence appendix.
- Use high / medium / low severity indicators for unmet needs, stigma signals, and content blind spots.
- Style video ideas as distinct cards with title, hook, audience need, and evidence.
- Keep the evidence appendix compact and table-based.
- Keep the Excel workbook compact, sortable, and useful for evidence review. It must show the same data as the PDF using tabs that mirror the report sections.
- Use only the approved mock report palette for PDF, Excel, JSON-backed dashboard UI, and generated header assets:
  - Ink `#203B38`
  - Deep teal `#31524C`
  - Sage `#6F9F92`
  - Olive `#8DA56A`
  - Clay `#D09B6B`
  - Lavender `#9F8FB4`
  - Blue-gray `#6D95AD`
  - Cream `#F6F3EE`
  - Card `#FFFDF8`
  - Soft panel `#E8ECE6`
  - Border `#D9DED6`
  - Muted text `#61726E`
  - High `#B35C4B`
  - Medium `#B58A45`
  - Low `#5F8F83`

## Dashboard Rules

When the user asks for the local dashboard, use:

```bash
python -m yt_audience_report.dashboard --db-path data/yt-audience-report.sqlite3 --reports-dir reports --port 8000
```

The dashboard must be localhost-only, read-only, unauthenticated, and backed by SQLite plus the generated report JSON. It must not fetch YouTube data during startup.
