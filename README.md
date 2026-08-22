# 🧟 Zombie Manhwa Video Bot

Fully automated **GitHub Actions** pipeline that generates a **2-minute Hinglish
zombie-apocalypse manhwa-style video** — story → images → narration → final
video render. No GPU, no paid services. Runs entirely on GitHub's free runners.

## Pipeline

| Step | What | Tool / Service | Cost |
|------|------|----------------|------|
| 1 | Story + scene prompts | Groq LLM API (`llama-3.1-8b-instant`) | Free tier |
| 2 | Manhwa-style panels | Pollinations.ai (FLUX model) | Free, no key |
| 3 | Hinglish narration TTS | edge-tts (Microsoft Edge TTS) | Free |
| 4 | Video assembly (1080×1920) | MoviePy + FFmpeg (CPU) | Free |
| 5 | Upload artifact | `actions/upload-artifact` | Free |

## Setup (2 minutes)

### 1. Get a free Groq API key
Go to **https://console.groq.com** → API Keys → Create. Copy the key.

### 2. Add it as a repo secret
- GitHub repo → **Settings** → **Secrets and variables** → **Actions**
- **New repository secret**
- Name: `GROQ_API_KEY`
- Value: *(paste your key)*

### 3. Run the workflow
- Go to **Actions** tab
- Select **"Generate Zombie Manhwa Video"**
- Click **"Run workflow"** (optionally edit topic / scene count)
- Wait ~15-25 minutes (depends on Pollinations response times)

### 4. Download the video
- When the run finishes, scroll to the **Artifacts** section
- Download `zombie-manhwa-video` — inside is `final_video.mp4`

## Project structure

```
.
├── .github/workflows/
│   └── generate-video.yml      # The GitHub Actions workflow
├── scripts/
│   ├── main.py                 # Orchestrator — runs all 4 steps
│   ├── story_gen.py            # Step 1: Groq LLM → story.json
│   ├── image_gen.py            # Step 2: Pollinations.ai → images/
│   ├── tts_gen.py              # Step 3: edge-tts → audio/
│   └── video_build.py          # Step 4: MoviePy → final_video.mp4
├── requirements.txt
└── README.md
```

## Configuration (env vars / workflow inputs)

| Variable | Default | Description |
|----------|---------|-------------|
| `GROQ_API_KEY` | *(required)* | Free Groq API key |
| `GROQ_MODEL` | `llama-3.1-8b-instant` | Any Groq-supported model |
| `NUM_SCENES` | `12` | Scene count (~10s each → ~2 min) |
| `VIDEO_TOPIC` | zombie survival theme | Passed to the LLM |
| `IMG_WIDTH` / `IMG_HEIGHT` | `1024` / `576` | Panel resolution |
| `ENABLE_ZOOM` | `0` | Set to `1` for Ken Burns zoom effect |

## Output specs

- **Resolution:** 1080×1920 (vertical Shorts/Reels)
- **FPS:** 24
- **Codec:** H.264 + AAC
- **Features:** Title card, burned-in subtitles, end card, fade transitions

## Limits to know

- GitHub free tier: **~2000 minutes/month** (private repos), **unlimited** (public repos)
- Max job runtime: **6 hours** (we target <30 min)
- Artifact retention: **14 days** (then auto-deleted; download in time)
- Pollinations.ai may rate-limit under heavy load; the script retries with backoff

## License

MIT — do whatever you want.
