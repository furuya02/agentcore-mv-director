"""共通設定。APIキーが無い場合は自動でドライラン（課金なし）になる。
SECRET_ARN が設定されている場合（AgentCore Runtime 上）は Secrets Manager からキーを取得する。
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

# 全ツール強制ドライラン（課金なし）。各ツールは加えて「自分が使う鍵の有無」でも判定する。
DRY_RUN: bool = os.environ.get("DRY_RUN") == "1"

OUTPUT_DIR: Path = Path(os.environ.get("OUTPUT_DIR", "output"))
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def write_placeholder(path: Path, note: str) -> Path:
    """ドライラン用のプレースホルダファイルを書き出す。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"[DRY_RUN placeholder] {note}\n", encoding="utf-8")
    return path


# REUSE=1 のとき、既に生成済みの成果物（10KB超の実ファイル）は再生成せず使い回す。
REUSE: bool = os.environ.get("REUSE") == "1"


def reuse_existing(path: Path) -> bool:
    return REUSE and path.exists() and path.stat().st_size > 10_000
