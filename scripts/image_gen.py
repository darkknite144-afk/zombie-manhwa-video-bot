"""
Image generator — generates high-quality manhwa-style panels per scene.

Primary: NVIDIA NIM API (FLUX.1-dev) — higher quality, sharper lines.
Fallback: Pollinations.ai (FLUX) — free, no API key, unlimited.

Images are generated at the best landscape resolution supported by both
NVIDIA NIM (1344x768) and Pollinations (1920x1080). Retries with
exponential backoff. Deterministic seed per scene keeps visuals
consistent across runs.
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

POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}"
NVIDIA_URL = "https://ai.api.nvidia.com/v1/genai/black-forest-labs/flux.1-dev"
# NVIDIA FLUX.1-dev only accepts these dimensions: 768, 832, 896, 960,
# 1024, 1088, 1152, 1216, 1280, 1344. Best 16:9 landscape combo is 1344x768.
NVIDIA_WIDTH = 1344
NVIDIA_HEIGHT = 768
POLLINATIONS_WIDTH = int(os.environ.get("IMG_WIDTH", "1920"))
POLLINATIONS_HEIGHT = int(os.environ.get("IMG_HEIGHT", "1080"))
TIMEOUT = 120
NVIDIA_API_KEY = os.environ.get("NVIDIA_API_KEY", "")


def _fetch_nvidia(prompt: str, dest: Path, seed: int) -> bool:
    """Generate image via NVIDIA NIM FLUX.1-dev API."""
    if not NVIDIA_API_KEY:
        print("[image_gen] NVIDIA_API_KEY not set, skipping NVIDIA")
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

    for attempt in range(1, 4):
        try:
            r = requests.post(NVIDIA_URL, headers=headers, json=payload, timeout=180)
            if r.status_code == 200:
                data = r.json()
                # NVIDIA returns base64 image in different possible fields
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
                              f"(attempt {attempt}, {len(img_bytes)} bytes, "
                              f"{NVIDIA_WIDTH}x{NVIDIA_HEIGHT})")
                        return True

            print(f"[image_gen] NVIDIA {dest.name} attempt {attempt}: "
                  f"status={r.status_code}, body={r.text[:300]}")

        except Exception as exc:  # noqa: BLE001
            print(f"[image_gen] NVIDIA {dest.name} attempt {attempt} error: {exc}")

        time.sleep(3 * attempt)

    return False


def _fetch_pollinations(prompt: str, dest: Path, seed: int) -> bool:
    """Generate image via Pollinations.ai FLUX (free, no key)."""
    url = POLLINATIONS_URL.format(prompt=requests.utils.quote(prompt))
    url += f"?width={POLLINATIONS_WIDTH}&height={POLLINATIONS_HEIGHT}&seed={seed}&nologo=true&model=flux"
    for attempt in range(1, 6):
        try:
            r = requests.get(url, timeout=TIMEOUT)
            if r.status_code == 200 and len(r.content) > 10000:
                dest.write_bytes(r.content)
                with Image.open(dest) as im:
                    im.verify()
                return True
            print(f"[image_gen] Pollinations {dest.name} attempt {attempt}: "
                  f"status={r.status_code}, bytes={len(r.content)}")
        except Exception as exc:  # noqa: BLE001
            print(f"[image_gen] Pollinations {dest.name} attempt {attempt} error: {exc}")
            time.sleep(2 ** attempt)
    return False


def _fetch(prompt: str, dest: Path, seed: int) -> bool:
    """Try NVIDIA first, fall back to Pollinations."""
    # Primary: NVIDIA NIM (FLUX.1-dev) — better quality
    if _fetch_nvidia(prompt, dest, seed):
        return True

    # Fallback: Pollinations.ai (FLUX) — free, unlimited
    print(f"[image_gen] NVIDIA failed for {dest.name}, trying Pollinations...")
    if _fetch_pollinations(prompt, dest, seed):
        return True

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
        ok = _fetch(scene["image_prompt"], dest, seed)
        if not ok:
            # Fallback: simpler prompt
            fallback = (
                "lone survivor in a ruined city, dark dramatic atmosphere, "
                "solo leveling manhwa style, high detail, clean line art, "
                "dramatic shading, vivid colors, cinematic composition, "
                "webtoon panel, masterpiece quality"
            )
            ok = _fetch(fallback, dest, seed + 1)
        if ok:
            results.append(dest)
            print(f"[image_gen] OK {dest.name}")
        else:
            # Last resort: placeholder
            Image.new("RGB", (NVIDIA_WIDTH, NVIDIA_HEIGHT), (15, 15, 20)).save(dest, "JPEG")
            results.append(dest)
            print(f"[image_gen] WARNING placeholder for {dest.name}")
    return results


if __name__ == "__main__":
    story = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("story.json")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("images")
    generate_images(story, out)