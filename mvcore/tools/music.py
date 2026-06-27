"""ElevenLabs Music v2 で歌入り楽曲を生成する（最小実装）。"""
import httpx
from pathlib import Path
from ..config import DRY_RUN, ELEVENLABS_API_KEY, OUTPUT_DIR, write_placeholder, reuse_existing

ENDPOINT = "https://api.elevenlabs.io/v1/music"


def generate_music(prompt: str, lyrics: str, length_ms: int) -> Path:
    """楽曲(mp3)を生成して output に保存し、パスを返す。"""
    out = OUTPUT_DIR / "music.mp3"
    if reuse_existing(out):
        return out
    if DRY_RUN or not ELEVENLABS_API_KEY:
        return write_placeholder(out, f"ElevenLabs music: {prompt} / lyrics={lyrics[:40]}...")

    # prompt に作詞済み歌詞を含めて歌入りで生成（force_instrumental=False）
    body = {
        "prompt": f"{prompt}, vocals start within the first 8 seconds\nLyrics:\n{lyrics}",
        "music_length_ms": length_ms,
        "model_id": "music_v2",
        "force_instrumental": False,
    }
    r = httpx.post(
        ENDPOINT,
        headers={"xi-api-key": ELEVENLABS_API_KEY},
        json=body,
        timeout=300,
    )
    r.raise_for_status()
    out.write_bytes(r.content)  # 同期でバイナリ(mp3)が返る
    return out
