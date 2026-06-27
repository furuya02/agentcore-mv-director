"""完成MVを S3 にアップロードする（最小実装）。"""
from pathlib import Path
from ..config import S3_BUCKET


def upload_to_s3(path: Path, prefix: str = "output") -> str:
    """ローカルファイルを S3 にアップロードし、s3:// URI を返す。"""
    key = f"{prefix}/{path.name}"
    if not S3_BUCKET:
        return f"s3://<S3_BUCKET未設定>/{key}"

    import boto3  # 実行時のみ依存

    boto3.client("s3").upload_file(str(path), S3_BUCKET, key)
    return f"s3://{S3_BUCKET}/{key}"
