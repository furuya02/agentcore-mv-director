"""完成MVを S3 にアップロードする（最小実装）。

ドライラン、または S3_BUCKET 未設定なら実アップロードせず、想定先 URI を返す（課金なし）。
"""
from pathlib import Path
from ..config import DRY_RUN, S3_BUCKET


def upload_to_s3(path: Path, prefix: str = "output") -> str:
    """ローカルファイルを S3 にアップロードし、s3:// URI を返す。"""
    key = f"{prefix}/{path.name}"
    if DRY_RUN or not S3_BUCKET:
        bucket = S3_BUCKET or "<S3_BUCKET未設定>"
        return f"s3://{bucket}/{key}  (DRY_RUN: 未アップロード)"

    import boto3  # 実行時のみ依存

    boto3.client("s3").upload_file(str(path), S3_BUCKET, key)
    return f"s3://{S3_BUCKET}/{key}"
