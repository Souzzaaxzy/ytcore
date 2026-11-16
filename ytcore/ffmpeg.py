"""ffmpeg/ffprobe helpers: locate the binary and run conversions.

ffmpeg is looked up in order: the ``ffmpeg`` argument, ``$FFMPEG_BINARY``,
``ffmpeg`` on ``PATH``, then the static build bundled by ``imageio-ffmpeg``
(pip-installable, so it works without root).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional, Sequence

from .errors import FFmpegError, FFmpegNotFound


def _from_imageio() -> Optional[str]:
    try:
        import imageio_ffmpeg
    except ImportError:
        return None
    try:
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # noqa: BLE001
        return None


def find_ffmpeg(explicit: Optional[str] = None) -> str:
    for candidate in (explicit, os.environ.get("FFMPEG_BINARY"), shutil.which("ffmpeg"), _from_imageio()):
        if candidate and Path(candidate).exists():
            return candidate
    raise FFmpegNotFound(
        "ffmpeg not found; install it, set FFMPEG_BINARY, or `pip install imageio-ffmpeg`"
    )


def find_ffprobe(explicit: Optional[str] = None) -> Optional[str]:
    for candidate in (explicit, os.environ.get("FFPROBE_BINARY"), shutil.which("ffprobe")):
        if candidate and Path(candidate).exists():
            return candidate
    return None


class FFmpeg:
    """Thin wrapper around the ffmpeg/ffprobe binaries."""

    def __init__(self, ffmpeg: Optional[str] = None, ffprobe: Optional[str] = None) -> None:
        self.ffmpeg = find_ffmpeg(ffmpeg)
        self.ffprobe = find_ffprobe(ffprobe)

    def run(self, args: Sequence[str], *, timeout: float = 600.0) -> str:
        try:
            proc = subprocess.run(
                [self.ffmpeg, *args],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=timeout,
            )
        except FileNotFoundError as exc:
            raise FFmpegNotFound(f"ffmpeg binary not found: {self.ffmpeg}") from exc
        output = proc.stdout.decode("utf-8", errors="replace")
        if proc.returncode != 0:
            tail = "\n".join(output.strip().splitlines()[-12:])
            raise FFmpegError(f"ffmpeg failed (exit {proc.returncode}):\n{tail}")
        return output

    def convert(
        self,
        source: str,
        target: str,
        *,
        fmt: Optional[str] = None,
        bitrate: Optional[str] = None,
        sample_rate: Optional[int] = None,
        channels: Optional[int] = None,
        start: Optional[float] = None,
        duration: Optional[float] = None,
        normalize: bool = False,
        user_agent: Optional[str] = None,
        http_headers: Optional[dict] = None,
        extra_args: Sequence[str] = (),
    ) -> str:
        """Convert/extract audio from ``source`` (file or URL) into ``target``."""
        args: List[str] = ["-hide_banner", "-loglevel", "error", "-y"]
        if _is_url(source):
            headers = dict(http_headers or {})
            if user_agent:
                headers.setdefault("User-Agent", user_agent)
            if headers:
                blob = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
                args += ["-headers", blob]
        if start is not None:
            args += ["-ss", str(start)]
        args += ["-i", source]
        if duration is not None:
            args += ["-t", str(duration)]
        args += ["-vn"]
        if normalize:
            args += ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"]
        if sample_rate:
            args += ["-ar", str(sample_rate)]
        if channels:
            args += ["-ac", str(channels)]
        if bitrate:
            args += ["-b:a", bitrate]
        if fmt:
            args += ["-f", fmt]
        args += list(extra_args)
        args.append(target)
        self.run(args)
        return target

    def duration(self, path: str) -> Optional[float]:
        if self.ffprobe:
            proc = subprocess.run(
                [
                    self.ffprobe, "-v", "error",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    path,
                ],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            try:
                return float(proc.stdout.decode().strip())
            except (ValueError, AttributeError):
                return None
        import re

        proc = subprocess.run(
            [self.ffmpeg, "-hide_banner", "-i", path],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
        )
        match = re.search(rb"Duration: (\d+):(\d+):(\d+\.\d+)", proc.stdout)
        if match:
            h, m, s = (float(x) for x in match.groups())
            return h * 3600 + m * 60 + s
        return None


def _is_url(value: str) -> bool:
    return value.startswith("http://") or value.startswith("https://")
