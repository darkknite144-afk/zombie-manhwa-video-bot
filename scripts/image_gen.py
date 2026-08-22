"""
Image generator — downloads one manhwa-style panel per scene from Pollinations.ai.
Free, no API key needed, hosted on their servers so the GitHub Actions CPU-only
runner never does heavy generation itself.

Each image is fetched as 1024x576 (16:9, Shorts-friendly portrait can be
configured via env). Retries with exponential backoff. A deterministic seed
per scene keeps visuals consistent across runs.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import requests
from PIL import Image

POLLINATIONS_URL = "https://image.pollinations.ai/prompt/{prompt}"
WIDTH = int(os.environ.get("IMG_WIDTH", "1024"))
HEIGHT = int(os.environ.get("IMG_HEIGHT", "576"))
TIMEOUT = 90


def _fetch(prompt: str, dest: Path, seed: int) -> bool:
    url = POLLINATIONS_URL.format(prompt=requests.utils.quote(prompt))
    url += f"?width={WIDTH}&height={HEIGHT}&seed={seed}&nologo=true&model=flux"
    for attempt in range(1, 5):
        try:
            r = requests.get(url, timeout=TIMEOUT)
            if r.status_code == 200 and len(r.content) > 5000:
                dest.write_bytes(r.content)
                # Validate it's a real image
                with Image.open(dest) as im:
                    im.verify()
                return True
            print(f"[image_gen] {dest.name} attempt {attempt}: "
                  f"status={r.status_code}, bytes={len(r.content)}")
        except Exception as exc:  # noqa: BLE001
            print(f"[image_gen] {dest.name} attempt {attempt} error: {exc}")
        time.sleep(2 ** attempt)
    return False


def generate_images(story_path: Path, out_dir: Path) -> list[Path]:
    story = json.loads(story_path.read_text())
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[Path] = []
    for i, scene in enumerate(story["scenes"]):
        dest = out_dir / f"scene_{i:02d}.jpg"
        seed = 1000 + i * 37
        if dest.exists() and dest.stat().st_size > 5000:
            print(f"[image_gen] {dest.name} already exists, skipping")
            results.append(dest)
            continue
        ok = _fetch(scene["image_prompt"], dest, seed)
        if not ok:
            # Fallback: a simpler prompt that rarely fails
            fallback = (
                "dark abandoned Indian city street at night with a lone figure, "
                "manhwa panel, dramatic lighting, cinematic, high quality"
            )
            ok = _fetch(fallback, dest, seed + 1)
        if ok:
            results.append(dest)
            print(f"[image_gen] OK {dest.name}")
        else:
            # Last resort: generate a solid placeholder so pipeline never breaks
            Image.new("RGB", (WIDTH, HEIGHT), (20, 20, 30)).save(dest, "JPEG")
            results.append(dest)
            print(f"[image_gen] WARNING placeholder for {dest.name}")
    return results


if __name__ == "__main__":
    story = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("story.json")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("images")
    generate_images(story, out)
