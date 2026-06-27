"""fal.ai で動画カットを生成し、最終フレームを抽出する（最小実装）。

first/last frame 制御の引数はモデル系統で異なる（handoff §10-2）:
  - Kling/Wan/Vidu系 : start_image_url / end_image_url
  - Veo系            : first_frame_url / last_frame_url
  - Luma系           : keyframes.frame0 / frame1
ここでは PoC として「開始画像」だけを連鎖に使う（カットNの最終フレーム→N+1の開始）。
"""
import subprocess
import time
import httpx
from pathlib import Path
from ..config import FAL_KEY, FFMPEG, OUTPUT_DIR
from ._fal import video_url

QUEUE = "https://queue.fal.run"
PIXVERSE_RESOLUTION = "720p"  # 360p / 540p / 720p / 1080p（軽くするなら 540p へ）


def _start_arg(model: str, image_url: str) -> dict:
    """モデル系統に応じた開始フレーム引数を返す（handoff §10-2）。"""
    if "luma" in model:
        return {"keyframes": {"frame0": {"type": "image", "url": image_url}}}
    if "kling" in model or "wan" in model or "vidu" in model:
        return {"start_image_url": image_url}
    return {"image_url": image_url}  # LTX / Veo / その他


def generate_video(model: str, prompt: str, sec: int, n: int,
                   start_image: Path | None = None) -> Path:
    """1カット動画(mp4)を生成して返す。start_image があれば連鎖の開始フレームに使う。"""
    out = OUTPUT_DIR / f"cut{n}.mp4"
    payload: dict = {"prompt": prompt}
    if "pixverse" in model:  # PixVerse v5：解像度と長さ(5/8s)を指定
        payload.update({
            "resolution": PIXVERSE_RESOLUTION,
            "duration": "8" if sec >= 8 else "5",
        })
    elif "ltx-2" in model:  # LTX-2 は長さ・解像度・fps を指定できる（音声は使わないので off）
        payload.update({
            "duration": str(sec),       # 6 / 8 / 10
            "resolution": "1080p",
            "fps": "25",
            "generate_audio": False,
        })
    if start_image:
        payload.update(_start_arg(model, _upload(start_image)))

    url = _run_queue_job(model, payload, "video", n)
    out.write_bytes(httpx.get(url, timeout=300).content)
    return out


EXTEND_MODEL = "fal-ai/pixverse/extend"


def extend_video(video: Path, prompt: str, n: int) -> Path:
    """既存動画の続きを PixVerse extend で生成（+8秒・連続）。出力は cut{n}.mp4。"""
    out = OUTPUT_DIR / f"cut{n}.mp4"
    payload = {
        "video_url": _upload(video),
        "prompt": prompt,
        "resolution": PIXVERSE_RESOLUTION,
        "duration": "8",
        "model": "v5",
    }
    url = _run_queue_job(EXTEND_MODEL, payload, "extend", n)
    out.write_bytes(httpx.get(url, timeout=300).content)
    return out


def _run_queue_job(model: str, payload: dict, label: str, n: int) -> str:
    """fal キューに投げ、COMPLETED まで待って結果の動画URLを返す（submit応答のURLを使用）。"""
    headers = {"Authorization": f"Key {FAL_KEY}"}
    res = httpx.post(f"{QUEUE}/{model}", headers=headers, json=payload, timeout=60)
    res.raise_for_status()  # 402/422 等を即surface
    sub = res.json()
    status_url, response_url = sub["status_url"], sub["response_url"]  # サブパス対応
    for _ in range(240):  # 最大 ~20分（5秒間隔）。キュー混雑に備えて長めに
        st = httpx.get(status_url, headers=headers, timeout=30).json()
        print(f"  [{label} cut{n}] fal status: {st.get('status')}")
        if st.get("status") == "COMPLETED":
            break
        time.sleep(5)
    else:
        raise TimeoutError(f"{label} cut{n}: fal がタイムアウトしました")
    out_json = httpx.get(response_url, headers=headers, timeout=60).json()
    return video_url(out_json)


def prepare_image(image: Path) -> Path:
    """入力画像を 3:2 へ中央クロップする（解像度は落とさず高品質を維持）。

    LTX 系の image-to-video は入力画像のアスペクト比を踏襲するため、3:2 に切れば 3:2 で出力される。
    """
    out = OUTPUT_DIR / "_input_3x2.png"
    subprocess.run(
        [FFMPEG, "-y", "-i", str(image),
         "-vf", "crop='min(iw,ih*3/2)':'min(ih,iw*2/3)'", str(out)],
        check=True,
    )
    return out


def extract_last_frame(video: Path, n: int) -> Path:
    """動画の最終フレームを PNG（可逆）で抽出（連鎖のガクつき防止）。"""
    out = OUTPUT_DIR / f"cut{n}_last.png"
    subprocess.run(
        [FFMPEG, "-y", "-sseof", "-0.1", "-i", str(video), "-update", "1", str(out)],
        check=True,
    )
    return out


def _upload(path: Path) -> str:
    """fal storage にファイルをアップロードして URL を得る（公式SDK）。"""
    import fal_client  # FAL_KEY を環境変数から読む

    return fal_client.upload_file(str(path))
