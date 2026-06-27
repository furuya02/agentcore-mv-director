"""FFmpeg で全カットを連結し、楽曲（フルミックス）を音声トラックに合成する（最小実装）。"""
import subprocess
from pathlib import Path
from ..config import FFMPEG, OUTPUT_DIR


def cut_segment(video: Path, start: float, dur: int, n: int) -> Path:
    """連続動画から [start, start+dur] 秒の区間を切り出す（全編リップシンクの分割用）。"""
    out = OUTPUT_DIR / f"_chunk{n}.mp4"
    subprocess.run(
        [FFMPEG, "-y", "-ss", str(start), "-i", str(video), "-t", str(dur),
         "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out)],
        check=True,
    )
    return out


def slice_audio(music: Path, start: float, dur: int, n: int) -> Path:
    """楽曲から [start, start+dur] 秒を切り出す（カットごとのリップシンク用）。"""
    out = OUTPUT_DIR / f"_seg{n}.mp3"
    subprocess.run(
        [FFMPEG, "-y", "-ss", str(start), "-t", str(dur), "-i", str(music), str(out)],
        check=True,
    )
    return out


def assemble_mv(clips: list[Path], music: Path) -> Path:
    """カット動画を順に連結し、楽曲を被せて完成MV(mp4)を返す。"""
    out = OUTPUT_DIR / "mv.mp4"

    # 各カットを 30fps / SAR=1 に正規化してから連結し、楽曲を音声トラックに合成。
    # （fps がカットごとに異なると -c copy 連結では DTS が壊れ、尺欠け・音声再生不可になる）
    n = len(clips)
    inputs: list[str] = []
    for c in clips:
        inputs += ["-i", str(c)]
    inputs += ["-i", str(music)]
    # 解像度を 1080x720(3:2 720p)/30fps に揃えてから連結（カットごとの差異を吸収）。
    pre = "".join(
        f"[{i}:v]scale=1080:720:force_original_aspect_ratio=decrease,"
        f"pad=1080:720:(ow-iw)/2:(oh-ih)/2,fps=30,setsar=1[v{i}];"
        for i in range(n)
    )
    cat = "".join(f"[v{i}]" for i in range(n)) + f"concat=n={n}:v=1:a=0[v]"
    subprocess.run(
        [FFMPEG, "-y", *inputs,
         "-filter_complex", pre + cat,
         "-map", "[v]", "-map", f"{n}:a",
         "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac",
         "-shortest", str(out)],
        check=True,
    )
    return out
