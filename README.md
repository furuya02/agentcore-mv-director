# agentcore-mv-director

A "creative director" AI agent running on Amazon Bedrock AgentCore.
Place images in S3 and send an empty payload — the agent automatically generates a concept from the images, produces lyrics, generates multi-cut video plus a song, and assembles them into one music video (PoC).

- **Concept**: Claude vision analyzes input images and auto-generates the MV concept
- **Lipsync detection**: Claude vision judges per-image whether the person is facing the camera in close-up — only those cuts get lipsync applied (no filename convention needed)
- **Lyrics**: Bedrock (Claude) generates original English lyrics matching the concept
- **Music**: ElevenLabs Music v2 (female vocals by default)
- **Video**: fal.ai PixVerse v5 image-to-video (per cut)
- **Lipsync**: fal.ai Kling LipSync (full mix, no stem separation needed)
- **Concat**: FFmpeg
- **Output**: Amazon S3 (`output/mv.mp4`)
- **Observability**: CloudWatch logs + OpenTelemetry traces (AgentCore built-in)
- **Concurrency guard**: S3 lock file prevents duplicate invocations (fal.ai / ElevenLabs cost protection)

## Architecture

![Architecture](docs/architecture-agentcore.png)

## Layout

```
main_agentcore.py   # AgentCore entrypoint (@app.entrypoint)
src/
  director.py       # Bedrock (Claude) — concept / lipsync judgment / storyboard / lyrics
  pipeline.py       # storyboard -> MV orchestration
  schema.py         # Storyboard schema / validation
  config.py         # config (auto dry-run when keys are absent)
  tools/            # music / video / lipsync / assemble / storage (S3)
cdk/                # S3 / Secrets Manager / IAM / AgentCore Runtime (TypeScript)
```

## Setup

### 1. Clone & deploy CDK

```bash
git clone https://github.com/furuya02/agentcore-mv-director.git
cd agentcore-mv-director/cdk
pnpm install
pnpm run cdk deploy -- --require-approval never
```

### 2. Put API keys into Secrets Manager

```bash
aws secretsmanager put-secret-value \
  --secret-id agentcore-mv-director-api-keys \
  --secret-string '{"FAL_KEY":"...","ELEVENLABS_API_KEY":"..."}'
```

### 3. Upload input images to S3

```bash
aws s3 cp input/ s3://agentcore-mv-director-<ACCOUNT_ID>/input/ --recursive
```

Image naming: any filename is fine. Claude vision automatically determines which images are
close-up / camera-facing (lipsync targets) — no special naming convention required.

## Invoke

```bash
echo '{}' > /tmp/payload.json

aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn "<RUNTIME_ARN>" \
  --payload fileb:///tmp/payload.json \
  --cli-read-timeout 0 \
  --region ap-northeast-1 \
  /tmp/response.json && cat /tmp/response.json
```

Default behavior with empty payload `{}`:

| Step | What happens |
|------|-------------|
| Images | Loaded from `s3://<bucket>/input/` automatically |
| Concept | Claude vision analyzes all images and generates the concept |
| Lipsync | Claude vision judges each image — close-up + camera-facing → lipsync applied |
| Lyrics | Bedrock generates original English lyrics matching the concept |
| Vocal | Female vocal |

### Payload parameters (all optional)

| Parameter | Default | Description |
|-----------|---------|-------------|
| `concept` | auto (from images) | Override the auto-generated concept |
| `images_s3_prefix` | `s3://<bucket>/input/` | S3 prefix for input images |
| `ai_lyrics` | `true` | Generate lyrics with Bedrock |
| `vocal` | `"female"` | `"male"` or `"female"` |
| `length` | `24` | Total MV length in seconds (single-image mode) |

## Observability

```bash
aws logs tail "/aws/bedrock-agentcore/runtimes/<agent_id>-DEFAULT" \
  --follow --format short --region ap-northeast-1
```

## Tear down (avoid lingering cost)

```bash
cd cdk && pnpm run cdk destroy
```

## Cost

- Video: ~$0.05–0.10 per cut (fal.ai PixVerse v5)
- Lipsync: ~$0.05 per singing cut (fal.ai Kling)
- Music: ~$0.03 per track (ElevenLabs Music v2)
- AgentCore: consumption-based (I/O wait is free)
- Generated songs are for in-MV background use only; uploading to music streaming services is not permitted (ElevenLabs terms)
