# ローカル実行ガイド（コマンド一覧）

ローカルから `scripts/run.py` 等でMVを生成する方法。AgentCore へデプロイした後も、このローカル実行はそのまま使える。

## 構成（どのプログラムが動くか）

`scripts/` は**ローカル実行（コマンド）専用の入口**。実際の生成ロジックは `src/` にあり、ローカルCLI（`scripts/`）と AgentCore（`src/agent.py`）が**同じ `src/` のコアを共有**する。

```
python -m scripts.run ...           ← ローカルCLIの入口（scripts/run.py）
        │
        ├─ src/config.py            … 設定（キー・DRY_RUN・REUSE 等）
        ├─ src/schema.py            … 絵コンテ組み立て（storyboard_from_images / stub_storyboard）
        ├─ src/director.py          … ★--ai-lyrics の時だけ Bedrock(Claude) で作詞
        ▼
        src/pipeline.py             … オーケストレーション（run_pipeline / run_image_extend）
        ├─ src/tools/music.py       → ElevenLabs（楽曲）
        ├─ src/tools/video.py       → fal/PixVerse（動画・延長）＋ ローカルffmpeg
        ├─ src/tools/lipsync.py     → fal/Kling LipSync
        ├─ src/tools/assemble.py    → ローカルffmpeg（連結・音声合成・分割）
        └─ src/tools/storage.py     → S3（S3_BUCKET 設定時のみ）
```

| 入口 | 用途 |
|---|---|
| `scripts/run.py` | MV生成のメイン（このガイドの対象） |
| `scripts/dryrun.py` / `test_music.py` / `test_video.py` | 疎通・最小テスト |
| `scripts/agent_local.py` | Director Agent(Bedrock)をローカルで試す（デプロイ前検証） |
| `src/agent.py` | AgentCore Runtime 用の入口（`agentcore deploy` 専用。`scripts.run` では動かない） |

- **Bedrock(Claude) が動くのは `--ai-lyrics` の時だけ**。付けなければ AWS なしで動く。
- `DRY_RUN=1` なら外部API（fal/ElevenLabs/S3）は呼ばずプレースホルダで流れる（課金なし）。

## 0. 準備（初回のみ）

```bash
cd agentcore-mv-director
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # strands / bedrock-agentcore / httpx / boto3 / fal-client / opencv-python / pytest
cp .env.example .env                      # キーを記入
```

`.env` に設定するもの：
```
FAL_KEY=...                  # fal.ai（動画・リップシンク）
ELEVENLABS_API_KEY=...       # ElevenLabs（楽曲）※Music API は Starter($6)以上が必要
FFMPEG_BIN=/Applications/ffmpeg   # ffmpeg実体パス（zsh alias は subprocess から見えないため）
# S3_BUCKET=...              # 設定すると完成MVをS3にアップロード（未設定ならローカルのみ）
```

実行前は毎回キーを読み込む：
```bash
set -a && source .env && set +a
```

## 1. 課金なしで確認する

```bash
DRY_RUN=1 python -m scripts.dryrun    # パイプライン全体をプレースホルダで疎通（常に無料）
python -m pytest -q                   # 自動テスト（ドライラン・output/ は汚さない）
```

## 2. 最小コストの実APIテスト

```bash
python -m scripts.test_music    # (a) ElevenLabsで楽曲1本（約$0.03）
python -m scripts.test_video    # (b) fal で動画1カット（fal疎通確認）
```

## 3. MVを生成する（実API・課金あり）

### モードA：複数画像（各画像＝1シーン、`sing_` で始まる画像のみリップシンク）
```bash
python -m scripts.run "夜の東京を舞台にしたシティポップのMV" --images input
# 作詞もコンセプトから AI に任せる場合：
python -m scripts.run "夜の東京..." --images input --ai-lyrics
```
- `input/` の各画像が**1シーン＝8秒**。**総尺 ＝ 8 × 画像枚数**（3枚→24秒 / 5枚→40秒）。
- **順番はファイル名中の数字（連番）で決まる**。
- **ファイル名に `sing` を含む画像だけ**、その時間帯の歌声でリップシンク。
  それ以外（後ろ向き・風景など）は映像のみ。
  - 例：`01.png`（1番・映像）→ `02_sing.png`（2番・歌唱）→ `03.png`（3番・映像）＝24秒
