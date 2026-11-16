"""The InnerTube client: search, metadata and player responses.

Talks straight to ``youtubei/v1/*`` - no yt-dlp, no external extractor. The
``ANDROID_VR`` client is used for the player endpoint because it returns
direct audio URLs (no signature cipher, no proof-of-origin token).
"""

from __future__ import annotations

from typing import List, Optional

from .clients import ANDROID_VR, INNERTUBE_BASE, PLAYER_CLIENTS, SEARCH_CLIENT, WEB, Client
from .errors import InnerTubeError, PlayerError
from .models import Format, Thumbnail, Track
from .parse import (
    best_thumbnail,
    first,
    parse_duration,
    runs_text,
    video_id_from_url,
    walk,
)
from .transport import Transport, UrllibTransport


class InnerTube:
    """Minimal, dependency-free YouTube InnerTube client."""

    def __init__(
        self,
        transport: Optional[Transport] = None,
        *,
        hl: str = "en",
        gl: str = "US",
        bootstrap: bool = True,
        cookiefile: Optional[str] = None,
    ) -> None:
        self.transport: Transport = transport or UrllibTransport(cookiefile=cookiefile)
        self.hl = hl
        self.gl = gl
        self._bootstrapped = False
        self._bootstrap = bootstrap
        #: When a player response comes back LOGIN_REQUIRED, how many extra
        #: search results to try before giving up.
        self.result_fallbacks = 4

    # -- session bootstrap ----------------------------------------------
    def bootstrap_session(self) -> None:
        """Visit the homepage once to collect cookies and a ``visitorData``.

        YouTube hands out ``VISITOR_INFO1_LIVE`` and a visitor id here; sending
        them on later calls makes far fewer requests come back
        ``LOGIN_REQUIRED``.
        """
        if self._bootstrapped or not self._bootstrap:
            return
        self._bootstrapped = True
        try:
            self.transport.get(
                "https://www.youtube.com/",
                {"User-Agent": SEARCH_CLIENT.user_agent, "Accept-Language": "en-US,en;q=0.9"},
            )
        except Exception:  # noqa: BLE001 - bootstrap is best-effort
            pass

    def _visitor_data(self) -> Optional[str]:
        return getattr(self.transport, "visitor_data", None)

    # -- low level -------------------------------------------------------
    def _post(self, endpoint: str, payload: dict, client: Client) -> dict:
        self.bootstrap_session()
        url = f"{INNERTUBE_BASE}/{endpoint}?key={client.key}&prettyPrint=false"
        body = dict(payload)
        context = client.context(hl=self.hl, gl=self.gl)
        visitor = self._visitor_data()
        if visitor:
            context["client"]["visitorData"] = visitor
        body.setdefault("context", context)
        headers = client.headers()
        if visitor:
            headers["X-Goog-Visitor-Id"] = visitor
        resp = self.transport.post_json(url, body, headers)
        if resp.status >= 400:
            raise InnerTubeError(f"{endpoint} returned HTTP {resp.status}: {resp.text[:200]}")
        data = resp.json()
        if not isinstance(data, dict):
            raise InnerTubeError(f"{endpoint} returned a non-JSON payload")
        return data

    # -- search ----------------------------------------------------------
    def search(self, query: str, *, limit: int = 10) -> List[Track]:
        """Search YouTube and return up to ``limit`` videos."""
        data = self._post("search", {"query": query}, SEARCH_CLIENT)
        tracks: List[Track] = []
        for renderer in walk(data, "videoRenderer"):
            track = _track_from_renderer(renderer)
            if track:
                tracks.append(track)
            if len(tracks) >= limit:
                break
        return tracks

    def search_one(self, query: str, *, attempts: int = 3) -> Optional[Track]:
        results = self.search(query, limit=max(1, attempts))
        return results[0] if results else None

    # -- player ----------------------------------------------------------
    def player(self, video_id: str, *, client: Optional[Client] = None) -> dict:
        """Raw player response for a video id."""
        client = client or ANDROID_VR
        return self._post(
            "player",
            {
                "videoId": video_id,
                "contentCheckOk": True,
                "racyCheckOk": True,
            },
            client,
        )

    def get(self, target: str) -> Track:
        """Full metadata for a video id or URL, including playable formats."""
        video_id = video_id_from_url(target)
        if not video_id:
            raise PlayerError(f"could not read a video id from {target!r}")

        last_status = None
        for client in PLAYER_CLIENTS:
            data = self.player(video_id, client=client)
            status = (data.get("playabilityStatus") or {}).get("status")
            last_status = status
            formats = _formats_from_player(data)
            if formats:
                return _track_from_player(data, video_id, formats)
            # LOGIN_REQUIRED / UNPLAYABLE -> try the next client
        raise PlayerError(
            f"no playable formats for {video_id} (status={last_status})",
            status=last_status,
        )

    def resolve(self, query: str, *, attempts: Optional[int] = None) -> Track:
        """Find a *playable* track for ``query``.

        Searches, then tries results in order until one yields audio. This
        handles the common case where the top hit is region-blocked or taken
        down (``UNPLAYABLE``).
        """
        if video_id_from_url(query):
            try:
                return self.get(query)
            except PlayerError:
                pass  # fall through to search

        limit = attempts or self.result_fallbacks + 1
        results = self.search(query, limit=limit)
        last_error: Optional[PlayerError] = None
        for result in results:
            try:
                return self.get(result.id)
            except PlayerError as exc:
                last_error = exc
                continue
        if last_error is not None:
            raise PlayerError(
                f"no playable result for {query!r} ({len(results)} tried, "
                f"last status={last_error.status})",
                status=last_error.status,
            )
        raise PlayerError(f"no results for {query!r}")

    def formats(self, target: str) -> List[Format]:
        return self.get(target).formats

    def audio_formats(self, target: str) -> List[Format]:
        return self.get(target).audio_formats

    def stream_url(self, target: str) -> Optional[str]:
        """Direct audio stream URL (googlevideo) for a video."""
        track = self.get(target)
        return track.audio_url


