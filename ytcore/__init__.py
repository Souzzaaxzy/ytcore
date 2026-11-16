"""ytcore: a dependency-free YouTube client (InnerTube), no yt-dlp.

Talks directly to YouTube's InnerTube API with only the Python standard
library, and uses ffmpeg to produce audio files.

    from ytcore import YouTube

    yt = YouTube()
    track = yt.search_one("daft punk instant crush")
    print(track.title, track.duration_str, track.thumbnail)

    # direct audio stream URL (googlevideo)
    print(track.audio_url)

    # download to mp3 + cover
    result = yt.fetch(track.id, out_dir="downloads", fmt="mp3")
    print(result.audio_path, result.cover_path)

The ``VISIONOS`` InnerTube client is used for playback because, with a
bootstrapped visitor id, it returns direct audio URLs where other clients
answer LOGIN_REQUIRED. ``ANDROID_VR`` and ``WEB`` are the fallbacks.
"""

from __future__ import annotations

import os

from .client import InnerTube
from .clients import ANDROID_VR, VISIONOS, WEB, Client
from .download import Downloaded, Downloader, safe_name
from .errors import (
    DownloadError,
    FFmpegError,
    FFmpegNotFound,
    InnerTubeError,
    PlayerError,
    YtcoreError,
)
from .ffmpeg import FFmpeg, find_ffmpeg, find_ffprobe
from .models import Format, Thumbnail, Track
from .parse import parse_duration, video_id_from_url
from .transport import FakeTransport, UrllibTransport

__version__ = "0.1.0"


class YouTube:
    """High-level facade: search, inspect and download."""

    def __init__(
        self,
        transport=None,
        *,
        ffmpeg: FFmpeg | None = None,
        hl: str = "en",
        gl: str = "US",
        cookiefile: str | None = None,
    ) -> None:
        self.inner = InnerTube(transport, hl=hl, gl=gl, cookiefile=cookiefile)
        cookie = getattr(self.inner.transport, "cookie", "") if cookiefile else ""
        self.downloader = Downloader(ffmpeg, cookie=cookie)

    # -- reads -----------------------------------------------------------
    def search(self, query: str, *, limit: int = 10) -> list[Track]:
        return self.inner.search(query, limit=limit)

    def search_one(self, query: str, *, attempts: int = 3) -> Track | None:
        return self.inner.search_one(query, attempts=attempts)

    def get(self, target: str) -> Track:
        return self.inner.get(target)

    def resolve(self, query: str) -> Track:
        """Find a playable track for a query, trying several results."""
        return self.inner.resolve(query)

    def stream_url(self, target: str) -> str | None:
        return self.inner.stream_url(target)

    def thumbnail(self, target: str) -> str | None:
        return self.get(target).thumbnail

    # -- downloads -------------------------------------------------------
    def download(
        self,
        target: str,
        *,
        out_dir: str = ".",
        fmt: str = "mp3",
        bitrate: str = "192k",
        filename: str | None = None,
        normalize: bool = False,
        with_cover: bool = False,
    ) -> str:
        """Download a video's audio to ``out_dir`` and return the file path."""
        track = self.get(target)
        name = filename or safe_name(f"{track.uploader or ''} - {track.title}".strip(" -"))
        out = os.path.join(out_dir, f"{name}.{fmt}")
        self.downloader.stream_to_file(track, out, fmt=fmt, bitrate=bitrate, normalize=normalize)
        if with_cover:
            self.downloader.download_cover(track, out_dir)
        return out

    def fetch(
        self,
        query: str,
        *,
        out_dir: str = "downloads",
        fmt: str = "mp3",
        bitrate: str = "192k",
        with_cover: bool = True,
        filename: str | None = None,
    ) -> Downloaded:
        """Search if needed, then download the audio (and cover)."""
        track = None
        if video_id_from_url(query):
            try:
                track = self.get(query)
            except YtcoreError:
                track = None
        if track is None:
            track = self.inner.resolve(query)
        if track is None:
            raise DownloadError(f"nothing found for {query!r}")

        name = filename or safe_name(f"{track.uploader or ''} - {track.title}".strip(" -"))
        out = os.path.join(out_dir, f"{name}.{fmt}")
        self.downloader.stream_to_file(track, out, fmt=fmt, bitrate=bitrate)

        cover = None
        if with_cover:
            try:
                cover = self.downloader.download_cover(track, out_dir)
            except Exception:  # noqa: BLE001 - cover is optional
                cover = None

        return Downloaded(
            title=track.title,
            artist=track.uploader,
            duration=track.duration,
            audio_path=out,
            cover_path=cover,
            video_id=track.id,
            source_url=track.watch_url,
        )


__all__ = [
    "YouTube",
    "InnerTube",
    "Track",
    "Format",
    "Thumbnail",
    "Downloaded",
    "Downloader",
    "safe_name",
    "Client",
    "WEB",
    "ANDROID_VR",
    "VISIONOS",
    "FFmpeg",
    "find_ffmpeg",
    "find_ffprobe",
    "UrllibTransport",
    "FakeTransport",
    "parse_duration",
    "video_id_from_url",
    "YtcoreError",
    "InnerTubeError",
    "PlayerError",
    "DownloadError",
    "FFmpegError",
    "FFmpegNotFound",
    "__version__",
]
