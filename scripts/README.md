# scripts — Local execution (without AgentCore)

Run the pipeline directly from your local machine without deploying to AgentCore Runtime.
Useful for quick testing or development.

## Setup

```bash
cp .env.example .env   # fill in keys
set -a && source .env && set +a
```

## Dry-run (no charges)

Runs the full pipeline with placeholders — no API calls, even with keys set.

```bash
DRY_RUN=1 python -m scripts.dryrun
```

Placeholder files are written under `output/`.

## Tests (no charges)

```bash
python -m pytest -q
```

## Real API (charges apply)

Keys are checked **per tool** — set only `ELEVENLABS_API_KEY` to run music only;
video stays a placeholder when `FAL_KEY` is unset.

```bash
# (a) One ElevenLabs track (~$0.03)
python -m scripts.test_music

# (b) One fal video cut (~$0.05)
python -m scripts.test_video

# (c) Full pipeline — concept only (LTX x3 cuts + lipsync, ~$0.2+)
python -m scripts.run "a city-pop MV set in nighttime Tokyo"

# (c') Single initial image (every cut generated from it — fixes character/style)
python -m scripts.run "a city-pop MV set in nighttime Tokyo" --image input/first.png

# (c'') Multi-image mode (each image in input/ = one cut)
python -m scripts.run "a city-pop MV set in nighttime Tokyo" --images input

# (c''') Continuous extend mode (i2v 8s + extend xN = one continuous clip)
python -m scripts.run "a city-pop MV set in nighttime Tokyo" --image input/first.png --extend 2
```
