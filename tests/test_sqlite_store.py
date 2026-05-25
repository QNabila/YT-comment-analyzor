import sqlite3

from yt_audience_report.storage.sqlite import SQLiteStore


def test_upserts_without_duplicate_comments(tmp_path):
    db_path = tmp_path / "test.sqlite3"
    store = SQLiteStore(db_path)
    channel = {
        "id": "UC123",
        "snippet": {"title": "Creator", "description": "Desc", "customUrl": "@creator"},
        "contentDetails": {"relatedPlaylists": {"uploads": "UU123"}},
    }
    video = {
        "id": "vid1",
        "snippet": {"title": "Video", "description": "Desc", "publishedAt": "2026-01-01T00:00:00Z"},
        "statistics": {"commentCount": "1"},
    }
    comment = {
        "id": "comment1",
        "snippet": {
            "authorDisplayName": "Viewer",
            "authorChannelId": {"value": "viewer1"},
            "textDisplay": "Please make a video about burnout.",
            "likeCount": 3,
            "publishedAt": "2026-01-02T00:00:00Z",
            "updatedAt": "2026-01-02T00:00:00Z",
        },
    }

    store.upsert_channel(channel)
    store.upsert_channel(channel)
    store.upsert_video(video, "UC123")
    store.upsert_video(video, "UC123")
    store.upsert_comment(comment, "vid1")
    store.upsert_comment(comment, "vid1")
    store.close()

    conn = sqlite3.connect(db_path)
    assert conn.execute("SELECT COUNT(*) FROM channels").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM videos").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM comments").fetchone()[0] == 1
    conn.close()


def test_reply_parent_comment_id_is_stored(tmp_path):
    store = SQLiteStore(tmp_path / "test.sqlite3")
    store.upsert_channel(
        {
            "id": "UC123",
            "snippet": {},
            "contentDetails": {"relatedPlaylists": {"uploads": "UU123"}},
        }
    )
    store.upsert_video({"id": "vid1", "snippet": {}, "statistics": {}}, "UC123")
    store.upsert_comment({"id": "reply1", "snippet": {"textDisplay": "same here"}}, "vid1", "parent1")
    row = store.conn.execute("SELECT parent_comment_id FROM comments WHERE comment_id = 'reply1'").fetchone()
    assert row["parent_comment_id"] == "parent1"
    store.close()

