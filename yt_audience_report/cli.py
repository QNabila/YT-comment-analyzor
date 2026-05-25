from __future__ import annotations

import os
from pathlib import Path

import typer
from dotenv import load_dotenv

from yt_audience_report.fetch.resolver import ChannelInputError
from yt_audience_report.fetch.sync import YouTubeSyncService
from yt_audience_report.fetch.youtube_client import YouTubeApiError, YouTubeClient, YouTubeNetworkError
from yt_audience_report.storage.sqlite import SQLiteStore


app = typer.Typer(help="Local YouTube audience report tools.")


@app.callback()
def main() -> None:
    """Local YouTube audience report tools."""


@app.command()
def fetch(
    channel: str = typer.Argument(..., help="YouTube @handle or channel URL."),
    max_videos: int = typer.Option(10, "--max-videos", min=1, max=50, help="Recent videos to fetch."),
    db_path: Path = typer.Option(
        Path("data/yt-audience-report.sqlite3"),
        "--db-path",
        help="SQLite database path.",
    ),
    skip_replies: bool = typer.Option(False, "--skip-replies", help="Fetch top-level comments only."),
    force_refresh: bool = typer.Option(
        False,
        "--force-refresh",
        help="Re-fetch comments for videos already marked as fetched.",
    ),
) -> None:
    """Fetch recent videos and comments for a YouTube channel."""

    load_dotenv()
    api_key = os.getenv("YOUTUBE_API_KEY", "")
    if not api_key:
        raise typer.BadParameter("YOUTUBE_API_KEY is missing. Add it to .env or your shell environment.")

    store = SQLiteStore(db_path)
    try:
        service = YouTubeSyncService(YouTubeClient(api_key), store)
        summary = service.fetch_channel(
            channel,
            max_videos=max_videos,
            include_replies=not skip_replies,
            force_refresh=force_refresh,
        )
    except ChannelInputError as exc:
        raise typer.BadParameter(str(exc)) from exc
    except YouTubeApiError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    except YouTubeNetworkError as exc:
        typer.echo(str(exc), err=True)
        raise typer.Exit(code=1) from exc
    finally:
        store.close()

    typer.echo(f"Fetch run {summary.run_id} completed.")
    typer.echo(f"Channel: {summary.channel_id}")
    typer.echo(f"Videos fetched: {summary.video_count}")
    typer.echo(f"Top-level comments fetched: {summary.comment_count}")
    typer.echo(f"Replies fetched: {summary.reply_count}")
    typer.echo(f"Videos skipped: {summary.skipped_video_count}")
    typer.echo(f"Database: {db_path}")


if __name__ == "__main__":
    app()
