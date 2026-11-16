"""Errors raised by ytcore."""

from __future__ import annotations


class YtcoreError(Exception):
    """Base class for every ytcore error."""


class InnerTubeError(YtcoreError):
    """The InnerTube API returned an error or an unusable payload."""


class PlayerError(YtcoreError):
    """The player response did not yield a playable stream.

    ``status`` carries YouTube's ``playabilityStatus`` (e.g. ``LOGIN_REQUIRED``,
    ``UNPLAYABLE``, ``ERROR``) when available.
    """

    def __init__(self, message: str, *, status: str | None = None) -> None:
        self.status = status
        super().__init__(message)


class DownloadError(YtcoreError):
    """A stream could not be downloaded."""


class FFmpegError(YtcoreError):
    """An ffmpeg/ffprobe command failed."""


class FFmpegNotFound(FFmpegError):
    """ffmpeg could not be located."""
