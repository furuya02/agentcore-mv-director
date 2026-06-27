"""(b) 最小コストの実APIテスト：fal LTX で text-to-video を1カットだけ生成する。

要 FAL_KEY。LTX text-to-video は約 $0.04/本。チェーン無し・ffmpeg 不要。

    set -a && source .env && set +a && python -m scripts.test_video
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import FAL_KEY, DRY_RUN  # noqa: E402
from src.tools.video import generate_video  # noqa: E402


def main() -> None:
    if DRY_RUN or not FAL_KEY:
        print("FAL_KEY 未設定（または DRY_RUN=1）。実生成しません。")
        print(".env に FAL_KEY を設定して再実行してください。")
        return
    print("fal LTX で text-to-video を1カット生成します（約 $0.04）...")
    path = generate_video(
        model="fal-ai/ltx-video",
        prompt="Rainy Shibuya crossing at midnight, neon reflections",
        sec=5,
        n=1,
    )
    print(f"生成: {path.resolve()}  ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
