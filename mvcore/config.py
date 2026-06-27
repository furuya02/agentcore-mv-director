"""共通設定。SECRET_ARN が設定されている場合（AgentCore Runtime 上）は Secrets Manager からキーを取得する。
"""
import json
import os
from pathlib import Path


def _load_secrets(secret_arn: str) -> dict:
    import boto3
    client = boto3.client("secretsmanager")
    resp = client.get_secret_value(SecretId=secret_arn)
    secret_string = resp.get("SecretString", "")
    if not secret_string:
        return {}
    return json.loads(secret_string)


_SECRET_ARN: str | None = os.environ.get("SECRET_ARN")
if _SECRET_ARN:
    for _k, _v in _load_secrets(_SECRET_ARN).items():
        if _v and not os.environ.get(_k):
            os.environ[_k] = _v  # fal_client / elevenlabs SDK が os.environ を直接参照するため

FAL_KEY: str | None = os.environ.get("FAL_KEY")
ELEVENLABS_API_KEY: str | None = os.environ.get("ELEVENLABS_API_KEY")
S3_BUCKET: str | None = os.environ.get("S3_BUCKET")
FFMPEG: str = os.environ.get("FFMPEG_BIN", "ffmpeg")

OUTPUT_DIR: Path = Path(os.environ.get("OUTPUT_DIR", "output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

