"""
TTS generator — uses edge-tts (Microsoft Edge Read Aloud, free, no API key,
pure Python, runs on CPU) to create one MP3 per scene.

Each MP3's duration is also returned so the video assembler knows how long
to hold each panel.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import edge_tts

VOICE = "hi-IN-MadhurNeural"   # Hindi male voice — fits tense narration
RATE = "+8%"                   # slightly faster for urgency


async def _synthesize(text: str, out_path: Path) -> float:
    communicate = edge_tts.Communicate(text, VOICE, rate=RATE)
    await communicate.save(str(out_path))
    # Edge-tts MP3s don't expose duration directly; probe with mutagen.
    try:
        from mutagen.mp3 import MP3
        audio = MP3(str(out_path))
        return float(audio.info.length)
    except Exception:  # noqa: BLE001
        # Rough fallback: ~16 KB/s for this voice's bitrate
        return max(2.0, out_path.stat().st_size / 16000.0)


def generate_tts(story_path: Path, out_dir: Path) -> list[dict]:
    story = json.loads(story_path.read_text())
    out_dir.mkdir(parents=True, exist_ok=True)
    durations: list[dict] = []
    for i, scene in enumerate(story["scenes"]):
        mp3 = out_dir / f"scene_{i:02d}.mp3"
        if mp3.exists() and mp3.stat().st_size > 1000:
            print(f"[tts_gen] {mp3.name} exists, reusing")
        else:
            dur = asyncio.run(_synthesize(scene["narration"], mp3))
            print(f"[tts_gen] OK {mp3.name} ({dur:.1f}s)")
        # (re)compute duration for manifest
        from mutagen.mp3 import MP3
        try:
            dur = float(MP3(str(mp3)).info.length)
        except Exception:  # noqa: BLE001
            dur = max(2.0, mp3.stat().st_size / 16000.0)
        durations.append({"index": i, "file": str(mp3), "duration": dur})
    return durations


if __name__ == "__main__":
    story = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("story.json")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("audio")
    durations = generate_tts(story, out)
    Path("audio_manifest.json").write_text(json.dumps(durations, indent=2))
    print(json.dumps(durations, indent=2))
