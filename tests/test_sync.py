import pytest

from yt_audience_report.fetch.sync import YouTubeSyncService
from yt_audience_report.fetch.youtube_client import YouTubeApiError
from yt_audience_report.storage.sqlite import SQLiteStore


class FakeClient:
    def __init__(self, comments_disabled=False):
        self.comments_disabled = comments_disabled

    def channels_by_handle(self, handle):
        return {
            "id": "UC123",
            "snippet": {"title": "Creator", "customUrl": f"@{handle}"},
            "contentDetails": {"relatedPlaylists": {"uploads": "UU123"}},
            "statistics": {},
        }

    def channels_by_id(self, channel_id):
        return None

    def channels_by_username(self, username):
        return None

    def playlist_items_page(self, playlist_id, max_results=50, page_token=None):
        return {
            "items": [
                {"contentDetails": {"videoId": "vid1"}},
                {"contentDetails": {"videoId": "vid2"}},
            ]
        }

    def videos_by_ids(self, video_ids):
        return [
            {"id": video_id, "snippet": {"title": video_id}, "statistics": {}}
            for video_id in video_ids
        ]

    def comment_threads_page(self, video_id, page_token=None):
        if self.comments_disabled:
            raise YouTubeApiError(403, "commentsDisabled", "Comments disabled")
        if page_token == "page2":
            return {
                "items": [
                    {
                        "snippet": {
                            "topLevelComment": {"id": f"{video_id}-c2", "snippet": {"textDisplay": "second page"}},
                            "totalReplyCount": 0,
                        }
                    }
                ]
            }
        return {
            "nextPageToken": "page2",
            "items": [
                {
                    "snippet": {
                        "topLevelComment": {"id": f"{video_id}-c1", "snippet": {"textDisplay": "top"}},
                        "totalReplyCount": 6,
                    },
                    "replies": {
                        "comments": [
                            {"id": f"{video_id}-c1-r1", "snippet": {"textDisplay": "inline reply"}}
                        ]
                    },
                }
            ],
        }

    def replies_page(self, parent_id, page_token=None):
        return {
            "items": [
                {"id": f"{parent_id}-r1", "snippet": {"textDisplay": "inline duplicate"}},
                {"id": f"{parent_id}-r2", "snippet": {"textDisplay": "extra reply"}},
            ]
        }


def test_sync_fetches_paginated_comments_and_replies(tmp_path):
    store = SQLiteStore(tmp_path / "test.sqlite3")
    service = YouTubeSyncService(FakeClient(), store)
    summary = service.fetch_channel("@creator", max_videos=2)

    assert summary.status == "completed"
    assert summary.video_count == 2
    assert summary.comment_count == 4
    assert summary.reply_count == 4

    rows = store.conn.execute("SELECT comment_id, parent_comment_id FROM comments").fetchall()
    ids = {row["comment_id"] for row in rows}
    assert "vid1-c1" in ids
    assert "vid1-c2" in ids
    assert "vid1-c1-r2" in ids
    assert any(row["parent_comment_id"] == "vid1-c1" for row in rows)
    store.close()


def test_sync_records_comments_disabled_without_failing(tmp_path):
    store = SQLiteStore(tmp_path / "test.sqlite3")
    service = YouTubeSyncService(FakeClient(comments_disabled=True), store)
    summary = service.fetch_channel("@creator", max_videos=1)

    assert summary.status == "completed"
    assert summary.video_count == 1
    assert summary.skipped_video_count == 1
    skip = store.conn.execute("SELECT reason FROM fetch_skips").fetchone()
    assert skip["reason"] == "comments_disabled"
    store.close()
