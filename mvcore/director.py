"""Director Agent の頭脳：Bedrock(Claude)でコンセプトから絵コンテ＋作詞を生成する。

AgentCore ラッパー（bedrock_agentcore）には依存しないので、ローカルでもそのまま動く。
要：AWS認証 ＋ Bedrock の Claude モデルアクセス。モデルは BEDROCK_MODEL_ID で指定可。
"""
import logging
import os
from pathlib import Path
from pydantic import BaseModel, Field
from strands import Agent
from .schema import Storyboard, Cut

_log = logging.getLogger(__name__)

DIRECTOR_PROMPT = """あなたはミュージックビデオのクリエイティブ・ディレクターです。
与えられたコンセプトから、3カット前後の絵コンテと、完全オリジナルの歌詞を作ってください。
- 各カットは 5〜8 秒。映像内容(prompt)は英語で簡潔に。
- 1カット目は必ず風景・情景・引きのショットにし、is_singing は false にする（楽曲の前奏に対応するため）。
- 歌唱カット（人物の顔アップ）は2カット目以降に必ず1つ以上含め、その is_singing を true にする。
- 既存曲の歌詞や実在アーティスト名は使わない（必ずオリジナル）。
"""

# 動画モデルはコード側で固定（LLM には技術的なモデルIDを選ばせない）
T2V_MODEL = "fal-ai/pixverse/v5/text-to-video"
I2V_MODEL = "fal-ai/pixverse/v5/image-to-video"


class CutSpec(BaseModel):
    sec: int = Field(ge=5, le=8, description="カットの秒数")
    prompt: str = Field(description="カットの映像内容（英語）")
    is_singing: bool = Field(description="歌唱カット（顔アップ）なら true")


class StoryboardPlan(BaseModel):
    title: str = Field(description="MVのタイトル")
    music_prompt: str = Field(description="楽曲スタイルの指示（英語）")
    lyrics: str = Field(description="オリジナル歌詞")
    cuts: list[CutSpec]


class MusicPlan(BaseModel):
    music_prompt: str = Field(description="楽曲スタイルの指示（英語）")
    lyrics: str = Field(description="オリジナル歌詞")


def should_lipsync(image: Path) -> bool:
    """画像を Claude(Bedrock) で分析し、リップシンク対象かどうかを判定する。
    人物がカメラ目線でアップに映っている場合のみ True を返す。
    """
    import boto3

    ext = image.suffix.lower().lstrip(".")
    fmt = "jpeg" if ext in ("jpg", "jpeg") else ext
    content = [
        {
            "image": {
                "format": fmt,
                "source": {"bytes": image.read_bytes()},
            }
        },
        {
            "text": (
                "この画像を見てください。"
                "人物の顔がアップで映っており、かつカメラ（視聴者）の方を向いている場合は YES、"
                "それ以外（風景・引きのショット・横顔・後ろ姿など）は NO と答えてください。"
                "YES か NO のみ返答してください。"
            )
        },
    ]

    model_id = os.environ.get("BEDROCK_VISION_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
    resp = boto3.client("bedrock-runtime").converse(
        modelId=model_id,
        system=[{"text": "You are an image analyst. Reply with exactly one word: YES or NO."}],
        messages=[{"role": "user", "content": content}],
    )
    answer = resp["output"]["message"]["content"][0]["text"].strip().upper()
    result = answer.startswith("YES")
    print(f"[should_lipsync] {image.name}: answer={answer!r} -> {result}", flush=True)
    return result


def generate_concept_from_images(images: list[Path]) -> str:
    """入力画像群を Claude(Bedrock) で分析してMVコンセプトを自動生成する。"""
    import boto3

    content = []
    for img in images:
        ext = img.suffix.lower().lstrip(".")
        fmt = "jpeg" if ext in ("jpg", "jpeg") else ext
        content.append({
            "image": {
                "format": fmt,
                "source": {"bytes": img.read_bytes()},
            }
        })
    content.append({
        "text": (
            "これらの画像を見て、ミュージックビデオのコンセプトを英語で1〜2文で生成してください。"
            "画像の雰囲気・ロケーション・人物・ムードを反映させてください。"
            "返答はコンセプト文のみ。余分な説明は不要。"
        )
    })

    model_id = os.environ.get("BEDROCK_VISION_MODEL_ID", "anthropic.claude-3-haiku-20240307-v1:0")
    resp = boto3.client("bedrock-runtime").converse(
        modelId=model_id,
        system=[{"text": "あなたはMVのクリエイティブ・ディレクターです。"}],
        messages=[{"role": "user", "content": content}],
    )
    return resp["output"]["message"]["content"][0]["text"].strip()


def generate_music_spec(concept: str) -> dict:
    """コンセプトから「楽曲スタイル＋作詞」だけを Bedrock(Claude) で生成する。

    映像（絵コンテ）は別途ユーザー画像から作るため、ここでは作詞のみ担当する。
    """
    music_prompt = (
        "あなたは作詞家です。与えられたコンセプトに合う楽曲スタイル(英語)と、"
        "完全オリジナルの歌詞を英語で作ってください。歌詞は必ず英語にすること。"
        "実在曲の歌詞・アーティスト名は使わない。"
    )
    agent = Agent(model=os.environ["BEDROCK_MODEL_ID"], system_prompt=music_prompt) \
        if os.environ.get("BEDROCK_MODEL_ID") else Agent(system_prompt=music_prompt)
    plan: MusicPlan = agent.structured_output(MusicPlan, f"コンセプト: {concept}")
    return {"prompt": plan.music_prompt, "lyrics": plan.lyrics}


def _agent() -> Agent:
    model_id = os.environ.get("BEDROCK_MODEL_ID")  # 例: us.anthropic.claude-... 未指定なら Strands 既定
    if model_id:
        return Agent(model=model_id, system_prompt=DIRECTOR_PROMPT)
    return Agent(system_prompt=DIRECTOR_PROMPT)


def generate_storyboard(concept: str) -> Storyboard:
    """Bedrock(Claude) で絵コンテ＋作詞を生成し、Storyboard へ変換する。"""
    plan: StoryboardPlan = _agent().structured_output(StoryboardPlan, f"コンセプト: {concept}")
    total_ms = sum(c.sec for c in plan.cuts) * 1000
    cuts = [
        Cut(i, c.sec, T2V_MODEL if i == 1 else I2V_MODEL, c.prompt, c.is_singing)
        for i, c in enumerate(plan.cuts, start=1)
    ]
    return Storyboard(
        title=plan.title,
        concept=concept,
        music={"prompt": plan.music_prompt, "lyrics": plan.lyrics, "length_ms": total_ms},
        cuts=cuts,
    )
