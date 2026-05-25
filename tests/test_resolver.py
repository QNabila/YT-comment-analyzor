import pytest

from yt_audience_report.fetch.resolver import ChannelInputError, parse_channel_input


@pytest.mark.parametrize(
    ("raw", "kind", "value"),
    [
        ("@creator", "handle", "creator"),
        ("https://www.youtube.com/@creator", "handle", "creator"),
        ("https://www.youtube.com/@creator/videos", "handle", "creator"),
        ("https://www.youtube.com/channel/UCabc12345678901234567", "channel_id", "UCabc12345678901234567"),
        ("UCabc12345678901234567", "channel_id", "UCabc12345678901234567"),
        ("https://www.youtube.com/user/legacyName", "username", "legacyName"),
    ],
)
def test_parse_channel_input(raw, kind, value):
    parsed = parse_channel_input(raw)
    assert parsed.kind == kind
    assert parsed.value == value


def test_rejects_ambiguous_custom_url():
    with pytest.raises(ChannelInputError, match="ambiguous"):
        parse_channel_input("https://www.youtube.com/c/custom-name")

