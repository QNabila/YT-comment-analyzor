from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests


@dataclass
class YouTubeApiError(Exception):
    """Raised when the YouTube Data API returns an error response."""

    status_code: int
    reason: str
    message: str

    def __str__(self) -> str:
        return f"YouTube API error {self.status_code} ({self.reason}): {self.message}"


@dataclass
class YouTubeNetworkError(Exception):
    """Raised when the YouTube Data API cannot be reached."""

    resource: str
    message: str

    def __str__(self) -> str:
        return f"Could not reach YouTube API resource {self.resource!r}: {self.message}"


class YouTubeClient:
    """Small wrapper around the public YouTube Data API v3 HTTP endpoints."""

    BASE_URL = "https://www.googleapis.com/youtube/v3"

    def __init__(self, api_key: str, timeout_seconds: int = 30) -> None:
        if not api_key:
            raise ValueError("YOUTUBE_API_KEY is required")
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds

    def channels_by_handle(self, handle: str) -> dict[str, Any] | None:
        data = self._get(
            "channels",
            {
                "part": "snippet,contentDetails,statistics",
                "forHandle": handle.lstrip("@"),
                "maxResults": 1,
            },
        )
        return _first_item(data)

    def channels_by_id(self, channel_id: str) -> dict[str, Any] | None:
        data = self._get(
            "channels",
            {
                "part": "snippet,contentDetails,statistics",
                "id": channel_id,
                "maxResults": 1,
            },
        )
        return _first_item(data)

    def channels_by_username(self, username: str) -> dict[str, Any] | None:
        data = self._get(
            "channels",
            {
                "part": "snippet,contentDetails,statistics",
                "forUsername": username,
                "maxResults": 1,
            },
        )
        return _first_item(data)

    def playlist_items_page(
        self,
        playlist_id: str,
        max_results: int = 50,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        params = {
            "part": "snippet,contentDetails",
            "playlistId": playlist_id,
            "maxResults": max_results,
        }
        if page_token:
            params["pageToken"] = page_token
        return self._get("playlistItems", params)

    def videos_by_ids(self, video_ids: list[str]) -> list[dict[str, Any]]:
        if not video_ids:
            return []
        data = self._get(
            "videos",
            {
                "part": "snippet,statistics,contentDetails,status",
                "id": ",".join(video_ids),
                "maxResults": min(len(video_ids), 50),
            },
        )
        return data.get("items", [])

    def comment_threads_page(
        self,
        video_id: str,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        params = {
            "part": "snippet,replies",
            "videoId": video_id,
            "maxResults": 100,
            "order": "time",
            "textFormat": "plainText",
        }
        if page_token:
            params["pageToken"] = page_token
        return self._get("commentThreads", params)

    def replies_page(
        self,
        parent_id: str,
        page_token: str | None = None,
    ) -> dict[str, Any]:
        params = {
            "part": "snippet",
            "parentId": parent_id,
            "maxResults": 100,
            "textFormat": "plainText",
        }
        if page_token:
            params["pageToken"] = page_token
        return self._get("comments", params)

    def _get(self, resource: str, params: dict[str, Any]) -> dict[str, Any]:
        request_params = dict(params)
        request_params["key"] = self.api_key
        try:
            response = requests.get(
                f"{self.BASE_URL}/{resource}",
                params=request_params,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            raise YouTubeNetworkError(resource, "network or DNS request failed") from exc
        try:
            data = response.json()
        except ValueError:
            data = {}

        if response.status_code >= 400:
            error = data.get("error", {})
            errors = error.get("errors") or [{}]
            first_error = errors[0]
            reason = first_error.get("reason") or error.get("status") or "unknown"
            message = error.get("message") or response.text
            raise YouTubeApiError(response.status_code, reason, message)

        return data


def _first_item(data: dict[str, Any]) -> dict[str, Any] | None:
    items = data.get("items", [])
    if not items:
        return None
    return items[0]
