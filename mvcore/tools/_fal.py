"""fal の結果JSONから動画URLを取り出すヘルパー（モデルでネスト形が違うのを吸収）。"""


def video_url(out_json: dict) -> str:
    if "detail" in out_json:  # fal のエラー応答（face_detection_error 等）
        raise RuntimeError(f"fal error: {out_json['detail']}")
    node = out_json.get("data", out_json)  # data でラップされる場合に対応
    v = node.get("video")
    if isinstance(v, dict) and v.get("url"):
        return v["url"]
    if isinstance(v, str):
        return v
    if node.get("video_url"):
        return node["video_url"]
    raise KeyError(f"動画URLが見つかりません: keys={list(out_json.keys())} json={out_json}")
