"""ドライラン（課金なし）でパイプラインとバリデーションを検証する。

    DRY_RUN=1 python -m pytest -q
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ["DRY_RUN"] = "1"  # import 前に強制ドライラン
os.environ["OUTPUT_DIR"] = tempfile.mkdtemp()  # 本番 output/ を汚さない
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402
from src.schema import stub_storyboard, validate_storyboard  # noqa: E402
from src.pipeline import run_pipeline  # noqa: E402


def test_dryrun_pipeline_produces_mv():
    result = run_pipeline(stub_storyboard("夜の東京のシティポップ"))
    assert result["mv"].exists()
    assert result["s3_uri"].startswith("s3://")


def test_validate_allows_no_singing_cut():
    # 複数画像モードでは顔が無い＝歌唱カット無しも許容される
    sb = stub_storyboard("x")
    for c in sb.cuts:
        c.is_singing = False
    validate_storyboard(sb)  # 例外を投げない


def test_validate_requires_lyrics():
    sb = stub_storyboard("x")
    sb.music["lyrics"] = ""
    with pytest.raises(ValueError):
        validate_storyboard(sb)
