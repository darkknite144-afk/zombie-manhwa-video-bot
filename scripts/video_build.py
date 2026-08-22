"""
Video assembler — combines manhwa panels + narration audio into one 2-minute
1080x1920 vertical (Shorts/Reels) video using MoviePy v2.x API.

Features:
  - Ken Burns slow zoom on each panel for cinematic feel (optional)
  - Title card at the start (story title from story.json)
  - Subtitle text (the narration) burned in at the bottom
  - Subtle fade between scenes
  - Ends with a 'Subscribe' end card

Runs on CPU inside GitHub Actions (no GPU needed).

MoviePy v2.x API notes:
  - Use moviepy.video.io.ImageSequenceClip / ImageClip, not moviepy.editor
  - resize() is now resized(); fadein/fadeout are with_effects()
  - TextClip is constructed differently; use ImageClip + PIL for text
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from moviepy import (
    AudioFileClip,
    CompositeVideoClip,
    ImageClip,
    concatenate_videoclips,
)
from moviepy.video.fx import FadeIn, FadeOut
from PIL import Image, ImageDraw, ImageFont

# Ensure FFmpeg binary is found even if not on system PATH
# (works locally with imageio-ffmpeg, and on GitHub Actions which installs
# ffmpeg via apt).
try:
    import imageio_ffmpeg
    import moviepy.config as _mc
    _mc.FFMPEG_BINARY = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    pass

# Output specs — vertical Shorts format
W, H = 1080, 1920
FPS = 24

# Panel dwell time after narration (a beat of silence + image)
PAD_TAIL = 0.6
# Title card / end card durations
TITLE_DUR = 3.0
END_DUR = 3.0


def _find_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for c in candidates:
        if Path(c).exists():
            return ImageFont.truetype(c, size)
    return ImageFont.load_default()


def _resize_cover(img_path: Path, target_w: int, target_h: int) -> Path:
    """Resize image to cover target dims (crop overflow), save as PNG."""
    img = Image.open(img_path).convert("RGB")
    src_ratio = img.width / img.height
    dst_ratio = target_w / target_h
    if src_ratio > dst_ratio:
        new_h = target_h
        new_w = int(target_h * src_ratio)
    else:
        new_w = target_w
        new_h = int(target_w / src_ratio)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - target_w) // 2
    top = (new_h - target_h) // 2
    img = img.crop((left, top, left + target_w, top + target_h))
    out = img_path.with_suffix(".panel.png")
    img.save(out, "PNG")
    return out


def _title_card(title: str, out_path: Path) -> Path:
    """Create a title card PNG."""
    img = Image.new("RGB", (W, H), (8, 8, 12))
    draw = ImageDraw.Draw(img)
    font = _find_font(64, bold=True)
    words = title.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > W - 120:
            if cur:
                lines.append(cur)
            cur = w
        else:
            cur = test
    if cur:
        lines.append(cur)
    line_h = 80
    total_h = line_h * len(lines)
    y = (H - total_h) // 2
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        draw.text(((W - tw) // 2, y), line, fill=(240, 240, 250), font=font)
        y += line_h
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    return out_path


def _end_card(out_path: Path) -> Path:
    img = Image.new("RGB", (W, H), (8, 8, 12))
    draw = ImageDraw.Draw(img)
    font = _find_font(80, bold=True)
    text = "SUBSCRIBE"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) // 2, H // 2 - 40), text, fill=(220, 60, 60), font=font)
    sub = "Next episode coming soon..."
    font2 = _find_font(44, bold=False)
    bbox2 = draw.textbbox((0, 0), sub, font=font2)
    tw2 = bbox2[2] - bbox2[0]
    draw.text(((W - tw2) // 2, H // 2 + 60), sub, fill=(200, 200, 200), font=font2)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    return out_path


def _subtitle_image(text: str, out_path: Path) -> Path:
    """Render subtitle text as a transparent PNG for compositing."""
    font = _find_font(42, bold=True)
    # Word-wrap to W-160 px
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        bbox = ImageDraw.Draw(Image.new("RGB", (1, 1))).textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > W - 160:
            if cur:
                lines.append(cur)
            cur = w
        else:
            cur = test
    if cur:
        lines.append(cur)
    line_h = 56
    total_h = line_h * len(lines)
    img = Image.new("RGBA", (W, total_h + 20), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    y = 0
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        tw = bbox[2] - bbox[0]
        x = (W - tw) // 2
        # Stroke (black outline) + white fill
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                draw.text((x + dx, y + dy), line, fill=(0, 0, 0, 220), font=font)
        draw.text((x, y), line, fill=(255, 255, 255, 255), font=font)
        y += line_h
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG")
    return out_path


def build_video(story_path: Path, images_dir: Path, audio_dir: Path,
                out_path: Path) -> Path:
    story = json.loads(story_path.read_text())
    scenes = story["scenes"]
    title = story.get("title", "Zombie Apocalypse")

    clips = []

    # Title card
    tc = _title_card(title, Path("assets/title_card.png"))
    title_clip = ImageClip(str(tc)).with_duration(TITLE_DUR).resized((W, H))
    clips.append(title_clip.with_effects([FadeIn(0.5), FadeOut(0.5)]))

    # Scene clips
    for i, scene in enumerate(scenes):
        img_file = images_dir / f"scene_{i:02d}.jpg"
        audio_file = audio_dir / f"scene_{i:02d}.mp3"
        if not img_file.exists() or not audio_file.exists():
            print(f"[video] missing assets for scene {i}, skipping")
            continue

        panel = _resize_cover(img_file, W, H)
        audio = AudioFileClip(str(audio_file))
        dur = audio.duration + PAD_TAIL

        # Ken Burns slow zoom (optional — disabled by default for speed)
        enable_zoom = os.environ.get("ENABLE_ZOOM", "0") == "1"
        base = ImageClip(str(panel)).with_duration(dur).with_audio(audio)
        if enable_zoom:
            base = base.resized(lambda t: 1.0 + 0.06 * (t / dur))
        base = base.with_position("center")

        # Subtitle at bottom
        sub_path = Path(f"assets/sub_{i:02d}.png")
        _subtitle_image(scene["narration"], sub_path)
        txt_clip = (ImageClip(str(sub_path))
                    .with_duration(dur)
                    .with_position(("center", H - 280)))

        comp = CompositeVideoClip([base, txt_clip], size=(W, H))
        comp = comp.with_effects([FadeIn(0.3), FadeOut(0.3)])
        clips.append(comp)
        print(f"[video] scene {i} built ({dur:.1f}s)")

    # End card
    ec = _end_card(Path("assets/end_card.png"))
    end_clip = ImageClip(str(ec)).with_duration(END_DUR).resized((W, H))
    clips.append(end_clip.with_effects([FadeIn(0.5), FadeOut(0.5)]))

    final = concatenate_videoclips(clips, method="compose")
    final = final.with_fps(FPS)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    final.write_videofile(
        str(out_path),
        fps=FPS,
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast",
        threads=4,
        ffmpeg_params=["-pix_fmt", "yuv420p", "-movflags", "+faststart"],
    )
    return out_path


if __name__ == "__main__":
    story = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("story.json")
    imgs = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("images")
    aud = Path(sys.argv[3]) if len(sys.argv) > 3 else Path("audio")
    out = Path(sys.argv[4]) if len(sys.argv) > 4 else Path("output/final_video.mp4")
    build_video(story, imgs, aud, out)
