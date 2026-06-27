"""ローカル・ドライラン（課金なし・LLM/外部API を呼ばない）。

固定の絵コンテでパイプライン全体を流し、output/ にプレースホルダ成果物を生成して
処理の流れ（楽曲→動画3カット＋連鎖→歌唱リップシンク→FFmpeg連結）を確認する。

    DRY_RUN=1 python -m scripts.dryrun
"""
import os
import sys
from pathlib import Path

os.environ["DRY_RUN"] = "1"  # このスクリプトは常に課金なし（鍵があっても叩かない）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.schema import stub_storyboard  # noqa: E402
from src.pipeline import run_pipeline  # noqa: E402
from src.config import DRY_RUN, OUTPUT_DIR  # noqa: E402


def main() -> None:
    print(f"DRY_RUN={DRY_RUN}  OUTPUT_DIR={OUTPUT_DIR.resolve()}")
    sb = stub_storyboard("夜の東京を舞台にしたシティポップのMV")
    print(f"Storyboard: {sb.title} / {len(sb.cuts)} cuts / 歌唱カット="
          f"{[c.n for c in sb.cuts if c.is_singing]}")
    result = run_pipeline(sb)
    print(f"完成MV: {result['mv'].resolve()}")
    print(f"S3:    {result['s3_uri']}")
    print("生成物:")
    for p in sorted(OUTPUT_DIR.iterdir()):
        print(f"  - {p.name}")


if __name__ == "__main__":
    main()
