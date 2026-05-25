from __future__ import annotations

MOCK_PALETTE = {
    "ink": "#203B38",
    "deep_teal": "#31524C",
    "sage": "#6F9F92",
    "olive": "#8DA56A",
    "clay": "#D09B6B",
    "lavender": "#9F8FB4",
    "blue_gray": "#6D95AD",
    "cream": "#F6F3EE",
    "card": "#FFFDF8",
    "soft_panel": "#E8ECE6",
    "border": "#D9DED6",
    "muted": "#61726E",
    "high": "#B35C4B",
    "medium": "#B58A45",
    "low": "#5F8F83",
    "white": "#FFFFFF",
}


def palette_css_vars() -> str:
    return "\n".join(f"    --{name.replace('_', '-')}: {value};" for name, value in MOCK_PALETTE.items())