# -- parsing -------------------------------------------------------------
def _track_from_renderer(renderer: dict) -> Optional[Track]:
    video_id = renderer.get("videoId")
    if not video_id:
        return None
    thumbs = [
        Thumbnail(url=t["url"], width=t.get("width"), height=t.get("height"))
        for t in ((renderer.get("thumbnail") or {}).get("thumbnails") or [])
        if t.get("url")
    ]
    return Track(
        id=video_id,
        title=runs_text(renderer.get("title")) or video_id,
        duration=parse_duration((renderer.get("lengthText") or {}).get("simpleText")),
        uploader=runs_text(renderer.get("ownerText")) or runs_text(renderer.get("longBylineText")),
        thumbnail=best_thumbnail((renderer.get("thumbnail") or {}).get("thumbnails") or []),
        thumbnails=thumbs,
    )


def _formats_from_player(data: dict) -> List[Format]:
    streaming = data.get("streamingData") or {}
    raw = list(streaming.get("formats") or []) + list(streaming.get("adaptiveFormats") or [])
    return [Format.from_dict(f) for f in raw if f.get("url")]


def _track_from_player(data: dict, video_id: str, formats: List[Format]) -> Track:
    details = data.get("videoDetails") or {}
    streaming = data.get("streamingData") or {}
    thumbs = [
        Thumbnail(url=t["url"], width=t.get("width"), height=t.get("height"))
        for t in ((details.get("thumbnail") or {}).get("thumbnails") or [])
        if t.get("url")
    ]
    return Track(
        id=video_id,
        title=details.get("title") or video_id,
        duration=float(details["lengthSeconds"]) if details.get("lengthSeconds") else None,
        uploader=details.get("author"),
        thumbnail=best_thumbnail((details.get("thumbnail") or {}).get("thumbnails") or []),
        thumbnails=thumbs,
        description=details.get("shortDescription"),
        view_count=int(details["viewCount"]) if details.get("viewCount") else None,
        is_live=bool(details.get("isLiveContent")),
        formats=formats,
        hls_url=streaming.get("hlsManifestUrl"),
    )
