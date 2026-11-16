"""InnerTube client definitions.

YouTube's web and mobile apps talk to ``youtubei/v1/*`` with a "client"
descriptor (name, version, API key, headers). Different clients expose
different data: the ``WEB`` client is good for search, while ``ANDROID_VR``
returns direct, un-ciphered audio URLs from the player endpoint.

These values are public - they ship inside the YouTube apps and the web page.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional

INNERTUBE_BASE = "https://www.youtube.com/youtubei/v1"

#: Public API key baked into the YouTube web page.
WEB_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"
#: Public API key used by the Android/VR clients.
ANDROID_KEY = "AIzaSyA8eiZmM1FaDVjRy-df2KTyQ_vz_yYM39w"


@dataclass
class Client:
    """One InnerTube client identity."""

    name: str
    version: str
    key: str
    user_agent: str
    #: numeric client id used in the ``X-YouTube-Client-Name`` header
    client_id: str
    extra: Dict[str, object] = field(default_factory=dict)

    def context(self, *, hl: str = "en", gl: str = "US") -> dict:
        client = {"clientName": self.name, "clientVersion": self.version, "hl": hl, "gl": gl}
        client.update(self.extra)
        return {
            "client": client,
            "user": {"lockedSafetyMode": False},
            "request": {"useSsl": True},
        }

    def headers(self) -> Dict[str, str]:
        return {
            "Content-Type": "application/json",
            "User-Agent": self.user_agent,
            "X-YouTube-Client-Name": self.client_id,
            "X-YouTube-Client-Version": self.version,
            "Origin": "https://www.youtube.com",
            "Accept-Language": "en-US,en;q=0.9",
        }


#: Web client - used for search and general metadata.
WEB = Client(
    name="WEB",
    version="2.20240726.00.00",
    key=WEB_KEY,
    client_id="1",
    user_agent=(
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
)

#: Android VR client - returns direct audio URLs from the player endpoint.
ANDROID_VR = Client(
    name="ANDROID_VR",
    version="1.60.19",
    key=ANDROID_KEY,
    client_id="28",
    user_agent="com.google.android.apps.youtube.vr.oculus/1.60.19 (Linux; U; Android 12; GB) gzip",
    extra={
        "androidSdkVersion": 32,
        "deviceMake": "Oculus",
        "deviceModel": "Quest 3",
        "osName": "Android",
        "osVersion": "12",
    },
)

#: Apple Vision Pro client - currently the most permissive for the player
#: endpoint: with a bootstrapped ``visitorData`` it returns direct audio URLs
#: where other clients answer LOGIN_REQUIRED.
VISIONOS = Client(
    name="VISIONOS",
    version="1.02",
    key=WEB_KEY,
    client_id="101",
    user_agent=(
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 15_7_3) AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/26.0 Safari/605.1.15"
    ),
    extra={
        "deviceMake": "Apple",
        "deviceModel": "RealityDevice17,1",
        "osName": "visionOS",
        "osVersion": "26.5.23O471",
    },
)

#: Fallback order for the player endpoint, best first.
PLAYER_CLIENTS = [VISIONOS, ANDROID_VR, WEB]
#: Client used for search / suggestions.
SEARCH_CLIENT = WEB


def client_by_name(name: str) -> Optional[Client]:
    for client in (WEB, ANDROID_VR, VISIONOS):
        if client.name == name:
            return client
    return None
