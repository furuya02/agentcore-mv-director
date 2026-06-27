"""AgentCore Runtime エントリポイント（AIオーケストレーション実験版）。

[実験] invoke() の制御フローを Strands Agent + ツール群に置き換えたバージョン。
Claude 自身が各ツールをいつ・どの順で呼ぶか判断する。
元に戻す場合: git restore main_agentcore.py
"""
import json
import re
import tempfile
import time
from pathlib import Path

import boto3
from botocore.exceptions import ClientError
from strands import Agent, tool
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from mvcore.config import S3_BUCKET
from mvcore.director import generate_music_spec, generate_concept_from_images
from mvcore.pipeline import run_pipeline
from mvcore.schema import storyboard_from_images

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


# ──────────────────────────────────────────────
# AIオーケストレーション版
# ツール間のデータをセッション辞書で共有する
# ──────────────────────────────────────────────
_session: dict = {}


@tool
def download_input_images() -> str:
    """S3のinput/フォルダから入力画像を全てダウンロードする。
    次のステップ（コンセプト生成・絵コンテ作成）で必要な画像を準備する。
    必ず最初に呼ぶこと。
    """
    print("=" * 60, flush=True)
    print("[tool:start] download_input_images", flush=True)
    tmpdir = Path(tempfile.mkdtemp())
    _session["tmpdir"] = tmpdir
    prefix = f"s3://{S3_BUCKET}/input/"
    print(f"  S3プレフィックス: {prefix}", flush=True)
    imgs = _download_prefix(prefix, tmpdir)
    _session["images"] = imgs
    print(f"[tool:done] download_input_images: {len(imgs)}枚", flush=True)
    for i, img in enumerate(imgs, 1):
        print(f"  [{i}] {img.name}", flush=True)
    return f"{len(imgs)}枚の画像をダウンロードしました: {[p.name for p in imgs]}"


@tool
def generate_mv_concept() -> str:
    """ダウンロード済みの画像を分析してMVのコンセプトを自動生成する。
    Claude vision が画像の雰囲気・ロケーション・ムードを読み取りコンセプト文を返す。
    download_input_images の後に呼ぶこと。
    """
    print("=" * 60, flush=True)
    print("[tool:start] generate_mv_concept", flush=True)
    imgs = _session.get("images", [])
    print(f"  対象画像: {len(imgs)}枚", flush=True)
    concept = generate_concept_from_images(imgs)
    _session["concept"] = concept
    print(f"[tool:done] generate_mv_concept", flush=True)
    print(f"  → コンセプト: {concept}", flush=True)
    return f"生成されたコンセプト: {concept}"


@tool
def generate_music_and_lyrics() -> str:
    """コンセプトに合う楽曲スタイルと英語歌詞を生成する。
    generate_mv_concept の後に呼ぶこと。
    """
    print("=" * 60, flush=True)
    print("[tool:start] generate_music_and_lyrics", flush=True)
    concept = _session.get("concept", "A cinematic music video")
    print(f"  コンセプト: {concept}", flush=True)
    spec = generate_music_spec(concept)
    _session["music_spec"] = spec
    print(f"[tool:done] generate_music_and_lyrics", flush=True)
    print(f"  → 楽曲スタイル: {spec['prompt']}", flush=True)
    print(f"  → 歌詞（先頭200文字）:\n{spec['lyrics'][:200]}", flush=True)
    return f"楽曲スタイル: {spec['prompt']}\n歌詞（先頭）: {spec['lyrics'][:80]}..."


@tool
def produce_music_video() -> str:
    """絵コンテを組み立ててMVを生成し、S3にアップロードする。
    download_input_images / generate_mv_concept / generate_music_and_lyrics を
    先に実行しておくこと。リップシンク対象は Claude vision が自動判定する。
    このツールが完了したら処理終了。追加のツール呼び出しは不要。
    """
    print("=" * 60, flush=True)
    print("[tool:start] produce_music_video", flush=True)
    imgs = _session.get("images", [])
    concept = _session.get("concept", "A cinematic music video")
    music_spec = _session.get("music_spec")
    print(f"  画像枚数: {len(imgs)}", flush=True)
    print(f"  コンセプト: {concept}", flush=True)

    print("  [絵コンテ組み立て中] Claude vision でリップシンク判定...", flush=True)
    sb = storyboard_from_images(imgs, concept, music_spec)
    sb.music["prompt"] = _vocalize(sb.music["prompt"], "female")

    print(f"  [絵コンテ完成] {len(sb.cuts)}カット / 総尺 {sum(c.sec for c in sb.cuts)}秒", flush=True)
    for cut in sb.cuts:
        tag = "✓ リップシンク対象" if cut.is_singing else "  映像のみ"
        print(f"    cut{cut.n}: {cut.sec}秒 [{tag}] {cut.prompt[:60]}", flush=True)

    print("  [MV生成開始] pipeline 実行中...", flush=True)
    result = run_pipeline(sb)
    _session["result"] = result
    _session["storyboard"] = sb

    lipsync_cuts = [c.n for c in sb.cuts if c.is_singing]
    total_sec = sum(c.sec for c in sb.cuts)
    print(f"[tool:done] produce_music_video", flush=True)
    print(f"  → S3 URI: {result['s3_uri']}", flush=True)
    print(f"  → 総尺: {total_sec}秒", flush=True)
    print(f"  → リップシンク適用カット: {lipsync_cuts}", flush=True)
    return (
        f"MV生成完了\n"
        f"S3 URI: {result['s3_uri']}\n"
        f"総尺: {total_sec}秒\n"
        f"リップシンクカット: {lipsync_cuts}"
    )


