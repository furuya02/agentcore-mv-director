"""AgentCore Runtime エントリポイント（クリエイティブ・ディレクター）。

ローカルの scripts/run.py と同じモードをすべてサポートする。

ペイロード:
  concept        str   コンセプト（必須）
  image_s3_uri   str   単一画像の S3 URI（s3://bucket/key）
  images_s3_prefix str 複数画像フォルダの S3 プレフィックス（s3://bucket/prefix/）
  extend         int   image_s3_uri と併用。i2v 8秒 + extend×N の連続延長
  ai_lyrics      bool  images_s3_prefix と併用。歌詞を Bedrock(Claude) で生成
  vocal          str   "male" または "female"
  length         int   images_s3_prefix で画像1枚のときの MV 尺（秒）。既定 24

モード早見表:
  concept のみ                        → スタブ絵コンテで生成
  + image_s3_uri                      → 単一画像から生成（人物/画風固定）
  + image_s3_uri + extend N           → 単一画像 i2v + extend×N 連続動画
  + images_s3_prefix                  → 複数画像（各画像=1カット）
  + images_s3_prefix + ai_lyrics true → 複数画像 + Bedrock 作詞
"""
import json
import re
import tempfile
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from mvcore.config import S3_BUCKET
from mvcore.director import generate_storyboard, generate_music_spec, generate_concept_from_images
from mvcore.pipeline import run_pipeline, run_image_extend
from mvcore.schema import stub_storyboard, storyboard_from_images

app = BedrockAgentCoreApp()
log = app.logger

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}
_LOCK_KEY = "locks/running.lock"
_LOCK_TTL_SEC = 1800  # 30分超のロックはステール扱い


def _acquire_lock(bucket: str) -> bool:
    """S3にロックを作成する。有効なロックが既に存在する場合は False を返す。"""
    s3 = boto3.client("s3")
    try:
        obj = s3.get_object(Bucket=bucket, Key=_LOCK_KEY)
        data = json.loads(obj["Body"].read())
        if time.time() - data.get("ts", 0) < _LOCK_TTL_SEC:
            return False  # 有効なロックが存在する
    except ClientError as e:
        if e.response["Error"]["Code"] != "NoSuchKey":
            raise
    s3.put_object(
        Bucket=bucket,
        Key=_LOCK_KEY,
        Body=json.dumps({"ts": time.time()}).encode(),
    )
    return True


def _release_lock(bucket: str) -> None:
    try:
        boto3.client("s3").delete_object(Bucket=bucket, Key=_LOCK_KEY)
        log.info("ロックを解放しました")
    except Exception as e:
        log.error(f"ロック解放に失敗しました（手動削除が必要）: {e}")


def _order_key(p: Path):
    m = re.search(r"\d+", p.stem)
    return (int(m.group()) if m else 10**9, p.name)


def _download_file(s3_uri: str, dest: Path) -> Path:
    """s3://bucket/key をダウンロードして dest に保存する。"""
    without_scheme = s3_uri[len("s3://"):]
    bucket, key = without_scheme.split("/", 1)
    boto3.client("s3").download_file(bucket, key, str(dest))
    return dest


def _download_prefix(s3_prefix: str, dest_dir: Path) -> list[Path]:
    """s3://bucket/prefix/ 以下の画像ファイルをすべてダウンロードして返す。"""
    without_scheme = s3_prefix[len("s3://"):]
    bucket, prefix = without_scheme.split("/", 1)
    s3 = boto3.client("s3")
    paginator = s3.get_paginator("list_objects_v2")
    paths: list[Path] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if Path(key).suffix.lower() not in IMAGE_EXTS:
                continue
            local = dest_dir / Path(key).name
            s3.download_file(bucket, key, str(local))
            paths.append(local)
    return sorted(paths, key=_order_key)


def _vocalize(prompt: str, vocal: str | None) -> str:
    if not vocal:
        return prompt
    prompt = re.sub(r"\b(male|female)\s+vocals?\b", "", prompt, flags=re.I)
    prompt = re.sub(r"\s*,\s*,", ", ", prompt).strip().strip(",").strip()
    return f"{prompt}, {vocal} vocal"


@app.entrypoint
def invoke(payload: dict) -> dict:
    payload = payload or {}
    if S3_BUCKET and not _acquire_lock(S3_BUCKET):
        log.warning("別の invocation が実行中のため、リクエストを拒否しました")
        return {"error": "別の invocation が実行中です。完了後に再試行してください。"}

    try:
        concept: str | None = payload.get("concept")
        image_s3_uri: str | None = payload.get("image_s3_uri")
        images_s3_prefix: str | None = payload.get("images_s3_prefix")
        extend: int = int(payload.get("extend", 0))
        ai_lyrics: bool = bool(payload.get("ai_lyrics", True))
        vocal: str | None = payload.get("vocal", "female")
        length: int = int(payload.get("length", 24))

        # images_s3_prefix のデフォルト（image_s3_uri も未指定の場合）
        if not images_s3_prefix and not image_s3_uri and S3_BUCKET:
            images_s3_prefix = f"s3://{S3_BUCKET}/input/"

        log.info(f"concept={concept} image={image_s3_uri} images={images_s3_prefix} "
                 f"extend={extend} ai_lyrics={ai_lyrics} vocal={vocal} length={length}")

        tmpdir = Path(tempfile.mkdtemp())
        title = concept
        result: dict

        if image_s3_uri and extend > 0:
            # 単一画像 + 連続延長モード
            suffix = Path(image_s3_uri).suffix or ".png"
            image = _download_file(image_s3_uri, tmpdir / f"input{suffix}")
            log.info(f"downloaded image: {image}")
            result = run_image_extend(image, concept, extend, vocal=vocal)

        elif images_s3_prefix:
            # 複数画像モード
            imgs = _download_prefix(images_s3_prefix, tmpdir)
            if not imgs:
                return {"error": f"画像が見つかりません: {images_s3_prefix}"}
            log.info(f"downloaded {len(imgs)} images")
            if not concept:
                log.info("画像からコンセプトを自動生成中...")
                concept = generate_concept_from_images(imgs)
                log.info(f"自動生成コンセプト: {concept}")
            music_override = None
            if ai_lyrics:
                log.info("Bedrock で作詞中...")
                music_override = generate_music_spec(concept)
            sb = storyboard_from_images(imgs, concept, music_override, single_length_sec=length)
            sb.music["prompt"] = _vocalize(sb.music["prompt"], vocal)
            title = sb.title
            result = run_pipeline(sb)

        else:
            # 単一画像 or スタブ絵コンテモード
            if not concept:
                concept = "A cinematic music video"
            initial_image: Path | None = None
            if image_s3_uri:
                suffix = Path(image_s3_uri).suffix or ".png"
                initial_image = _download_file(image_s3_uri, tmpdir / f"input{suffix}")
                log.info(f"downloaded image: {initial_image}")
            sb = generate_storyboard(concept)
            sb.music["prompt"] = _vocalize(sb.music["prompt"], vocal)
            title = sb.title
            log.info(f"storyboard: {title} / {len(sb.cuts)} cuts")
            result = run_pipeline(sb, initial_image=initial_image)

        return {"title": title, "mv_path": str(result["mv"]), "s3_uri": result["s3_uri"]}

    finally:
        if S3_BUCKET:
            _release_lock(S3_BUCKET)


if __name__ == "__main__":
    app.run()
