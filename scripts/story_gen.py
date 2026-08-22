"""
Story generator — calls Groq (OpenAI-compatible) to produce a Hinglish
zombie apocalypse manhwa-style 2-minute narration script broken into scenes.

Uses openai/gpt-oss-120b (current Groq production model) with fallback chain.
Story has a proper narrative arc: setup → rising action → climax → resolution.
Image prompts are tuned for Solo Leveling / high-quality webtoon art style.

Output JSON structure (story.json):
{
  "title": "...",
  "scenes": [
    {"narration": "...", "image_prompt": "..."},
    ...
  ]
}
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

# Fallback model list — Groq periodically deprecates models.
FALLBACK_MODELS = [
    "openai/gpt-oss-120b",
    "openai/gpt-oss-20b",
    "qwen/qwen3.6-27b",
]

NUM_SCENES = int(os.environ.get("NUM_SCENES", "12"))

TOPIC = os.environ.get(
    "VIDEO_TOPIC",
    "zombie apocalypse survival manhwa — a lone survivor in a ruined Indian city",
)

SYSTEM_PROMPT = (
    "You are a master storyteller who writes gripping Hinglish narration "
    "for short YouTube videos in a Solo Leveling / webtoon manhwa art style. "
    "You write ONLY in Hinglish (Hindi in Roman letters, mixed with English "
    "naturally as Indians speak). Narration is dramatic, tense, second-person "
    "('tu', 'tum') to put the viewer inside the story.\n\n"
    "CRITICAL — STORYTELLING RULES:\n"
    "- The story MUST have a proper narrative arc: SETUP (world + character intro) "
    "→ RISING ACTION (danger escalates) → CLIMAX (big confrontation/twist) → "
    "RESOLUTION (aftermath + cliffhanger for next episode).\n"
    "- First 2-3 scenes: establish the world, the protagonist, the threat. "
    "Make the viewer CARE about the character before the action starts.\n"
    "- Middle scenes: escalate danger. The protagonist faces growing challenges. "
    "Show fear, determination, loss, hope.\n"
    "- Last 2-3 scenes: climactic confrontation + aftermath. End with a "
    "cliffhanger or emotional beat that makes viewers want part 2.\n"
    "- Each scene's narration should flow into the next like a continuous story, "
    "NOT random disconnected sentences.\n\n"
    "IMAGE PROMPT RULES:\n"
    "- Each image_prompt MUST be a detailed English description for generating "
    "a Solo Leveling quality manhwa panel.\n"
    "- Specify: character appearance (consistent across all scenes — same hair, "
    "clothing, build), facial expression, body pose, action, background setting, "
    "lighting (dramatic, moody, etc.), camera angle (close-up, wide shot, etc.).\n"
    "- End EVERY image_prompt with exactly: "
    "'solo leveling manhwa style, high detail, clean line art, dramatic shading, "
    "vivid colors, cinematic composition, webtoon panel, masterpiece quality'.\n"
    "- Keep the protagonist description IDENTICAL in every scene (same clothes, "
    "same hair, same scars/features) for visual consistency.\n"
    "- NEVER describe gore or explicit violence. Show tension through atmosphere, "
    "expressions, shadows, silhouettes — not blood."
)

USER_PROMPT_TEMPLATE = (
    "Create a {n}-scene 2-minute video script for: {topic}\n\n"
    "STORY ARC REQUIREMENT:\n"
    "- Scenes 1-3: SETUP — establish the fallen city, introduce the protagonist "
    "(give them a name and distinct appearance), show the zombie threat.\n"
    "- Scenes 4-{mid}: RISING ACTION — the survivor faces escalating danger. "
    "Show their fear, their resourcefulness, encounters with zombies or other survivors.\n"
    "- Scenes {mid+1}-{n-1}: CLIMAX — a major confrontation or turning point. "
    "Highest tension, a decision that changes everything.\n"
    "- Scene {n}: RESOLUTION + CLIFFHANGER — aftermath, the survivor's emotional "
    "state, a hook for the next episode.\n\n"
    "Return STRICT JSON only (no markdown fences):\n"
    "{{\n"
    '  "title": "catchy Hinglish title (max 6 words)",\n'
    '  "protagonist": "detailed English description of the main character '
    "(appearance, clothing, weapon, expression — used in ALL image prompts)\",\n"
    '  "scenes": [\n'
    '    {{"narration": "Hinglish narration (8-14 words, flows into next scene)", '
    '"image_prompt": "detailed English prompt describing THIS scene\'s manhwa panel '
    "using the protagonist description, background, lighting, action. End with: "
    "solo leveling manhwa style, high detail, clean line art, dramatic shading, "
    "vivid colors, cinematic composition, webtoon panel, masterpiece quality\"}}\n'
    "    ...\n"
    "  ]\n"
    "}}\n\n"
    "Exactly {n} scenes. Each narration must connect to the previous and next "
    "scene like chapters of one story — NOT random disconnected sentences. "
    "The narration should make the viewer feel they are watching a real story unfold."
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

    mid = max(4, NUM_SCENES - 3)
    user_prompt = USER_PROMPT_TEMPLATE.format(
        n=NUM_SCENES, topic=TOPIC, mid=mid
    )

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
                    temperature=0.85,
                    response_format={"type": "json_object"},
                    max_tokens=4096,
                )
                raw = resp.choices[0].message.content or ""
                story = json.loads(raw)
                if "scenes" not in story or not isinstance(story["scenes"], list):
                    raise ValueError("Missing 'scenes' array in LLM response")

                # If protagonist description exists, prepend it to each image prompt
                protagonist = story.get("protagonist", "")
                scenes = story["scenes"][:NUM_SCENES]
                for scene in scenes:
                    if protagonist and protagonist not in scene.get("image_prompt", ""):
                        scene["image_prompt"] = (
                            protagonist + ". " + scene["image_prompt"]
                        )

                # Pad if fewer than NUM_SCENES
                while len(scenes) < NUM_SCENES:
                    scenes.append(
                        {
                            "narration": "Aur tabhi, sab kuch badal gaya.",
                            "image_prompt": (
                                (protagonist + ". " if protagonist else "")
                                + "standing amid ruins of a burning city, "
                                "solo leveling manhwa style, high detail, "
                                "clean line art, dramatic shading, vivid colors, "
                                "cinematic composition, webtoon panel, masterpiece quality"
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
                if "model_not_found" in err_str or "does not exist" in err_str or "model_decommissioned" in err_str:
                    print(f"[story_gen] Model '{model}' not available, trying next...")
                    break
                wait = 2 ** attempt
                print(f"[story_gen] attempt {attempt} failed: {exc}; retrying in {wait}s")
                time.sleep(wait)

    raise SystemExit(f"[story_gen] Failed after trying all models. Last error: {last_err}")


if __name__ == "__main__":
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("story.json")
    generate_story(out)
