"""Downloading and converting YouTube audio.

Two paths, both feeding ffmpeg:

* :meth:`Downloader.stream_to_file` - ffmpeg reads the googlevideo URL
  directly (fastest, no intermediate file);
* :meth:`Downloader.download_bytes` - the stream is fetched with urllib and
  written to disk, for cases where ffmpeg cannot reach the URL.

YouTube's CDN requires the same client headers the InnerTube call used, so the
``ANDROID_VR`` user agent is sent on both paths.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Optional
from urllib.request import Request, urlopen

from .clients import ANDROID_VR
from .errors import DownloadError
from .ffmpeg import FFmpeg
from .models import Track


@dataclass
class Downloaded:
    """Result of a download: the audio file plus its cover."""

    title: str
    artist: Optional[str]
    duration: Optional[float]
    audio_path: str
    cover_path: Optional[str]
    video_id: str
    source_url: str


def safe_name(text: str, max_len: int = 80) -> str:
    text = re.sub(r"[^\w\s.-]", "", text, flags=re.UNICODE).strip()
    text = re.sub(r"\s+", "_", text)
    return text[:max_len] or "audio"


class Downloader:
    def __init__(self, ffmpeg: Optional[FFmpeg] = None, *, user_agent: Optional[str] = None) -> None:
        self._ffmpeg = ffmpeg
        self.user_agent = user_agent or ANDROID_VR.user_agent

    @property
    def ffmpeg(self) -> FFmpeg:
        if self._ffmpeg is None:
            self._ffmpeg = FFmpeg()
        return self._ffmpeg

    def stream_to_file(
        self,
        track: Track,
        out_path: str,
        *,
        fmt: Optional[str] = None,
        bitrate: str = "192k",
        duration: Optional[float] = None,
        start: Optional[float] = None,
        normalize: bool = False,
    ) -> str:
        """Have ffmpeg pull the audio straight from the stream URL."""
        best = track.best_audio()
        if best is None:
            raise DownloadError(f"no audio stream for {track.id}")
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        return self.ffmpeg.convert(
            best.url,
            out_path,
            fmt=fmt,
            bitrate=bitrate,
            duration=duration,
            start=start,
            normalize=normalize,
            user_agent=self.user_agent,
        )

    def download_bytes(self, track: Track, out_path: str, *, chunk_size: int = 1 << 16) -> str:
        """Fetch the raw audio stream with urllib and write it to ``out_path``."""
        best = track.best_audio()
        if best is None:
            raise DownloadError(f"no audio stream for {track.id}")
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        req = Request(best.url, headers={"User-Agent": self.user_agent})
        try:
            with urlopen(req, timeout=60) as resp, open(out_path, "wb") as fh:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    fh.write(chunk)
        except Exception as exc:  # noqa: BLE001
            raise DownloadError(f"could not download stream for {track.id}: {exc}") from exc
        if not os.path.exists(out_path) or os.path.getsize(out_path) == 0:
            raise DownloadError(f"download produced no data for {track.id}")
        return out_path

    def download_cover(self, track: Track, out_dir: str, *, width: Optional[int] = None) -> Optional[str]:
        """Save the video thumbnail as a cover image."""
        if not track.thumbnail:
            return None
        os.makedirs(out_dir, exist_ok=True)
        ext = "webp" if ".webp" in track.thumbnail else "jpg"
        out = os.path.join(out_dir, f"{track.id}.{ext}")
        req = Request(track.thumbnail, headers={"User-Agent": self.user_agent})
        with urlopen(req, timeout=30) as resp, open(out, "wb") as fh:
            fh.write(resp.read())
        return out
