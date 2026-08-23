"""
Image generator — NVIDIA NIM FLUX.1-dev ONLY.

Generates high-quality manhwa-style panels at 1344x768 (NVIDIA's best 16:9).
No fallback to Pollinations. Retries with exponential backoff + rate-limit delay.
"""

from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path

import requests
from PIL import Image

NVIDIA_URL = "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.1-dev"
# NVIDIA FLUX.1-dev only accepts: 768,832,896,960,1024,1088,1152,1216,1280,1344
NVIDIA_WIDTH = 1344
NVIDIA_HEIGHT = 768
TIMEOUT = 180
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")
# Delay between images to avoid rate limiting (seconds)
INTER_IMAGE_DELAY = 8


def _fetch_nvidia(prompt: str, dest: Path, seed: int) -> bool:
    """Generate image via NVIDIA NIM FLUX.1-dev API."""
    if not NVIDIA_API_KEY:
        print("[image_gen] ERROR: NVIDIA_API_KEY not set!")
        return False

    headers = {
        "Authorization": f"Bearer {NVIDIA_API_KEY}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    payload = {
        "prompt": prompt,
        "cfg_scale": 4.5,
        "steps": 30,
        "seed": seed,
        "width": NVIDIA_WIDTH,
        "height": NVIDIA_HEIGHT,
    }

    for attempt in range(1, 6):
        try:
            r = requests.post(NVIDIA_URL, headers=headers, json=payload, timeout=TIMEOUT)
            if r.status_code == 200:
                data = r.json()
                img_b64 = None
                if "artifacts" in data and len(data["artifacts"]) > 0:
                    img_b64 = data["artifacts"][0].get("base64")
                elif "images" in data and len(data["images"]) > 0:
                    img_b64 = data["images"][0].get("base64")
                elif "data" in data and len(data["data"]) > 0:
                    img_b64 = data["data"][0].get("b64_json")
                elif "b64_json" in data:
                    img_b64 = data["b64_json"]
                elif "image" in data:
                    img_b64 = data["image"]

                if img_b64:
                    img_bytes = base64.b64decode(img_b64)
                    if len(img_bytes) > 10000:
                        dest.write_bytes(img_bytes)
                        with Image.open(dest) as im:
                            im.verify()
                        print(f"[image_gen] NVIDIA OK {dest.name} "
                              f"(attempt {attempt}, {len(img_bytes)} bytes)")
                        return True

            # 429 = rate limited, wait longer
            if r.status_code == 429:
                wait = 15 * attempt
                print(f"[image_gen] NVIDIA {dest.name} rate limited (429), "
                      f"waiting {wait}s...")
                time.sleep(wait)
                continue

            print(f"[image_gen] NVIDIA {dest.name} attempt {attempt}: "
                  f"status={r.status_code}, body={r.text[:400]}")

        except Exception as exc:  # noqa: BLE001
            print(f"[image_gen] NVIDIA {dest.name} attempt {attempt} error: {exc}")

        # Exponential backoff: 5, 10, 20, 40, 60
        wait = min(5 * (2 ** (attempt - 1)), 60)
        print(f"[image_gen] Retrying in {wait}s...")
        time.sleep(wait)

    return False


def generate_images(story_path: Path, out_dir: Path) -> list[Path]:
    story = json.loads(story_path.read_text())
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []
    for i, scene in enumerate(story["scenes"]):
        dest = out_dir / f"scene_{i:02d}.jpg"
        seed = 1000 + i * 37
        if dest.exists() and dest.stat().st_size > 10000:
            print(f"[image_gen] {dest.name} already exists, skipping")
            results.append(dest)
            continue

        ok = _fetch_nvidia(scene["image_prompt"], dest, seed)

        if not ok:
            # Retry with shorter prompt (sometimes long prompts fail)
            short_prompt = scene["image_prompt"][:500]
            ok = _fetch_nvidia(short_prompt, dest, seed + 1)

        if ok:
            results.append(dest)
            print(f"[image_gen] OK {dest.name}")
        else:
            # Last resort: dark placeholder
            Image.new("RGB", (NVIDIA_WIDTH, NVIDIA_HEIGHT), (15, 15, 20)).save(dest, "JPEG")
            results.append(dest)
            print(f"[image_gen] WARNING placeholder for {dest.name}")

        # Rate-limit delay between images
        if i < len(story["scenes"]) - 1:
            print(f"[image_gen] Cooling down {INTER_IMAGE_DELAY}s before next image...")
            time.sleep(INTER_IMAGE_DELAY)

    return results


if __name__ == "__main__":
    story = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("story.json")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("images")
    generate_images(story, out)