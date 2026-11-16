"""Offline tests for ytcore.

A fake transport stands in for the network; parsing, model logic, URL
building and the ffmpeg wrapper are the real code.
"""

from __future__ import annotations

import os

import pytest
from ytcore import (
    ANDROID_VR,
    WEB,
    DownloadError,
    FFmpeg,
    FFmpegNotFound,
    Format,
    InnerTube,
    PlayerError,
    Track,
    YouTube,
)
from ytcore.parse import best_thumbnail, parse_duration, runs_text, video_id_from_url
from ytcore.transport import FakeTransport

SEARCH_PAYLOAD = {
    "contents": {
        "twoColumnSearchResultsRenderer": {
            "primaryContents": {
                "sectionListRenderer": {
                    "contents": [
                        {
                            "itemSectionRenderer": {
                                "contents": [
                                    {
                                        "videoRenderer": {
                                            "videoId": "dQw4w9WgXcQ",
                                            "title": {"runs": [{"text": "Rick Astley - Never Gonna Give You Up"}]},
                                            "ownerText": {"runs": [{"text": "Rick Astley"}]},
                                            "lengthText": {"simpleText": "3:33"},
                                            "thumbnail": {
                                                "thumbnails": [
                                                    {"url": "https://i.ytimg.com/small.jpg", "width": 120, "height": 90},
                                                    {"url": "https://i.ytimg.com/big.jpg", "width": 480, "height": 360},
                                                ]
                                            },
                                        }
                                    }
                                ]
                            }
                        }
                    ]
                }
            }
        }
    }
}

PLAYER_PAYLOAD = {
    "playabilityStatus": {"status": "OK"},
    "videoDetails": {
        "videoId": "dQw4w9WgXcQ",
        "title": "Rick Astley - Never Gonna Give You Up",
        "author": "Rick Astley",
        "lengthSeconds": "213",
        "viewCount": "1500000000",
        "isLiveContent": False,
        "thumbnail": {"thumbnails": [{"url": "https://i.ytimg.com/vi/x/sd.jpg", "width": 640, "height": 480}]},
    },
    "streamingData": {
        "formats": [{"itag": 18, "url": "https://cdn/av", "mimeType": "video/mp4; codecs=\"avc1\"", "bitrate": 500000}],
        "adaptiveFormats": [
            {"itag": 140, "url": "https://cdn/a140", "mimeType": "audio/mp4; codecs=\"mp4a.40.2\"", "bitrate": 130677},
            {"itag": 251, "url": "https://cdn/a251", "mimeType": "audio/webm; codecs=\"opus\"", "bitrate": 136544},
        ],
    },
}


# -- parsing helpers -----------------------------------------------------
def test_parse_duration():
    assert parse_duration("3:33") == 213
    assert parse_duration("1:02:05") == 3725
    assert parse_duration("0:07") == 7
    assert parse_duration(None) is None
    assert parse_duration("bogus") is None


def test_runs_text():
    assert runs_text({"runs": [{"text": "a"}, {"text": "b"}]}) == "ab"
    assert runs_text({"simpleText": "hi"}) == "hi"
    assert runs_text(None) is None


def test_best_thumbnail():
    thumbs = [{"url": "a", "width": 10, "height": 10}, {"url": "b", "width": 100, "height": 100}]
    assert best_thumbnail(thumbs) == "b"
    assert best_thumbnail([]) is None


