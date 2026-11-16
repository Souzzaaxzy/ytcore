"""Data models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Thumbnail:
    url: str
    width: Optional[int] = None
    height: Optional[int] = None

    @property
    def resolution(self) -> Optional[str]:
        if self.width and self.height:
            return f"{self.width}x{self.height}"
        return None


@dataclass
class Format:
    """One audio/video stream offered by the player."""

    itag: int
    url: str
    mime_type: str
    bitrate: int = 0
    content_length: Optional[int] = None
    quality: Optional[str] = None

    @property
    def is_audio(self) -> bool:
        return self.mime_type.startswith("audio/")

    @property
    def codec(self) -> Optional[str]:
        if "codecs=" in self.mime_type:
            return self.mime_type.split("codecs=", 1)[1].strip('"')
        return None

    @property
    def container(self) -> Optional[str]:
        if "/" in self.mime_type:
            return self.mime_type.split("/", 1)[1].split(";", 1)[0]
        return None

    @property
    def kbps(self) -> Optional[float]:
        return round(self.bitrate / 1000, 1) if self.bitrate else None

    @classmethod
    def from_dict(cls, data: dict) -> "Format":
        return cls(
            itag=int(data.get("itag", 0)),
            url=data.get("url", ""),
            mime_type=data.get("mimeType", ""),
            bitrate=int(data.get("bitrate") or 0),
            content_length=int(data["contentLength"]) if data.get("contentLength") else None,
            quality=data.get("audioQuality") or data.get("quality"),
        )


@dataclass
class Track:
    """A search result / video with the fields a bot needs."""

    id: str
    title: str
    duration: Optional[float] = None
    uploader: Optional[str] = None
    thumbnail: Optional[str] = None
    thumbnails: List[Thumbnail] = field(default_factory=list)
    description: Optional[str] = None
    view_count: Optional[int] = None
    is_live: bool = False
    formats: List[Format] = field(default_factory=list)
    #: HLS manifest URL. Unlike the direct googlevideo URLs, it does not need
    #: the ``n`` parameter that a JavaScript challenge would produce.
    hls_url: Optional[str] = None

    @property
    def duration_str(self) -> str:
        if not self.duration:
            return "0:00"
        total = int(self.duration)
        hours, rem = divmod(total, 3600)
        minutes, seconds = divmod(rem, 60)
        if hours:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        return f"{minutes}:{seconds:02d}"

    @property
    def watch_url(self) -> str:
        return f"https://www.youtube.com/watch?v={self.id}"

    @property
    def embed_url(self) -> str:
        return f"https://www.youtube.com/embed/{self.id}"

    @property
    def audio_formats(self) -> List[Format]:
        return [f for f in self.formats if f.is_audio]

    def best_audio(self) -> Optional[Format]:
        """Highest-bitrate audio-only stream."""
        audio = self.audio_formats
        if not audio:
            return None
        return max(audio, key=lambda f: f.bitrate)

    @property
    def audio_url(self) -> Optional[str]:
        best = self.best_audio()
        return best.url if best else None