DIRECTOR_SYSTEM_PROMPT = """あなたはミュージックビデオ（MV）のクリエイティブディレクターです。
ツールを使って、S3に保存された画像から完成度の高いMVを自律的に制作してください。

## ★ 絶対に守るガードレール（最優先）

### ツール呼び出しの制限
- 各ツールは **必ず1回だけ** 呼ぶ。同じツールを2回以上呼んではいけない
- ツールは **必ず下記の順番通り** に呼ぶ。順番を変えてはいけない
- 指定された4つ以外のツールを呼んではいけない
- ツールが成功しても失敗しても、**同じツールをリトライしてはいけない**

### エラー時の対応
- ツールがエラーを返したら **即座に処理を停止** してエラー内容を報告する
- 「別の方法を試す」「パラメータを変えて再実行する」などの回避策を取ってはいけない

### 費用に関する注意
- 各ツールの呼び出しは外部API（fal.ai・ElevenLabs）への課金が発生する
- 不要な繰り返しは直接コストにつながるため、**一度きりの実行を厳守する**
- 処理が長時間かかっても（動画生成は数分・リップシンクは12分）、待機中に再実行してはいけない

### 完了条件
- produce_music_video が成功したら **そこで終了** する
- 追加の確認・改善・別バリエーション生成などは行わない

---

## 制作ルール（背景知識）

### 映像の単位
- PixVerse v5（動画生成AI）は **8秒単位** でクリップを生成する
- 1枚の画像 = 1カット = 8秒 が基本。総尺 = 8秒 × 画像枚数

### リップシンクの判断基準
- **適用する**: 人物の顔がアップで映っており、カメラ目線の画像
- **適用しない**: 風景・引きのショット・横顔・後ろ姿
- この判断は Claude vision が自動で行う（コードが制御するため追加指示不要）
- リップシンク対象の顔画像は **正面の顔が必須**（顔なしだと face_detection_error になる）

### ボーカル・出力
- デフォルトは女性ボーカル（female vocal）
- 完成MVは S3 の output/mv.mp4 に保存される

---

## ツールの実行順序（厳守・各1回のみ）

1. download_input_images     — S3から画像を取得（必ず最初）
2. generate_mv_concept       — 画像からコンセプトを生成
3. generate_music_and_lyrics — 楽曲スタイルと英語歌詞を生成
4. produce_music_video       — MV生成・S3出力（これで終了）

produce_music_video 完了後は結果を報告して終了。それ以上の処理は一切行わないこと。
"""


@app.entrypoint
def invoke(payload: dict) -> dict:
    payload = payload or {}
    if S3_BUCKET and not _acquire_lock(S3_BUCKET):
        log.warning("別の invocation が実行中のため、リクエストを拒否しました")
        return {"error": "別の invocation が実行中です。完了後に再試行してください。"}

    _session.clear()
    try:
        agent = Agent(
            system_prompt=DIRECTOR_SYSTEM_PROMPT,
            tools=[
                download_input_images,
                generate_mv_concept,
                generate_music_and_lyrics,
                produce_music_video,
            ],
        )
        agent("MVを作成してください")

        sb = _session.get("storyboard")
        result = _session.get("result", {})
        return {
            "concept": _session.get("concept", ""),
            "lipsync_cuts": [c.n for c in sb.cuts if c.is_singing] if sb else [],
            "total_sec": sum(c.sec for c in sb.cuts) if sb else 0,
            "music_prompt": sb.music.get("prompt", "") if sb else "",
            "mv_path": str(result.get("mv", "")),
            "s3_uri": result.get("s3_uri", ""),
        }
    finally:
        _session.clear()
        if S3_BUCKET:
            _release_lock(S3_BUCKET)


if __name__ == "__main__":
    app.run()
