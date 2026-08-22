#!/usr/bin/env python3
"""
Main orchestrator — runs the full pipeline in order:
  1. Generate story (Groq LLM)
  2. Generate images (Pollinations.ai)
  3. Generate TTS audio (edge-tts)
  4. Assemble final video (MoviePy)

Usage: python main.py [--output out.mp4]

Environment variables:
  GROQ_API_KEY   (required) — free key from https://console.groq.com
  GROQ_MODEL     (optional) — default llama-3.1-8b-instant
  NUM_SCENES     (optional) — default 12
  VIDEO_TOPIC    (optional) — default zombie survival theme
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Ensure local script imports work regardless of CWD
sys.path.insert(0, str(Path(__file__).parent))

from story_gen import generate_story
from image_gen import generate_images
from tts_gen import generate_tts
from video_build import build_video


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate a 2-min manhwa video")
    parser.add_argument("--output", default="output/final_video.mp4",
                        help="Output video path")
    parser.add_argument("--workdir", default=".",
                        help="Working directory for intermediate files")
    args = parser.parse_args()

    work = Path(args.workdir).resolve()
    work.mkdir(parents=True, exist_ok=True)

    story_path = work / "story.json"
    images_dir = work / "images"
    audio_dir = work / "audio"
    out_path = Path(args.output).resolve()

    print("=" * 60)
    print("  ZOMBIE MANHWA VIDEO GENERATOR")
    print("=" * 60)

    # Step 1 — Story
    print("\n[1/4] Generating story via Groq LLM...")
    generate_story(story_path)
    story = json.loads(story_path.read_text())
    print(f"      Title: {story.get('title', '?')}")
    print(f"      Scenes: {len(story['scenes'])}")

    # Step 2 — Images
    print("\n[2/4] Generating manhwa panels via Pollinations.ai...")
    generate_images(story_path, images_dir)

    # Step 3 — TTS
    print("\n[3/4] Generating narration audio via edge-tts...")
    generate_tts(story_path, audio_dir)

    # Step 4 — Video
    print("\n[4/4] Assembling final video via MoviePy...")
    build_video(story_path, images_dir, audio_dir, out_path)

    print("\n" + "=" * 60)
    print(f"  DONE! Video saved to: {out_path}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
