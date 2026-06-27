"""絵コンテ（Storyboard）の構造化スキーマ。"""
from dataclasses import dataclass, field
from pathlib import Path

# Director Agent に構造化出力させる JSON Schema（Strands structured output 用）
STORYBOARD_SCHEMA: dict = {
    "type": "object",
    "required": ["title", "concept", "music", "cuts"],
    "properties": {
        "title": {"type": "string"},
        "concept": {"type": "string"},
        "music": {
            "type": "object",
            "required": ["prompt", "lyrics", "length_ms"],
            "properties": {
                "prompt": {"type": "string", "description": "ElevenLabs Music へのスタイル指示"},
                "lyrics": {"type": "string", "description": "エージェントが作詞した歌詞（[Verse]/[Chorus] タグ可）"},
                "length_ms": {"type": "integer"},
            },
        },
        "cuts": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["n", "sec", "model", "prompt", "is_singing"],
                "properties": {
                    "n": {"type": "integer"},
                    "sec": {"type": "integer"},
                    "model": {"type": "string", "description": "fal.ai のモデルID"},
                    "prompt": {"type": "string"},
                    "is_singing": {"type": "boolean", "description": "歌唱カット（後で LipSync）"},
                },
            },
        },
    },
}


@dataclass
class Cut:
    n: int
    sec: int
    model: str
    prompt: str
    is_singing: bool
    image: Path | None = None  # このカット専用の起点画像（複数画像モードで使用）


@dataclass
class Storyboard:
    title: str
    concept: str
    music: dict
    cuts: list[Cut] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Storyboard":
        return cls(
            title=d["title"],
            concept=d["concept"],
            music=d["music"],
            cuts=[Cut(**c) for c in d["cuts"]],
        )


def validate_storyboard(sb: Storyboard) -> None:
    """絵コンテの整合性を検証。問題があれば ValueError を投げる。"""
    if not sb.cuts:
        raise ValueError("cuts が空です")
    for c in sb.cuts:
        if c.sec <= 0:
            raise ValueError(f"cut{c.n}: sec は正の値が必要です")
        if not c.model or not c.prompt:
            raise ValueError(f"cut{c.n}: model / prompt が空です")
    m = sb.music
    if not m.get("prompt"):
        raise ValueError("music.prompt が空です")
    if any(c.is_singing for c in sb.cuts) and not m.get("lyrics"):
        raise ValueError("歌唱カットがあるのに music.lyrics が空です（作詞が必要）")
    if m.get("length_ms", 0) < 3000:
        raise ValueError("music.length_ms は 3000ms 以上が必要です（ElevenLabs 制約）")


SCENE_SEC = 8  # 1画像あたりの秒数（PixVerse i2v の1クリップ）


def storyboard_from_images(images: list[Path], concept: str,
                           music_override: dict | None = None,
                           single_length_sec: int = 24) -> "Storyboard":
    """input/ に置いた複数画像から絵コンテを組み立てる。

    各画像を1カット(image-to-video, 8秒)にする。総尺 = 8 × 画像枚数（3枚→24秒/5枚→40秒）。
    **画像が1枚だけ**の場合は、規定の尺(single_length_sec, 既定24秒)になるよう同じ画像を
    8秒×n カットに複製する。
    **ファイル名に "sing" を含む画像のみ**歌唱カット（リップシンク対象）。並び順は run.py 側で連番ソート。
    music_override（{"prompt","lyrics"}）で楽曲スタイル・歌詞を上書きできる（AI作詞の差し込み用）。
    """
    if len(images) == 1:  # 1枚なら規定尺になるよう複製
        images = images * max(1, round(single_length_sec / SCENE_SEC))

    from .director import should_lipsync  # 循環インポート回避のため遅延インポート

    cuts: list[Cut] = []
    for i, img in enumerate(images, start=1):
        singing = should_lipsync(img)
        prompt = ("The person sings to the camera, gentle head movement, cinematic" if singing
                  else "Subtle natural cinematic motion, city pop night mood")
        cuts.append(Cut(i, SCENE_SEC, "fal-ai/pixverse/v5/image-to-video", prompt, singing, image=img))

    total_ms = sum(c.sec for c in cuts) * 1000
    music = {
        "prompt": "80s Japanese city pop, dreamy synths, slow groove, female vocal",
        "lyrics": "[Verse]\nNeon rain on the empty street\n[Chorus]\nDrive me through the Tokyo night",
    }
    if music_override:
        music = {"prompt": music_override["prompt"], "lyrics": music_override["lyrics"]}
    music["length_ms"] = total_ms

    return Storyboard(title="Image MV", concept=concept, music=music, cuts=cuts)

