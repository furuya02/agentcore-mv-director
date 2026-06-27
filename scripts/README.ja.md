# scripts — ローカル実行ガイド

> **注意**: AgentCore Runtime のエントリポイント（`main_agentcore.py`）は **Strands Agent AIオーケストレーション** を使用しており、Claude が自律的にツールを選択します。このスクリプト群は**ローカル開発・テスト用**で、Python の固定パイプラインとして動作します。

AgentCore Runtime にデプロイせず、ローカルから直接パイプラインを実行する方法です。
`src/` のコアはローカルCLI（`scripts/`）と AgentCore Runtime（`main_agentcore.py`）で共有されています。

```
python -m scripts.run ...           ← ローカルCLIの入口
        │
        ├─ src/config.py            … 設定（キー・DRY_RUN・REUSE など）
        ├─ src/schema.py            … 絵コンテ組み立て
        ├─ src/director.py          … Bedrock（Claude）— コンセプト生成・リップシンク判定・作詞
        ▼
        src/pipeline.py             … オーケストレーション（run_pipeline / run_image_extend）
        ├─ src/tools/music.py       → ElevenLabs（楽曲）
        ├─ src/tools/video.py       → fal / PixVerse（動画・延長）
        ├─ src/tools/lipsync.py     → fal / Kling LipSync
        ├─ src/tools/assemble.py    → FFmpeg（連結・音声合成・分割）
        └─ src/tools/storage.py     → S3（S3_BUCKET 設定時のみ）
```

## 0. 準備（初回のみ）

```bash
cd agentcore-mv-director
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # キーを記入
```

`.env` に設定するもの：

```
FAL_KEY=...                       # fal.ai（動画・リップシンク）
ELEVENLABS_API_KEY=...            # ElevenLabs（楽曲）※ Starter プラン（$6/月）以上が必要
FFMPEG_BIN=/Applications/ffmpeg   # ffmpeg 実体のフルパス
# S3_BUCKET=...                   # 完成MV を S3 へアップロード（未設定ならローカルのみ）
```

実行前は毎回キーを読み込む：

```bash
set -a && source .env && set +a
```

## 1. 課金なしで確認する

```bash
DRY_RUN=1 python -m scripts.dryrun    # パイプライン全体をプレースホルダで疎通（常に無料）
python -m pytest -q                    # 自動テスト（ドライラン）
```

## 2. 最小コストの実API テスト

```bash
python -m scripts.test_music    # (a) ElevenLabs で楽曲1本（約 $0.03）
python -m scripts.test_video    # (b) fal で動画1カット
```

## 3. MV を生成する（実API・課金あり）

### モードA：複数画像（各画像＝8秒1カット）

```bash
python -m scripts.run "地中海の夏を舞台にした夏ポップMV" --images input
# Bedrock で作詞する場合：
python -m scripts.run "地中海の夏を舞台にした夏ポップMV" --images input --ai-lyrics
```

- `input/` の各画像が 8 秒 1 カットになります。総尺 ＝ 8 × 画像枚数。
- **リップシンク対象は Claude vision が自動判定** — 人物がカメラ目線でアップに映っている画像のみリップシンクを適用。ファイル名の命名規則は不要。
- 並び順はファイル名中の数字（昇順）で決まります。
- 画像が1枚のときは既定で 24 秒（同じ画像を複製）。`--length` で変更可。

### モードB：1画像から連続生成（extend＋全編リップシンク）

```bash
python -m scripts.run "地中海の夏..." --image input/01.png --extend 2
```

8 × (1 + 2) = 24 秒の連続動画。8 秒チャンクごとに全編リップシンクを適用。

### モードC：1画像（extend なし）

```bash
python -m scripts.run "地中海の夏..." --image input/01.png
```

### モードD：画像なし（text-to-video スタブ絵コンテ）

```bash
python -m scripts.run "地中海の夏..."
```

### フラグ一覧

| フラグ | 効果 |
|--------|------|
| `--vocal male\|female` | ボーカルの性別を指定 |
| `--ai-lyrics` | Bedrock（Claude）で歌詞を自動生成 |
| `--length 秒` | 単一画像モード時のMV尺（8の倍数に丸め・既定24） |
| `--extend N` | 連続延長モード（`--image` と併用） |

## 4. よく使う環境変数

| 変数 | 効果 |
|------|------|
| `OUTPUT_DIR` | 出力先フォルダを変更（既定 `output/`） |
| `REUSE=1` | 生成済みファイルを再利用 — 失敗後の途中再開に使う |
| `DRY_RUN=1` | 全ツール強制ドライラン（課金なし） |
| `FFMPEG_BIN` | ffmpeg 実体のフルパス |
| `S3_BUCKET` | 完成MV を S3 へアップロード |

## 5. 並行実行

`OUTPUT_DIR` と入力フォルダを分けることで並行実行が可能です：

```bash
# ターミナル1
OUTPUT_DIR=out_a python -m scripts.run "..." --images input_a
# ターミナル2
OUTPUT_DIR=out_b python -m scripts.run "..." --image input_b/x.png --extend 2
```

## 6. 時間・コストの目安

| ステップ | 所要時間 | コスト |
|---------|---------|--------|
| PixVerse v5 動画生成（720p・8秒） | 30秒〜2分/カット | 約 $0.05〜0.10 |
| Kling LipSync | 約5〜15分/チャンク | 約 $0.05 |
| ElevenLabs Music v2 | 約30秒 | 約 $0.03 |

途中でタイムアウトした場合は `REUSE=1` を付けて同じコマンドを再実行すると途中から再開できます。

## 7. 出力物

| ファイル | 内容 |
|---------|------|
| `<OUTPUT_DIR>/mv.mp4` | 完成MV |
| `cutN.mp4` | カット別動画 |
| `cutN_lipsync.mp4` | リップシンク適用済みカット |
| `music.mp3` | 生成楽曲 |
| `_segN.mp3` | カット別音声セグメント |

## 8. 生成のルール

破綻しにくい構成の原則は [generation-rules.md](../docs/generation-rules.md) を参照してください。
