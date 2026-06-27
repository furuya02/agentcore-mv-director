"""絵コンテ（Storyboard）を受け取り、MV を組み立てるオーケストレーション。"""
from pathlib import Path
from .schema import Storyboard, validate_storyboard
from .tools import (
    generate_music, generate_video, extend_video, extract_last_frame, prepare_image,
    lipsync, assemble_mv, slice_audio, cut_segment, upload_to_s3,
)

I2V_MODEL = "fal-ai/pixverse/v5/image-to-video"
SEG_SEC = 8  # PixVerse の1クリップ秒数（i2v / extend / リップシンク分割の単位）


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