- **画像が1枚だけ**のときは既定で**24秒**（同じ画像を8秒×3に複製）。`--length 秒` で変更可（8の倍数に丸め。例 `--length 40` で40秒＝8×5）。
- `--ai-lyrics`：作詞・楽曲スタイルをコンセプトから Bedrock(Claude) で生成（要 AWS/Bedrock）。
- ※ `sing` を付けた画像は**正面の顔が必要**（リップシンクは内部で顔検出するため）。

### モードB：1画像から連続生成（extend＋全編リップシンク）
```bash
python -m scripts.run "夜の東京..." --image input/001.png --extend 2
```
- 8×(1+2)=24秒の**連続動画**。8秒チャンクごとに全編リップシンク。
- `--extend 1` なら16秒、`--extend 2` なら24秒。

### モードC：1画像を起点（extendなし・スタブ絵コンテ）
```bash
python -m scripts.run "夜の東京..." --image input/001.png
```

### モードD：画像なし（text-to-video のスタブ絵コンテ）
```bash
python -m scripts.run "夜の東京..."
```

### コマンドフラグ

| フラグ | 効果 | 例 |
|---|---|---|
| `--vocal male/female` | ボーカルの性別を指定（楽曲プロンプトに反映。全モード可） | `--images input --vocal male` |
| `--ai-lyrics` | 作詞・楽曲スタイルをコンセプトから Bedrock(Claude) で生成（要 AWS/Bedrock） | `--images input --ai-lyrics` |
| `--length 秒` | `--images` で画像1枚のときのMV尺（8の倍数に丸め。既定24） | `--images input1 --length 40` |
| `--extend N` | `--image` と併用。連続延長＋全編リップシンク | `--image input/01.png --extend 2` |

## 4. よく使うオプション（環境変数）

| 変数 | 効果 | 例 |
|---|---|---|
| `OUTPUT_DIR` | 出力先フォルダを変える（`output/` を上書きしない／並行実行可） | `OUTPUT_DIR=out_a python -m scripts.run ...` |
| `REUSE=1` | 生成済みファイルを再利用。失敗時の**途中再開**や再連結に使う | `REUSE=1 python -m scripts.run ...` |
| `DRY_RUN=1` | 全ツール強制ドライラン（課金なし） | `DRY_RUN=1 python -m scripts.run ...` |
| `FFMPEG_BIN` | ffmpeg 実体パス | `FFMPEG_BIN=/Applications/ffmpeg` |
| `S3_BUCKET` | 完成MVをS3へアップロード | `S3_BUCKET=agentcore-mv-director-20260623` |

動画の解像度は `src/tools/video.py` の `PIXVERSE_RESOLUTION`（既定 `720p`、軽くするなら `540p`）。

## 5. 並行実行・出力の分け方

`OUTPUT_DIR` を分ければ**並行実行OK**（出力は混ざらない）。別画像で並行するなら**入力フォルダも分ける**こと（画像は実行中に読まれるため）。
```bash
# ターミナル1
OUTPUT_DIR=out_a python -m scripts.run "..." --images input_a
# ターミナル2
OUTPUT_DIR=out_b python -m scripts.run "..." --image input_b/x.png --extend 2
```
共有されるのは API アカウント（コスト・レート）と FAL_KEY（読み取り専用）のみ。

## 6. 時間・コストの目安

- 動画生成（PixVerse 720p）：1カット 数十秒〜数分。
- **リップシンク（Kling LipSync）：1チャンク約12分**。顔チャンク数 × 12分かかる。
- 例：`--images input`（3枚・全部顔）→ リップシンク3回で約36分。
- 途中タイムアウトは `REUSE=1` を付けて同じコマンドで再開。

## 7. 出力物

- 完成MV：`<OUTPUT_DIR>/mv.mp4`（既定 `output/mv.mp4`）
- 中間物：`cutN.mp4`（動画）、`cutN_lipsync.mp4`（同期済み）、`_chunkN.mp4`（分割）、`_segN.mp3`（音声切片）、`music.mp3`（楽曲）

## 8. 生成のルール

破綻しにくい構成の原則は [generation-rules.md](./generation-rules.md) を参照。
