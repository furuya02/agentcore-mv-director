# scripts — Local execution guide

Run the pipeline directly from your local machine without deploying to AgentCore Runtime.
The same `src/` core is shared by both local CLI (`scripts/`) and AgentCore Runtime (`main_agentcore.py`).

```
python -m scripts.run ...           ← local CLI entry point
        │
        ├─ src/config.py            … config (keys / DRY_RUN / REUSE)
        ├─ src/schema.py            … storyboard builder
        ├─ src/director.py          … Bedrock (Claude) — concept / lipsync judgment / lyrics
        ▼
        src/pipeline.py             … orchestration (run_pipeline / run_image_extend)
        ├─ src/tools/music.py       → ElevenLabs (music)
        ├─ src/tools/video.py       → fal / PixVerse (video / extend)
        ├─ src/tools/lipsync.py     → fal / Kling LipSync
        ├─ src/tools/assemble.py    → FFmpeg (concat / mix / split)
        └─ src/tools/storage.py     → S3 (only when S3_BUCKET is set)
```

## 0. Setup (first time only)

```bash
cd agentcore-mv-director
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # fill in keys
```

`.env` keys:

```
FAL_KEY=...                       # fal.ai (video / lipsync)
ELEVENLABS_API_KEY=...            # ElevenLabs (music) — Starter plan ($6/mo) or above
FFMPEG_BIN=/Applications/ffmpeg   # full path to ffmpeg binary
# S3_BUCKET=...                   # upload finished MV to S3 (omit for local only)
```

Load keys before each run:

```bash
set -a && source .env && set +a
```

## 1. No-charge checks

```bash
DRY_RUN=1 python -m scripts.dryrun    # full pipeline with placeholders (always free)
python -m pytest -q                    # automated dry-run tests
```

## 2. Minimal real-API tests

```bash
python -m scripts.test_music    # (a) one ElevenLabs track (~$0.03)
python -m scripts.test_video    # (b) one fal video cut
```

## 3. Generate an MV (real APIs — charges apply)

### Mode A: Multi-image (each image = one 8-second cut)

```bash
python -m scripts.run "a Mediterranean summer pop MV" --images input
# With AI-generated lyrics:
python -m scripts.run "a Mediterranean summer pop MV" --images input --ai-lyrics
```

- Each image in `input/` becomes one 8-second cut. Total length = 8 × number of images.
- **Lipsync target is determined automatically by Claude vision** — images where a person is
  facing the camera in close-up get lipsync applied. No special filename convention needed.
- File order is determined by the number in the filename (ascending).
- When only one image is provided, it is duplicated to fill the default 24 seconds (`--length` to override).

### Mode B: Single image + continuous extend

```bash
python -m scripts.run "a Mediterranean summer pop MV" --image input/01.png --extend 2
```

8 × (1 + 2) = 24 seconds of continuous video. Lipsync is applied to every 8-second chunk.

### Mode C: Single image (no extend)

```bash
python -m scripts.run "a Mediterranean summer pop MV" --image input/01.png
```

### Mode D: No image (text-to-video stub storyboard)

```bash
python -m scripts.run "a Mediterranean summer pop MV"
```

### Flags

| Flag | Effect |
|------|--------|
| `--vocal male\|female` | Specify vocal gender |
| `--ai-lyrics` | Generate lyrics with Bedrock (Claude) |
| `--length SEC` | MV length in seconds for single-image mode (rounded to 8s; default 24) |
| `--extend N` | Continuous extend mode (use with `--image`) |

## 4. Useful environment variables

| Variable | Effect |
|----------|--------|
| `OUTPUT_DIR` | Change output folder (default `output/`) |
| `REUSE=1` | Reuse existing generated files — resume after failure |
| `DRY_RUN=1` | Force dry-run for all tools (no charges) |
| `FFMPEG_BIN` | Full path to ffmpeg binary |
| `S3_BUCKET` | Upload finished MV to S3 |

## 5. Parallel runs

Set different `OUTPUT_DIR` (and separate input folders) to run multiple jobs in parallel:

```bash
# Terminal 1
OUTPUT_DIR=out_a python -m scripts.run "..." --images input_a
# Terminal 2
OUTPUT_DIR=out_b python -m scripts.run "..." --image input_b/x.png --extend 2
```

## 6. Time & cost estimates

| Step | Time | Cost |
|------|------|------|
| PixVerse v5 video (720p, 8s) | 30s – 2min per cut | ~$0.05–0.10 |
| Kling LipSync | ~5–15min per chunk | ~$0.05 |
| ElevenLabs Music v2 | ~30s | ~$0.03 |

If a run times out mid-way, add `REUSE=1` and rerun the same command to resume from existing files.

## 7. Output files

| File | Description |
|------|-------------|
| `<OUTPUT_DIR>/mv.mp4` | Final MV |
| `cutN.mp4` | Per-cut video |
| `cutN_lipsync.mp4` | Lipsync-applied cut |
| `music.mp3` | Generated music track |
| `_segN.mp3` | Audio segment (per cut) |

## 8. Generation rules

See [generation-rules.md](../docs/generation-rules.md) for principles on producing stable, coherent MVs.
