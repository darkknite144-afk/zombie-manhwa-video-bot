"""
Story generator — calls Groq (OpenAI-compatible) to produce a Hinglish
zombie apocalypse manhwa-style 2-minute narration script broken into scenes.

Output JSON structure (story.json):
{
  "title": "...",
  "scenes": [
    {"narration": "...", "image_prompt": "..."},
    ...
  ]
}

Designed to run both locally and inside the GitHub Actions runner.
No GPU required — the LLM call happens server-side at Groq.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from openai import OpenAI

# --- Configuration ---------------------------------------------------------
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
GROQ_BASE_URL = "https://api.groq.com/openai/v1"

# Fallback model list — if the primary model 404s or is unavailable, try these.
# Groq periodically deprecates/renames models; this makes the pipeline resilient.
# Current production models as of Aug 2026: openai/gpt-oss-120b, openai/gpt-oss-20b
FALLBACK_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.6-27b",
]

# Number of scenes — tuned so total narration lands at ~2 minutes.
NUM_SCENES = int(os.environ.get("NUM_SCENES", "12"))

# A fixed seed topic keeps output reproducible enough to debug; override via env.
TOPIC = os.environ.get(
    "VIDEO_TOPIC",
    "zombie apocalypse survival manhwa — a lone survivor in a ruined Indian city",
)

SYSTEM_PROMPT = (
    "You are a master storyteller who writes gripping Hinglish narration "
    "for short YouTube Shorts-style videos in a manhwa / webtoon art style. "
    "You write ONLY in Hinglish (Hindi written in Roman letters, mixed with "
    "English words naturally as Indians speak). Narration is dramatic, tense, "
    "and second-person ('tu', 'tum') to put the viewer inside the story. "
    "Each scene must have: (1) a 1-2 sentence Hinglish narration, and "
    "(2) a detailed English image prompt for Pollinations.ai / Stable Diffusion "
    "describing the manhwa panel: characters, expression, pose, background, "
    "lighting, camera angle, art style keywords like 'manhwa panel, dramatic "
    "lighting, detailed line art, cinematic composition'. Keep characters "
    "consistent across scenes (same protagonist description). No gore that "
    "would be rejected — imply danger, show tension and atmosphere."
)


def _client() -> OpenAI:
    if not GROQ_API_KEY:
        raise SystemExit(
            "GROQ_API_KEY environment variable is not set. "
            "Create a free key at https://console.groq.com and add it as a "
            "GitHub repo secret named GROQ_API_KEY."
        )
    return OpenAI(api_key=GROQ_API_KEY, base_url=GROQ_BASE_URL)


def generate_story(out_path: Path) -> dict:
    """Generate the story JSON and write it to out_path."""
    client = _client()

    user_prompt = (
        f"Create a {NUM_SCENES}-scene 2-minute video script for the topic: "
        f"{TOPIC}\n\n"
        f"Return STRICT JSON only (no markdown fences) with this shape:\n"
        "{\n"
        '  "title": "short catchy Hinglish title",\n'
        '  "scenes": [\n'
        '    {"narration": "Hinglish narration line", '
        '"image_prompt": "detailed English SD prompt for the manhwa panel"},\n'
        "    ...\n"
        "  ]\n"
        "}\n"
        f"Exactly {NUM_SCENES} scenes. Each narration ~8-14 words so the total "
        "spoken duration is close to 2 minutes. Image prompts MUST end with: "
        "'manhwa panel, dramatic lighting, detailed line art, "
        "cinematic composition, high quality'."
    )

    # Try the primary model first, then fall back through FALLBACK_MODELS
    models_to_try = [GROQ_MODEL] + [m for m in FALLBACK_MODELS if m != GROQ_MODEL]
    last_err: Exception | None = None

    for model in models_to_try:
        print(f"[story_gen] Trying model: {model}")
        for attempt in range(1, 4):
            try:
                resp = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_prompt},
                    ],
                    temperature=0.8,
                    response_format={"type": "json_object"},
                    max_tokens=2048,
                )
                raw = resp.choices[0].message.content or ""
                story = json.loads(raw)
                if "scenes" not in story or not isinstance(story["scenes"], list):
                    raise ValueError("Missing 'scenes' array in LLM response")
                # Pad/trim to exactly NUM_SCENES
                scenes = story["scenes"][:NUM_SCENES]
                while len(scenes) < NUM_SCENES:
                    scenes.append(
                        {
                            "narration": "Aur tabhi, sab kuch badal gaya.",
                            "image_prompt": (
                                "lone survivor looking at burning Indian city skyline, "
                                "manhwa panel, dramatic lighting, detailed line art, "
                                "cinematic composition, high quality"
                            ),
                        }
                    )
                story["scenes"] = scenes
                out_path.write_text(json.dumps(story, ensure_ascii=False, indent=2))
                print(f"[story_gen] Wrote {len(scenes)} scenes to {out_path} (model: {model})")
                return story
            except Exception as exc:  # noqa: BLE001
                last_err = exc
                err_str = str(exc)
                # If model not found or decommissioned, skip to next model immediately
                if "model_not_found" in err_str or "does not exist" in err_str or "model_decommissioned" in err_str:
                    print(f"[story_gen] Model '{model}' not available, trying next...")
                    break
                # For other errors (rate limit, timeout), retry with backoff
                wait = 2 ** attempt
                print(f"[story_gen] attempt {attempt} failed: {exc}; retrying in {wait}s")
                time.sleep(wait)

    raise SystemExit(f"[story_gen] Failed after trying all models. Last error: {last_err}")


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("story.json")
    generate_story(out)
