from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from yt_audience_report.fetch.youtube_client import YouTubeClient


class ChannelInputError(ValueError):
    """Raised when a channel input cannot be resolved safely."""


@dataclass(frozen=True)
class ParsedChannelInput:
    kind: str
    value: str


def parse_channel_input(raw_input: str) -> ParsedChannelInput:
    value = raw_input.strip()
    if not value:
        raise ChannelInputError("Provide a YouTube channel handle or URL.")

    if value.startswith("@"):
        return ParsedChannelInput("handle", value.lstrip("@"))

    if value.startswith("UC") and len(value) >= 20:
        return ParsedChannelInput("channel_id", value)

    parsed = urlparse(value if "://" in value else f"https://{value}")
    host = parsed.netloc.lower().removeprefix("www.")
    if host not in {"youtube.com", "m.youtube.com"}:
        raise ChannelInputError("Use a youtube.com channel URL, @handle, or /channel/UC... URL.")

    parts = [part for part in parsed.path.split("/") if part]
    if not parts:
        raise ChannelInputError("Use a YouTube channel URL that includes a handle or channel ID.")

    first = parts[0]
    if first.startswith("@"):
        return ParsedChannelInput("handle", first.lstrip("@"))

    if first == "channel" and len(parts) >= 2:
        return ParsedChannelInput("channel_id", parts[1])

    if first == "user" and len(parts) >= 2:
        return ParsedChannelInput("username", parts[1])

    if first == "c" and len(parts) >= 2:
        raise ChannelInputError(
            "Custom /c/... URLs are ambiguous. Use the channel's @handle or /channel/UC... URL."
        )

    raise ChannelInputError("Unsupported YouTube channel URL. Use @handle or /channel/UC... URL.")


def resolve_channel(client: YouTubeClient, raw_input: str) -> dict:
    parsed = parse_channel_input(raw_input)
    if parsed.kind == "handle":
        channel = client.channels_by_handle(parsed.value)
    elif parsed.kind == "channel_id":
        channel = client.channels_by_id(parsed.value)
    elif parsed.kind == "username":
        channel = client.channels_by_username(parsed.value)
    else:
        raise ChannelInputError(f"Unsupported channel input type: {parsed.kind}")

    if not channel:
        raise ChannelInputError(f"No YouTube channel found for {raw_input!r}.")
    return channel

