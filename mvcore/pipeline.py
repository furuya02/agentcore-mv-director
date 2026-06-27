"""絵コンテ（Storyboard）を受け取り、MV を組み立てるオーケストレーション。

Director Agent もドライランスクリプトも、この run_pipeline を共通で使う。
"""
import math
from pathlib import Path
from .schema import Storyboard, validate_storyboard, stub_storyboard
from .tools import (
    generate_music, generate_video, extend_video, extract_last_frame, prepare_image,
    lipsync, assemble_mv, slice_audio, cut_segment, upload_to_s3,
)

I2V_MODEL = "fal-ai/pixverse/v5/image-to-video"
SEG_SEC = 8  # PixVerse の1クリップ秒数（i2v / extend / リップシンク分割の単位）


def run_image_extend(initial_image: Path, concept: str, extend_count: int,
                     vocal: str | None = None) -> dict:
    """1枚の画像から連続動画を作り、全編を 8秒チャンクごとにリップシンクする。

    1) 画像 → i2v 8秒 → extend で連続延長（累積動画。最後の extend 出力が完成形）
    2) その連続動画を 8秒ごとに分割し、各チャンクをその時間帯の歌声でリップシンク
    3) リップシンク済みチャンクを連結＋楽曲合成 → 連続性を保ったまま全編で口が歌に同期
    """
    total_sec = SEG_SEC * (1 + extend_count)
    sb = stub_storyboard(concept)  # 楽曲プロンプト/歌詞を流用
    music_prompt = sb.music["prompt"]
    if vocal:  # ボーカル性別の指定があれば反映
        import re
        music_prompt = re.sub(r"\b(male|female)\s+vocals?\b", "", music_prompt, flags=re.I).strip().strip(",").strip()
        music_prompt = f"{music_prompt}, {vocal} vocal"
    music = generate_music(music_prompt, sb.music["lyrics"], total_sec * 1000)

    # 1) 連続動画（PixVerse extend は累積動画を返すので最後の出力が完成形）
    img = prepare_image(initial_image)
    final = generate_video(I2V_MODEL, sb.cuts[0].prompt, SEG_SEC, 1, start_image=img)
    for k in range(extend_count):
        final = extend_video(final, "continue the same scene seamlessly, cinematic, city pop night mood", k + 2)

    # 2) 全編リップシンク：8秒ごとに分割→各チャンクをその時間帯の歌声で口元同期
    segments: list[Path] = []
    for i in range(math.ceil(total_sec / SEG_SEC)):
        start = i * SEG_SEC
        dur = min(SEG_SEC, total_sec - start)
        chunk = cut_segment(final, start, dur, i + 1)
        seg_audio = slice_audio(music, start, dur, 200 + i)
        segments.append(lipsync(chunk, seg_audio, 200 + i))

    # 3) 連結＋楽曲合成
    mv = assemble_mv(segments, music)
    return {"mv": mv, "s3_uri": upload_to_s3(mv)}


def run_pipeline(sb: Storyboard, initial_image: Path | None = None) -> dict:
    validate_storyboard(sb)  # 絵コンテの整合性チェック

    # 1. 楽曲（歌入り・フルミックス）
    music = generate_music(sb.music["prompt"], sb.music["lyrics"], sb.music["length_ms"])

    # 2. 各カットを生成
    #    初期画像あり : 全カットを「元画像」から image-to-video 生成（孫世代の劣化を断つ）。
    #                   画像は LTX 固定解像度(3:2)へ事前クロップしてアスペクト比の歪みを防ぐ。
    #    初期画像なし : 従来どおり「前カットの最終フレーム」を次カットへ連鎖。
    anchor = prepare_image(initial_image) if initial_image is not None else None
    clips: list[Path] = []
    prev_last: Path | None = None
    offset = 0.0  # MV内での各カットの開始時刻（リップシンク用の音声切り出しに使う）
    for cut in sb.cuts:
        if cut.image is not None:        # 複数画像モード：このカット専用の画像を起点に
            model, start = I2V_MODEL, prepare_image(cut.image)
        elif anchor is not None:         # 単一初期画像モード：全カットを同じ画像から
            model, start = I2V_MODEL, anchor
        else:                            # 連鎖モード：前カットの最終フレームから
            model, start = cut.model, prev_last
        clip = generate_video(model, cut.prompt, cut.sec, cut.n, start_image=start)
        # 3. 顔があるカット（is_singing）のみ、その時間帯の音声で口元同期
        if cut.is_singing:
            seg = slice_audio(music, offset, cut.sec, cut.n)
            clip = lipsync(clip, seg, cut.n)
        clips.append(clip)
        offset += cut.sec
        if cut.image is None and anchor is None:
            prev_last = extract_last_frame(clip, cut.n)

    # 4. FFmpeg 連結＋音声合成
    mv = assemble_mv(clips, music)

    # 5. S3 へアップロード
    s3_uri = upload_to_s3(mv)
    return {"mv": mv, "s3_uri": s3_uri}
