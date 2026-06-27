# agentcore-mv-director

A "creative director" AI agent running on Amazon Bedrock AgentCore.
From a single concept (e.g. "a city-pop MV set in nighttime Tokyo"), it generates a storyboard
and lyrics, then auto-produces multi-cut video plus a song and assembles them into one music video (PoC).

- Director Agent (Strands Agents / Python) emits the storyboard + lyrics as structured output
- Music: ElevenLabs Music v2 (with vocals)
- Video: fal.ai (per-cut model, last-frame -> next-cut start-frame chaining)
- Singing cut: fal.ai Kling LipSync (no stem separation needed; full mix works)
- Concatenation: FFmpeg (intended to run on AgentCore Code Interpreter)
- Output: Amazon S3 / reasoning traces via CloudWatch (AgentCore Observability)

Architecture diagram: [../Blog/architecture.png](../Blog/architecture.png) (source: `../Blog/architecture.drawio`)

## Layout

```
src/
  agent.py        # AgentCore entrypoint (Strands Director Agent)
  pipeline.py     # storyboard -> MV orchestration (with validation)
  schema.py       # Storyboard schema / validation / stub
  config.py       # config (auto dry-run when keys are absent)
  tools/          # music / video / lipsync / assemble / storage(S3)
scripts/
  dryrun.py       # always free smoke test (never calls APIs, even with keys)
  test_music.py   # (a) cheapest real-API test (one ElevenLabs track)
  test_video.py   # (b) cheapest real-API test (one fal LTX cut)
  run.py          # (c) full real pipeline, one MV (charges apply)
tests/            # dry-run automated tests (pytest)
cdk/              # S3 / Secrets Manager / IAM (TypeScript)
```

## Setup

```bash
git clone <REPO_URL>
cd agentcore-mv-director
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Verify (dry-run, no charges)

The whole pipeline flows with placeholders even without API keys.

```bash
DRY_RUN=1 python -m scripts.dryrun
```

Placeholders for each cut, the song and the final MV are written under `output/`.

### Tests (no charges)

```bash
python -m pytest -q
```

Validates pipeline wiring and storyboard validation (a singing cut and lyrics are required) under dry-run.

## Run (real APIs, usage-based billing)

Keys are checked **per tool** (set only `ELEVENLABS_API_KEY` to run music only; video stays a
placeholder when `FAL_KEY` is unset). `scripts/dryrun.py` never charges, even with keys set.

```bash
cp .env.example .env   # fill in keys
set -a && source .env && set +a

# (a) one ElevenLabs track (~$0.03)
python -m scripts.test_music

# (b) one fal LTX cut (~$0.04)
python -m scripts.test_video

# (c) full pipeline (LTX x3 cuts + lipsync, ~$0.1+)
python -m scripts.run "a city-pop MV set in nighttime Tokyo"

# (c') single initial image (every cut generated from it -> fixes character/style)
python -m scripts.run "a city-pop MV set in nighttime Tokyo" --image input/first.png

# (c'') multi-image mode (each image in input/ = one cut; only face images get lipsync)
python -m scripts.run "a city-pop MV set in nighttime Tokyo" --images input

# (c''') one-image continuous mode (i2v 8s [first part lipsynced] + extend xN = one continuous clip)
python -m scripts.run "a city-pop MV set in nighttime Tokyo" --image input/first0.png --extend 2
```

## AWS resources (CDK)

Create the S3 bucket (MV output), Secrets Manager (API keys) and IAM policy via CDK.
Note: the agent itself is deployed with the AgentCore CLI, not CDK.

```bash
cd cdk
pnpm install
# Name is agentcore-mv-director-{accountId}; override with -c bucket_suffix=YYYYMMDD.
pnpm exec cdk deploy -c bucket_suffix=20260623
```

After deploy, put the API keys into Secrets Manager:

```bash
aws secretsmanager put-secret-value \
  --secret-id agentcore-mv-director-api-keys \
  --secret-string '{"FAL_KEY":"...","ELEVENLABS_API_KEY":"..."}'
```

Attach the `RuntimePolicyArn` output to the AgentCore Runtime execution role.

Tear down (avoid lingering cost):

```bash
pnpm exec cdk destroy
```

## Deploy (AgentCore CLI)

The agent itself is deployed with the AgentCore CLI (`@aws/agentcore`). Note: use pnpm (npm/npx are not used here).

```bash
pnpm add -g @aws/agentcore
agentcore deploy
agentcore invoke '{"concept": "a city-pop MV set in nighttime Tokyo"}'
```

## Observability (reasoning traces)

An agent deployed to AgentCore Runtime is auto-instrumented with OpenTelemetry, so you can inspect
traces of storyboard decisions, model selection and tool calls in CloudWatch.

1. Enable CloudWatch Transaction Search once per account (first time only):
   ```bash
   aws xray update-trace-segment-destination --destination CloudWatchLogs
   ```
   (Console: CloudWatch -> Settings -> Transaction Search -> Enable)
2. `agentcore deploy` (OTel auto-instrumentation; no extra libraries)
3. In the CloudWatch console, open "GenAI Observability" -> Trace View to see the agent's
   reasoning and tool-call timeline.

Logs go to `/aws/bedrock-agentcore/runtimes/<agent_id>-<endpoint>/...`.

## Cost & notes

- Video generation cost grows with the number of attempts. Decide a cap before running real APIs.
- AgentCore is consumption-based (I/O wait is free). No always-on charges.
- Generated songs are for in-MV background use only; uploading them as tracks to music streaming services is not permitted (ElevenLabs terms).
