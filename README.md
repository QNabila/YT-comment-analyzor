# yt-audience-report

`yt-audience-report` is a local pipeline for psychology and mental health YouTube creators. The first module fetches public channel, video, and comment data from the YouTube Data API v3 and stores it in SQLite for later AI analysis.

## YouTube API Setup

1. Create a Google Cloud project.
2. Enable **YouTube Data API v3**.
3. Create an API key.
4. Restrict the key to YouTube Data API v3.
5. Add the key to a local `.env` file:

```bash
YOUTUBE_API_KEY=your_key_here
```

Public channel, video, and published comment reads only require an API key. OAuth is not needed for this first fetch module.

## Install

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Fetch A Channel

```bash
yt-audience-report fetch "https://www.youtube.com/@somecreator"
```

Defaults:

- Fetches 10 recent public videos.
- Fetches all available top-level comments.
- Fetches replies.
- Stores data in `data/yt-audience-report.sqlite3`.
- Does not re-fetch comments for videos already marked as fully fetched unless `--force-refresh` is used.

Useful flags:

```bash
yt-audience-report fetch "@somecreator" --max-videos 25
yt-audience-report fetch "@somecreator" --skip-replies
yt-audience-report fetch "@somecreator" --force-refresh
yt-audience-report fetch "@somecreator" --db-path data/custom.sqlite3
```

Supported channel inputs:

- `@creator`
- `https://www.youtube.com/@creator`
- `https://www.youtube.com/channel/UC...`
- `https://www.youtube.com/user/legacyName`

Ambiguous custom URLs like `https://www.youtube.com/c/name` are rejected. Use the channel's `@handle` or `/channel/UC...` URL instead.

## Generate A Full Audience Report

Use `main.py` to run the complete local flow:

```bash
python3 main.py --channel @somecreator
```

This will:

- Fetch recent videos and comments.
- Analyze the most recent comments.
- Generate a PDF report and Excel workbook.
- Save them to `reports/{channel_name}_{date}_audience_report.pdf`, `reports/{channel_name}_{date}_audience_report.xlsx`, and `reports/{channel_name}_{date}_audience_report.json`.

Useful flags:

```bash
python3 main.py --channel @somecreator --max-videos 30 --max-comments 200
python3 main.py --channel @somecreator --force-refresh
python3 main.py --channel @somecreator --no-fetch
python3 main.py --channel @somecreator --reports-dir reports
```

The report is designed for psychology and mental health creators. It uses an at-a-glance page 1, severity indicators, distinct video idea cards, and a compact evidence appendix. The PDF follows a polished suite structure: cover, segment breakdown, audience voice, patterns, video strategy, and appendix. The Excel workbook mirrors the same data in scannable tabs. The JSON artifact is used by the local dashboard and preserves the same evidence-backed structure.

## Run The Local Dashboard

After generating a report JSON, start the dashboard:

```bash
python3 -m yt_audience_report.dashboard --db-path data/yt-audience-report.sqlite3 --reports-dir reports --port 8000
```

Open `http://127.0.0.1:8000`.

The dashboard is read-only. It loads channels from SQLite, reads the latest generated report JSON for the selected channel, and visualizes audience segments, emotional temperature, unmet needs, blind spots, video ideas, high-signal stories, direct requests, and comment volume per video.

## Deploy The Read-Only Dashboard To Vercel

Vercel is only for the read-only dashboard. The YouTube fetch, analysis, PDF generation, Excel generation, and SQLite database stay local.

Deployment uses:

- `app.py` as the FastAPI entrypoint Vercel can discover.
- `vercel.json` to explicitly route all requests to the Python function.
- `requirements.txt` so Vercel installs the dashboard runtime dependencies.
- `reports/*_audience_report.json` as the hosted dashboard data source.
- `public/research_mark.png` as the dashboard header asset.

Before deploying, generate and commit a report JSON:

```bash
python3 main.py --channel @somecreator --no-fetch
git add reports/*_audience_report.json
git commit -m "Add latest dashboard report data"
git push
```

Do not deploy `.env` or `data/`. They are intentionally ignored.
