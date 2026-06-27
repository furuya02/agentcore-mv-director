"""実APIでフルパイプラインを1本通す（課金あり）。

要 FAL_KEY / ELEVENLABS_API_KEY。動画生成を含むためコストが伸びる。
--image を渡すと、その画像を cut1 の開始フレームにして「初期画像から開始」する
（人物・画風を最初の1枚で固定でき、一貫性が上がる）。

    set -a && source .env && set +a
    python -m scripts.run "夜の東京のシティポップ"
    python -m scripts.run "夜の東京のシティポップ" --image input/first.png
"""
import argparse
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.schema import stub_storyboard, storyboard_from_images  # noqa: E402
from src.pipeline import run_pipeline, run_image_extend  # noqa: E402

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def _order_key(p: Path):
    """ファイル名中の数字で並べる（sing_ プレフィックスに関係なく連番順）。"""
    m = re.search(r"\d+", p.stem)
    return (int(m.group()) if m else 10**9, p.name)


def _vocalize(prompt: str, vocal: str | None) -> str:
    """楽曲プロンプトのボーカル性別を male / female で上書きする。"""
    if not vocal:
        return prompt
    prompt = re.sub(r"\b(male|female)\s+vocals?\b", "", prompt, flags=re.I)
    prompt = re.sub(r"\s*,\s*,", ", ", prompt).strip().strip(",").strip()
    return f"{prompt}, {vocal} vocal"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("concept", nargs="?", default="夜の東京を舞台にしたシティポップのMV")
    p.add_argument("--image", help="cut1 の開始画像（単一）。指定すると全カットをこの画像から生成")
    p.add_argument("--images", help="複数画像のディレクトリ。各画像=1カット（顔ありはリップシンク）")
    p.add_argument("--extend", type=int, default=0,
                   help="--image と併用。8秒i2v(先頭リップシンク)＋extendをN回で連続延長")
    p.add_argument("--ai-lyrics", action="store_true",
                   help="--images と併用。作詞をコンセプトから Bedrock(Claude) で生成する")
    p.add_argument("--vocal", choices=["male", "female"],
                   help="ボーカルの性別を指定（楽曲プロンプトに male/female vocal を反映）")
    p.add_argument("--length", type=int, default=24,
                   help="--images で画像が1枚のときのMV尺(秒)。8の倍数に丸め（既定24＝8×3）")
    args = p.parse_args()

    if args.image and args.extend > 0:  # 1画像→i2v＋extend 連続生成モード
        image = Path(args.image)
        if not image.exists():
            print(f"画像が見つかりません: {image}")
            return
        print(f"1枚の画像から i2v 8秒＋extend×{args.extend} で連続生成します")
        result = run_image_extend(image, args.concept, args.extend, vocal=args.vocal)
    elif args.images:  # 複数画像モード
        d = Path(args.images)
        imgs = sorted((f for f in d.iterdir() if f.suffix.lower() in IMAGE_EXTS), key=_order_key)
        if not imgs:
            print(f"画像が見つかりません: {d}")
            return
        music_override = None
        if args.ai_lyrics:  # 作詞だけ Bedrock(Claude) に任せる
            from src.director import generate_music_spec
            print("コンセプトから Bedrock(Claude) で作詞中...")
            music_override = generate_music_spec(args.concept)
            print(f"歌詞:\n{music_override['lyrics']}\n")
        sb = storyboard_from_images(imgs, args.concept, music_override, single_length_sec=args.length)
        sb.music["prompt"] = _vocalize(sb.music["prompt"], args.vocal)
        print(f"{len(imgs)} 枚の画像でMVを生成します（{sb.music['length_ms']//1000}秒・sing を含む名前のみリップシンク）")
        result = run_pipeline(sb)
    else:  # 単一画像 or スタブ
        image = Path(args.image) if args.image else None
        if image and not image.exists():
            print(f"画像が見つかりません: {image}")
            return
        sb = stub_storyboard(args.concept)
        sb.music["prompt"] = _vocalize(sb.music["prompt"], args.vocal)
        result = run_pipeline(sb, initial_image=image)

    print(f"完成MV: {result['mv'].resolve()}")
    print(f"S3:    {result['s3_uri']}")


if __name__ == "__main__":
    main()
