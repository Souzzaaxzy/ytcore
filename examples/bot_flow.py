"""Example: search a song, download the audio and the cover.

    python examples/bot_flow.py "daft punk instant crush"

Uses only ytcore (InnerTube) + ffmpeg. No yt-dlp.
"""

import os
import sys

from ytcore import YouTube

query = " ".join(sys.argv[1:]) or "daft punk instant crush"
out_dir = "downloads"

yt = YouTube()

print("Buscando:", query)
track = yt.search_one(query)
if track is None:
    raise SystemExit("nada encontrado")

print("=" * 60)
print("Título  :", track.title)
print("Canal   :", track.uploader)
print("Duração :", track.duration_str)
print("Thumb   :", track.thumbnail)
print("Áudio   :", track.audio_url and track.audio_url[:60] + "...")
for f in track.audio_formats:
    print(f"  itag={f.itag} {f.container} {f.codec} {f.kbps} kbps")

print("\nBaixando (ffmpeg direto do stream)...")
result = yt.fetch(track.id, out_dir=out_dir, fmt="mp3", bitrate="192k")
print("Áudio   :", result.audio_path, f"({os.path.getsize(result.audio_path)} bytes)")
print("Capa    :", result.cover_path)
print("=" * 60)
print("Pronto pra mandar no chat.")
