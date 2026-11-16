"""Parsing helpers for InnerTube's deeply nested renderer payloads."""

from __future__ import annotations

import re
from typing import Iterable, Iterator, List, Optional

_VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")


def walk(node, key: str) -> Iterator[dict]:
    """Yield every value stored under ``key`` anywhere in a nested structure."""
    if isinstance(node, dict):
        for k, value in node.items():
            if k == key and isinstance(value, dict):
                yield value
            yield from walk(value, key)
    elif isinstance(node, list):
        for item in node:
            yield from walk(item, key)


def first(node, key: str) -> Optional[dict]:
    return next(walk(node, key), None)


def runs_text(node: Optional[dict]) -> Optional[str]:
    """Join a ``{"runs": [...]}`` / ``{"simpleText": ...}`` text object."""
    if not node:
        return None
    if "simpleText" in node:
        return node["simpleText"]
    runs = node.get("runs")
    if isinstance(runs, list):
        return "".join(r.get("text", "") for r in runs) or None
    return None


def parse_duration(text: Optional[str]) -> Optional[float]:
    """Turn ``"3:33"`` / ``"1:02:05"`` into seconds."""
    if not text:
        return None
    parts = text.split(":")
    try:
        nums = [int(p) for p in parts]
    except ValueError:
        return None
    seconds = 0
    for num in nums:
        seconds = seconds * 60 + num
    return float(seconds)


def best_thumbnail(thumbnails: Iterable[dict]) -> Optional[str]:
    """Pick the highest-resolution thumbnail URL."""
    items = [t for t in thumbnails if t.get("url")]
    if not items:
        return None
    items.sort(key=lambda t: (t.get("width") or 0) * (t.get("height") or 0))
    return items[-1]["url"]


def looks_like_video_id(value: str) -> bool:
    return bool(_VIDEO_ID.match(value.strip()))


def video_id_from_url(url: str) -> Optional[str]:
    """Extract a video id from a watch/youtu.be/shorts/embed URL."""
    url = url.strip()
    if looks_like_video_id(url):
        return url
    for pattern in (
        r"[?&]v=([A-Za-z0-9_-]{11})",
        r"youtu\.be/([A-Za-z0-9_-]{11})",
        r"/shorts/([A-Za-z0-9_-]{11})",
        r"/embed/([A-Za-z0-9_-]{11})",
        r"/live/([A-Za-z0-9_-]{11})",
    ):
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None
