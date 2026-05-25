from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


class SQLiteStore:
    """SQLite persistence for fetched YouTube source data."""

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.init_schema()

    def close(self) -> None:
        self.conn.close()

    def init_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS channels (
                channel_id TEXT PRIMARY KEY,
                handle TEXT,
                title TEXT,
                description TEXT,
                uploads_playlist_id TEXT,
                raw_json TEXT NOT NULL,
                first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS videos (
                video_id TEXT PRIMARY KEY,
                channel_id TEXT NOT NULL,
                title TEXT,
                description TEXT,
                published_at TEXT,
                statistics_json TEXT,
                raw_json TEXT NOT NULL,
                comments_fetched_at TEXT,
                comments_disabled INTEGER NOT NULL DEFAULT 0,
                first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                last_fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (channel_id) REFERENCES channels(channel_id)
            );

            CREATE TABLE IF NOT EXISTS comments (
                comment_id TEXT PRIMARY KEY,
                video_id TEXT NOT NULL,
                parent_comment_id TEXT,
                author_channel_id TEXT,
                author_display_name TEXT,
                text TEXT,
                like_count INTEGER,
                published_at TEXT,
                updated_at TEXT,
                raw_json TEXT NOT NULL,
                fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (video_id) REFERENCES videos(video_id)
            );

            CREATE TABLE IF NOT EXISTS fetch_runs (
                run_id INTEGER PRIMARY KEY AUTOINCREMENT,
                input TEXT NOT NULL,
                resolved_channel_id TEXT,
                started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                finished_at TEXT,
                status TEXT NOT NULL,
                video_count INTEGER NOT NULL DEFAULT 0,
                comment_count INTEGER NOT NULL DEFAULT 0,
                reply_count INTEGER NOT NULL DEFAULT 0,
                skipped_video_count INTEGER NOT NULL DEFAULT 0,
                error_message TEXT
            );

            CREATE TABLE IF NOT EXISTS fetch_skips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                video_id TEXT,
                reason TEXT NOT NULL,
                detail TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (run_id) REFERENCES fetch_runs(run_id)
            );
            """
        )
        self.conn.commit()

    def start_fetch_run(self, input_value: str) -> int:
        cursor = self.conn.execute(
            "INSERT INTO fetch_runs (input, status) VALUES (?, ?)",
            (input_value, "running"),
        )
        self.conn.commit()
        return int(cursor.lastrowid)

    def finish_fetch_run(
        self,
        run_id: int,
        status: str,
        resolved_channel_id: str | None,
        video_count: int,
        comment_count: int,
        reply_count: int,
        skipped_video_count: int,
        error_message: str | None = None,
    ) -> None:
        self.conn.execute(
            """
            UPDATE fetch_runs
            SET status = ?,
                resolved_channel_id = ?,
                finished_at = CURRENT_TIMESTAMP,
                video_count = ?,
                comment_count = ?,
                reply_count = ?,
                skipped_video_count = ?,
                error_message = ?
            WHERE run_id = ?
            """,
            (
                status,
                resolved_channel_id,
                video_count,
                comment_count,
                reply_count,
                skipped_video_count,
                error_message,
                run_id,
            ),
        )
        self.conn.commit()

    def record_skip(self, run_id: int, video_id: str | None, reason: str, detail: str | None = None) -> None:
        self.conn.execute(
            "INSERT INTO fetch_skips (run_id, video_id, reason, detail) VALUES (?, ?, ?, ?)",
            (run_id, video_id, reason, detail),
        )
        self.conn.commit()

    def upsert_channel(self, channel: dict[str, Any]) -> None:
        snippet = channel.get("snippet", {})
        content_details = channel.get("contentDetails", {})
        related_playlists = content_details.get("relatedPlaylists", {})
        custom_url = snippet.get("customUrl")
        handle = custom_url.lstrip("@") if isinstance(custom_url, str) else None
        self.conn.execute(
            """
            INSERT INTO channels (
                channel_id, handle, title, description, uploads_playlist_id, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(channel_id) DO UPDATE SET
                handle = excluded.handle,
                title = excluded.title,
                description = excluded.description,
                uploads_playlist_id = excluded.uploads_playlist_id,
                raw_json = excluded.raw_json,
                last_fetched_at = CURRENT_TIMESTAMP
            """,
            (
                channel["id"],
                handle,
                snippet.get("title"),
                snippet.get("description"),
                related_playlists.get("uploads"),
                _json(channel),
            ),
        )
        self.conn.commit()

    def upsert_video(self, video: dict[str, Any], channel_id: str) -> None:
        snippet = video.get("snippet", {})
        self.conn.execute(
            """
            INSERT INTO videos (
                video_id, channel_id, title, description, published_at, statistics_json, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(video_id) DO UPDATE SET
                channel_id = excluded.channel_id,
                title = excluded.title,
                description = excluded.description,
                published_at = excluded.published_at,
                statistics_json = excluded.statistics_json,
                raw_json = excluded.raw_json,
                last_fetched_at = CURRENT_TIMESTAMP
            """,
            (
                video["id"],
                channel_id,
                snippet.get("title"),
                snippet.get("description"),
                snippet.get("publishedAt"),
                _json(video.get("statistics", {})),
                _json(video),
            ),
        )
        self.conn.commit()

    def upsert_comment(
        self,
        comment: dict[str, Any],
        video_id: str,
        parent_comment_id: str | None = None,
    ) -> None:
        snippet = comment.get("snippet", {})
        author_channel_id = snippet.get("authorChannelId")
        if isinstance(author_channel_id, dict):
            author_channel_id = author_channel_id.get("value")
        self.conn.execute(
            """
            INSERT INTO comments (
                comment_id, video_id, parent_comment_id, author_channel_id,
                author_display_name, text, like_count, published_at, updated_at, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(comment_id) DO UPDATE SET
                video_id = excluded.video_id,
                parent_comment_id = excluded.parent_comment_id,
                author_channel_id = excluded.author_channel_id,
                author_display_name = excluded.author_display_name,
                text = excluded.text,
                like_count = excluded.like_count,
                published_at = excluded.published_at,
                updated_at = excluded.updated_at,
                raw_json = excluded.raw_json,
                fetched_at = CURRENT_TIMESTAMP
            """,
            (
                comment["id"],
                video_id,
                parent_comment_id,
                author_channel_id,
                snippet.get("authorDisplayName"),
                snippet.get("textDisplay"),
                snippet.get("likeCount"),
                snippet.get("publishedAt"),
                snippet.get("updatedAt"),
                _json(comment),
            ),
        )
        self.conn.commit()

    def mark_comments_fetched(self, video_id: str) -> None:
        self.conn.execute(
            "UPDATE videos SET comments_fetched_at = CURRENT_TIMESTAMP, comments_disabled = 0 WHERE video_id = ?",
            (video_id,),
        )
        self.conn.commit()

    def mark_comments_disabled(self, video_id: str) -> None:
        self.conn.execute(
            "UPDATE videos SET comments_fetched_at = CURRENT_TIMESTAMP, comments_disabled = 1 WHERE video_id = ?",
            (video_id,),
        )
        self.conn.commit()

    def comments_already_fetched(self, video_id: str) -> bool:
        row = self.conn.execute(
            "SELECT comments_fetched_at FROM videos WHERE video_id = ?",
            (video_id,),
        ).fetchone()
        return bool(row and row["comments_fetched_at"])


def _json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)

