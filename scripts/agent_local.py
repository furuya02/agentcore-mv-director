"""ステップ1：ローカルで Director Agent（Bedrock）を動かし、絵コンテ＋作詞を生成して表示する。

要：AWS認証（aws configure / SSO 等）＋ Bedrock の Claude モデルアクセス。
既定では絵コンテ生成のみ（Bedrockのテキスト生成だけ＝低コスト、fal/ElevenLabsは呼ばない）。
--run を付けると、その絵コンテから実際にMVも生成する（fal/ElevenLabs課金あり）。

    python -m scripts.agent_local "夜の東京を舞台にしたシティポップのMV"
    python -m scripts.agent_local "..." --run
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.director import generate_storyboard  # noqa: E402
from src.pipeline import run_pipeline  # noqa: E402


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("concept", nargs="?", default="夜の東京を舞台にしたシティポップのMV")
    p.add_argument("--run", action="store_true", help="絵コンテからMVも生成（課金あり）")
    args = p.parse_args()

    print(f"コンセプト: {args.concept}")
    print("Bedrock(Claude) で絵コンテ＋作詞を生成中...\n")
    sb = generate_storyboard(args.concept)

    print(f"=== 絵コンテ: {sb.title} ===")
    print(f"楽曲スタイル: {sb.music['prompt']}")
    print(f"尺: {sb.music['length_ms'] / 1000:.0f}秒")
    print(f"歌詞:\n{sb.music['lyrics']}\n")
    for c in sb.cuts:
        tag = "♪歌唱" if c.is_singing else "　映像"
        print(f"  cut{c.n} [{tag}] {c.sec}s: {c.prompt}")

    if args.run:
        print("\nMV生成を開始します（課金あり）...")
        result = run_pipeline(sb)
        print(f"完成MV: {result['mv'].resolve()}")
        print(f"S3:    {result['s3_uri']}")
    else:
        print("\n（絵コンテのみ生成しました。--run を付けると実際にMVを生成します）")


if __name__ == "__main__":
    main()
