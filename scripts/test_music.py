"""(a) 最小コストの実APIテスト：ElevenLabs で短い楽曲を1本だけ生成する。

要 ELEVENLABS_API_KEY。10秒生成で概算 $0.03 程度（または Free クレジット消費）。
動画は生成しないので fal の課金は発生しない。

    set -a && source .env && set +a && python -m scripts.test_music
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import ELEVENLABS_API_KEY, DRY_RUN  # noqa: E402
from src.tools import generate_music  # noqa: E402


def main() -> None:
    if DRY_RUN or not ELEVENLABS_API_KEY:
        print("ELEVENLABS_API_KEY 未設定（または DRY_RUN=1）。実生成しません。")
        print(".env に ELEVENLABS_API_KEY を設定して再実行してください。")
        return
    print("ElevenLabs で楽曲を1本生成します（10秒・最小コスト）...")
    path = generate_music(
        prompt="80s Japanese city pop, dreamy synths, slow groove, female vocal",
        lyrics="[Verse]\nNeon rain on the empty street",
        length_ms=10000,
    )
    print(f"生成: {path.resolve()}  ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
