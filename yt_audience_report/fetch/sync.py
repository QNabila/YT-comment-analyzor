from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from yt_audience_report.fetch.resolver import resolve_channel
from yt_audience_report.fetch.youtube_client import YouTubeApiError, YouTubeClient
from yt_audience_report.storage.sqlite import SQLiteStore


@dataclass
class FetchSummary:
    run_id: int
    channel_id: str | None
    video_count: int = 0
    comment_count: int = 0
    reply_count: int = 0
    skipped_video_count: int = 0
    status: str = "running"
    error_message: str | None = None


class YouTubeSyncService:
    def __init__(self, client: YouTubeClient, store: SQLiteStore) -> None:
        self.client = client
        self.store = store

    def fetch_channel(
        self,
        channel_input: str,
        max_videos: int = 10,
        include_replies: bool = True,
        force_refresh: bool = False,
    ) -> FetchSummary:
        run_id = self.store.start_fetch_run(channel_input)
        summary = FetchSummary(run_id=run_id, channel_id=None)

        try:
            channel = resolve_channel(self.client, channel_input)
            summary.channel_id = channel["id"]
            self.store.upsert_channel(channel)

            uploads_playlist_id = channel.get("contentDetails", {}).get("relatedPlaylists", {}).get("uploads")
            if not uploads_playlist_id:
                raise RuntimeError("Resolved channel does not expose an uploads playlist.")

            video_ids = self._fetch_recent_video_ids(uploads_playlist_id, max_videos)
            videos = self.client.videos_by_ids(video_ids)
            video_by_id = {video["id"]: video for video in videos}

            for video_id in video_ids:
                video = video_by_id.get(video_id)
                if not video:
                    summary.skipped_video_count += 1
                    self.store.record_skip(run_id, video_id, "video_unavailable", "Video not returned by videos.list.")
                    continue

                self.store.upsert_video(video, channel["id"])
                summary.video_count += 1

                if not force_refresh and self.store.comments_already_fetched(video_id):
                    continue

                comments, replies, skipped = self._fetch_video_comments(
                    run_id,
                    video_id,
                    include_replies=include_replies,
                )
                summary.comment_count += comments
                summary.reply_count += replies
                summary.skipped_video_count += skipped

            summary.status = "completed"
            return summary
        except Exception as exc:
            summary.status = "failed"
            summary.error_message = str(exc)
            raise
        finally:
            self.store.finish_fetch_run(
                run_id=summary.run_id,
                status=summary.status,
                resolved_channel_id=summary.channel_id,
                video_count=summary.video_count,
                comment_count=summary.comment_count,
                reply_count=summary.reply_count,
                skipped_video_count=summary.skipped_video_count,
                error_message=summary.error_message,
            )

    def _fetch_recent_video_ids(self, uploads_playlist_id: str, max_videos: int) -> list[str]:
        video_ids: list[str] = []
        page_token: str | None = None
        while len(video_ids) < max_videos:
            page_size = min(50, max_videos - len(video_ids))
            page = self.client.playlist_items_page(
                uploads_playlist_id,
                max_results=page_size,
                page_token=page_token,
            )
            for item in page.get("items", []):
                video_id = item.get("contentDetails", {}).get("videoId")
                if video_id:
                    video_ids.append(video_id)
                    if len(video_ids) >= max_videos:
                        break

            page_token = page.get("nextPageToken")
            if not page_token:
                break

        return video_ids

    def _fetch_video_comments(
        self,
        run_id: int,
        video_id: str,
        include_replies: bool,
    ) -> tuple[int, int, int]:
        comment_count = 0
        reply_count = 0
        skipped_count = 0
        page_token: str | None = None

        try:
            while True:
                page = self.client.comment_threads_page(video_id, page_token=page_token)
                for thread in page.get("items", []):
                    top_comment = thread.get("snippet", {}).get("topLevelComment")
                    if not top_comment:
                        continue

                    self.store.upsert_comment(top_comment, video_id)
                    comment_count += 1

                    if include_replies:
                        inline_reply_ids = self._store_inline_replies(thread, video_id, top_comment["id"])
                        reply_count += len(inline_reply_ids)

                        total_reply_count = thread.get("snippet", {}).get("totalReplyCount", 0)
                        if total_reply_count > len(inline_reply_ids):
                            reply_count += self._fetch_all_replies(video_id, top_comment["id"], inline_reply_ids)

                page_token = page.get("nextPageToken")
                if not page_token:
                    break

            self.store.mark_comments_fetched(video_id)
            return comment_count, reply_count, skipped_count
        except YouTubeApiError as exc:
            if exc.reason == "commentsDisabled":
                self.store.mark_comments_disabled(video_id)
                self.store.record_skip(run_id, video_id, "comments_disabled", exc.message)
                return comment_count, reply_count, 1
            raise

    def _store_inline_replies(self, thread: dict[str, Any], video_id: str, parent_id: str) -> set[str]:
        replies = thread.get("replies", {}).get("comments", [])
        reply_ids: set[str] = set()
        for reply in replies:
            self.store.upsert_comment(reply, video_id, parent_comment_id=parent_id)
            reply_ids.add(reply["id"])
        return reply_ids

    def _fetch_all_replies(self, video_id: str, parent_id: str, seen_reply_ids: set[str]) -> int:
        reply_count = 0
        page_token: str | None = None
        seen = set(seen_reply_ids)

        while True:
            page = self.client.replies_page(parent_id, page_token=page_token)
            for reply in page.get("items", []):
                reply_id = reply["id"]
                if reply_id in seen:
                    continue
                seen.add(reply_id)
                self.store.upsert_comment(reply, video_id, parent_comment_id=parent_id)
                reply_count += 1

            page_token = page.get("nextPageToken")
            if not page_token:
                break

        return reply_count