def test_video_id_from_url():
    assert video_id_from_url("dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert video_id_from_url("https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=1") == "dQw4w9WgXcQ"
    assert video_id_from_url("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert video_id_from_url("https://www.youtube.com/shorts/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert video_id_from_url("not a url") is None


# -- Format / Track ------------------------------------------------------
def test_format_parsing():
    f = Format.from_dict(
        {"itag": 251, "url": "https://cdn/x", "mimeType": "audio/webm; codecs=\"opus\"", "bitrate": 136544}
    )
    assert f.itag == 251
    assert f.is_audio is True
    assert f.codec == "opus"
    assert f.container == "webm"
    assert f.kbps == 136.5


def test_track_best_audio():
    t = Track(id="x", title="t", formats=[
        Format.from_dict({"itag": 140, "url": "a", "mimeType": "audio/mp4", "bitrate": 130000}),
        Format.from_dict({"itag": 251, "url": "b", "mimeType": "audio/webm", "bitrate": 136000}),
        Format.from_dict({"itag": 18, "url": "c", "mimeType": "video/mp4", "bitrate": 500000}),
    ])
    assert t.best_audio().itag == 251
    assert t.audio_url == "b"
    assert len(t.audio_formats) == 2


def test_track_duration_str():
    assert Track(id="x", title="t", duration=213).duration_str == "3:33"
    assert Track(id="x", title="t", duration=3725).duration_str == "1:02:05"


# -- InnerTube -----------------------------------------------------------
def test_search_parses_renderers():
    ft = FakeTransport({"search": SEARCH_PAYLOAD})
    itu = InnerTube(ft)
    results = itu.search("rick", limit=5)
    assert len(results) == 1
    t = results[0]
    assert t.id == "dQw4w9WgXcQ"
    assert t.uploader == "Rick Astley"
    assert t.duration == 213
    assert t.thumbnail == "https://i.ytimg.com/big.jpg"
    # request went to the search endpoint with the WEB client
    assert "search" in ft.calls[0].url
    assert ft.calls[0].payload["query"] == "rick"
    assert ft.calls[0].headers["X-YouTube-Client-Name"] == "1"


def test_get_builds_track_from_player():
    ft = FakeTransport({"player": PLAYER_PAYLOAD})
    itu = InnerTube(ft)
    track = itu.get("dQw4w9WgXcQ")
    assert track.title.startswith("Rick Astley")
    assert track.view_count == 1500000000
    assert len(track.audio_formats) == 2
    assert track.audio_url == "https://cdn/a251"
    # player call used the ANDROID_VR client
    assert ft.calls[0].headers["X-YouTube-Client-Name"] == "28"


def test_get_falls_back_to_next_client(monkeypatch):
    calls = {"n": 0}

    def handler(call):
        calls["n"] += 1
        if calls["n"] == 1:
            return {"playabilityStatus": {"status": "LOGIN_REQUIRED"}, "streamingData": {}}
        return PLAYER_PAYLOAD

    ft = FakeTransport({"player": handler})
    itu = InnerTube(ft)
    track = itu.get("dQw4w9WgXcQ")
    assert track.audio_formats
    assert calls["n"] == 2  # tried ANDROID_VR, then WEB


def test_get_raises_when_no_formats():
    ft = FakeTransport({"player": {"playabilityStatus": {"status": "UNPLAYABLE"}, "streamingData": {}}})
    itu = InnerTube(ft)
    with pytest.raises(PlayerError) as exc:
        itu.get("dQw4w9WgXcQ")
    assert exc.value.status in ("UNPLAYABLE", "LOGIN_REQUIRED")


def test_stream_url():
    ft = FakeTransport({"player": PLAYER_PAYLOAD})
    assert InnerTube(ft).stream_url("dQw4w9WgXcQ") == "https://cdn/a251"


def test_youtube_facade_search():
    ft = FakeTransport({"search": SEARCH_PAYLOAD})
    yt = YouTube(transport=ft)
    assert yt.search("rick")[0].id == "dQw4w9WgXcQ"


def test_download_raises_without_stream():
    ft = FakeTransport({"player": {"playabilityStatus": {"status": "OK"}, "streamingData": {}}})
    yt = YouTube(transport=ft)
    with pytest.raises(DownloadError):
        yt.downloader.stream_to_file(Track(id="x", title="t"), "/tmp/none.mp3")


# -- ffmpeg --------------------------------------------------------------
def test_find_ffmpeg_missing(monkeypatch):
    import ytcore.ffmpeg as mod

    monkeypatch.setattr(mod.shutil, "which", lambda _: None)
    monkeypatch.setattr(mod, "_from_imageio", lambda: None)
    monkeypatch.delenv("FFMPEG_BINARY", raising=False)
    with pytest.raises(FFmpegNotFound):
        mod.find_ffmpeg()


def test_convert_sends_user_agent_for_urls(tmp_path, monkeypatch):
    ff = FFmpeg.__new__(FFmpeg)
    ff.ffmpeg = "/fake/ffmpeg"
    ff.ffprobe = None
    captured = {}
    monkeypatch.setattr(ff, "run", lambda args, timeout=600.0: captured.setdefault("args", args) or "")
    ff.convert("https://cdn/audio", str(tmp_path / "o.mp3"), fmt="mp3", user_agent="UA/1")
    assert "-user_agent" in captured["args"]
    assert captured["args"][captured["args"].index("-user_agent") + 1] == "UA/1"


def test_convert_omits_user_agent_for_files(tmp_path, monkeypatch):
    ff = FFmpeg.__new__(FFmpeg)
    ff.ffmpeg = "/fake/ffmpeg"
    ff.ffprobe = None
    captured = {}
    monkeypatch.setattr(ff, "run", lambda args, timeout=600.0: captured.setdefault("args", args) or "")
    ff.convert(str(tmp_path / "in.wav"), str(tmp_path / "o.mp3"), fmt="mp3", user_agent="UA/1")
    assert "-user_agent" not in captured["args"]


def test_convert_end_to_end(tmp_path):
    """Really run ffmpeg: tone -> mp3, then read its duration."""
    ff = FFmpeg()
    src = str(tmp_path / "tone.wav")
    ff.run(["-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "sine=frequency=440:duration=2", src])
    out = str(tmp_path / "tone.mp3")
    ff.convert(src, out, fmt="mp3", bitrate="128k")
    assert os.path.exists(out) and os.path.getsize(out) > 0
    assert 1.5 < (ff.duration(out) or 0) < 2.5


# -- clients -------------------------------------------------------------
def test_client_context_and_headers():
    ctx = ANDROID_VR.context()
    assert ctx["client"]["clientName"] == "ANDROID_VR"
    assert ctx["client"]["deviceModel"] == "Quest 3"
    headers = ANDROID_VR.headers()
    assert headers["X-YouTube-Client-Name"] == "28"
    assert WEB.headers()["X-YouTube-Client-Name"] == "1"
