from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from yt_audience_report.fetch.sync import YouTubeSyncService
from yt_audience_report.fetch.youtube_client import YouTubeApiError, YouTubeClient, YouTubeNetworkError
from yt_audience_report.report import build_report, render_report_json, render_report_pdf, render_report_xlsx
from yt_audience_report.storage.sqlite import SQLiteStore


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fetch YouTube comments and generate an audience report PDF.")
    parser.add_argument("--channel", required=True, help="YouTube channel handle or URL, e.g. @channelhandle.")
    parser.add_argument("--max-videos", type=int, default=30, help="Recent videos to fetch before analysis.")
    parser.add_argument("--max-comments", type=int, default=200, help="Most recent comments to analyze.")
    parser.add_argument("--db-path", default="data/yt-audience-report.sqlite3", help="SQLite database path.")
    parser.add_argument("--reports-dir", default="reports", help="Directory for generated reports.")
    parser.add_argument("--skip-replies", action="store_true", help="Fetch top-level comments only.")
    parser.add_argument("--force-refresh", action="store_true", help="Re-fetch comments already marked fetched.")
    parser.add_argument("--no-fetch", action="store_true", help="Generate reports from current database data without calling YouTube.")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_dotenv()
    api_key = os.getenv("YOUTUBE_API_KEY", "")
    if not api_key:
        raise SystemExit("YOUTUBE_API_KEY is missing. Add it to .env or your shell environment.")

    store = SQLiteStore(args.db_path)
    try:
        if args.no_fetch:
            report = build_report(store.conn, None, max_comments=args.max_comments)
        else:
            service = YouTubeSyncService(YouTubeClient(api_key), store)
            fetch_summary = service.fetch_channel(
                args.channel,
                max_videos=args.max_videos,
                include_replies=not args.skip_replies,
                force_refresh=args.force_refresh,
            )
            report = build_report(store.conn, fetch_summary.channel_id, max_comments=args.max_comments)
    except (YouTubeApiError, YouTubeNetworkError) as exc:
        raise SystemExit(str(exc)) from exc
    finally:
        store.close()

    report_date = datetime.now().strftime("%Y-%m-%d")
    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    output_path = reports_dir / f"{report.channel_slug}_{report_date}_audience_report.pdf"
    workbook_path = reports_dir / f"{report.channel_slug}_{report_date}_audience_report.xlsx"
    json_path = reports_dir / f"{report.channel_slug}_{report_date}_audience_report.json"
    render_report_pdf(report, output_path)
    render_report_xlsx(report, workbook_path)
    render_report_json(report, json_path)

    print(f"Report generated: {output_path}")
    print(f"Workbook generated: {workbook_path}")
    print(f"JSON generated: {json_path}")
    print(f"Comments analyzed: {report.metrics.comments_analyzed}")
    print(f"Urgent signals: {report.metrics.urgent_signals}")
    print(f"Video ideas: {len(report.video_ideas)}")


if __name__ == "__main__":
    main()
