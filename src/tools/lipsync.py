"""fal.ai Kling LipSync で歌唱カットの口元を楽曲に同期する（最小実装）。

ステム分離は不要（handoff §10-8）。フルミックス音声をそのまま渡す。
入力制約: 動画 2-10秒/≤100MB、音声 2-60秒/≤5MB。
"""
import time
import httpx
from pathlib import Path
from ..config import DRY_RUN, FAL_KEY, OUTPUT_DIR, write_placeholder, reuse_existing
from ._fal import video_url

MODEL = "fal-ai/kling-video/lipsync/audio-to-video"
QUEUE = "https://queue.fal.run"


def lipsync(video: Path, audio: Path, n: int) -> Path:
    """歌唱カットに口元同期を適用して返す。"""
    out = OUTPUT_DIR / f"cut{n}_lipsync.mp4"
    if reuse_existing(out):
        return out
    if DRY_RUN or not FAL_KEY:
        return write_placeholder(out, f"Kling LipSync: {video.name} + {audio.name} (full mix)")

    headers = {"Authorization": f"Key {FAL_KEY}"}
    payload = {"video_url": _upload(video), "audio_url": _upload(audio)}
    res = httpx.post(f"{QUEUE}/{MODEL}", headers=headers, json=payload, timeout=60)
    res.raise_for_status()  # 400/402/422 等を即surface
    sub = res.json()
    status_url, response_url = sub["status_url"], sub["response_url"]  # サブパス対応（自前生成しない）
    for _ in range(100):  # 生成に約12分。最大 ~25分（15秒間隔）
        st = httpx.get(status_url, headers=headers, timeout=30).json()
        print(f"  [lipsync cut{n}] fal status: {st.get('status')}")
        if st.get("status") == "COMPLETED":
            break
        time.sleep(15)
    else:
        raise TimeoutError(f"lipsync cut{n}: fal がタイムアウトしました")
    out_json = httpx.get(response_url, headers=headers, timeout=60).json()
    out.write_bytes(httpx.get(video_url(out_json), timeout=300).content)
    return out


def _upload(path: Path) -> str:
    """fal storage にファイルをアップロードして URL を得る（公式SDK）。"""
    import fal_client  # FAL_KEY を環境変数から読む

    return fal_client.upload_file(str(path))
