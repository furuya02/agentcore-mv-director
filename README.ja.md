# agentcore-mv-director

Amazon Bedrock AgentCore 上で動く「クリエイティブ・ディレクター」AIエージェント。
1つのコンセプト（例：「夜の東京を舞台にしたシティポップのMV」）から、絵コンテと歌詞を生成し、
複数カットの動画＋楽曲を自動生成して1本のMVに仕上げる PoC です。

- Director Agent（Strands Agents / Python）が絵コンテ＋作詞を構造化出力
- 楽曲：ElevenLabs Music v2（歌入り）
- 動画：fal.ai（カット別モデル、last frame→次カット開始フレームの連鎖）
- 歌唱カット：fal.ai Kling LipSync（ステム分離不要・フルミックスで同期）
- 連結：FFmpeg（AgentCore Code Interpreter 想定）
- 出力：Amazon S3／思考トレースは CloudWatch（AgentCore Observability）で可視化

アーキテクチャ図：[../Blog/architecture.png](../Blog/architecture.png)（編集元: `../Blog/architecture.drawio`）

## 構成

```
src/
  agent.py        # AgentCore エントリポイント（Strands Director Agent）
  pipeline.py     # 絵コンテ → MV のオーケストレーション（バリデーション込み）
  schema.py       # 絵コンテ(Storyboard)スキーマ・検証・スタブ
  config.py       # 設定（キー無しなら自動ドライラン）
  tools/          # music / video / lipsync / assemble / storage(S3)
scripts/
  dryrun.py       # 常に課金なしの疎通確認（鍵があっても叩かない）
  test_music.py   # (a) 最小コスト実APIテスト（ElevenLabs 楽曲1本）
  test_video.py   # (b) 最小コスト実APIテスト（fal LTX 動画1カット）
  run.py          # (c) 実APIでフルパイプライン1本（課金あり）
tests/            # ドライランの自動テスト（pytest）
cdk/              # S3 / Secrets Manager / IAM（TypeScript）
```

## セットアップ

```bash
git clone <REPO_URL>
cd agentcore-mv-director
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## 動作確認（ドライラン・課金なし）

APIキーが無くても、パイプライン全体がプレースホルダで流れます。

```bash
DRY_RUN=1 python -m scripts.dryrun
```

`output/` に各カット・楽曲・完成MVのプレースホルダが生成され、処理の流れを確認できます。

### テスト（課金なし）

```bash
python -m pytest -q
```

ドライランでパイプライン疎通と絵コンテのバリデーション（歌唱カット必須・作詞必須など）を検証します。

## 実行（実API・従量課金）

鍵は **ツールごとに判定**されます（`ELEVENLABS_API_KEY` のみ設定すれば楽曲だけ実行、
`FAL_KEY` 未設定なら動画はプレースホルダ）。`scripts/dryrun.py` は鍵があっても課金しません。

```bash
cp .env.example .env   # キーを記入
set -a && source .env && set +a

# (a) ElevenLabs 楽曲1本（概算 $0.03）
python -m scripts.test_music

# (b) fal LTX 動画1カット（概算 $0.04）
python -m scripts.test_video

# (c) フルパイプライン（LTX×3カット＋リップシンク。概算 $0.1〜）
python -m scripts.run "夜の東京のシティポップ"

# (c') 単一の初期画像から開始（全カットをその画像から生成し、人物・画風を固定）
python -m scripts.run "夜の東京のシティポップ" --image input/first.png

# (c'') 複数画像モード（input/ の各画像=1カット。顔が検出された画像のみリップシンク）
python -m scripts.run "夜の東京のシティポップ" --images input

# (c''') 1画像→連続生成モード（i2v 8秒[先頭リップシンク]＋extend×N で1本の連続動画）
python -m scripts.run "夜の東京のシティポップ" --image input/first0.png --extend 2
```

## AWSリソース（CDK）

S3バケット（MV出力先）・Secrets Manager（APIキー）・IAMポリシーを CDK で作成する。
※エージェント本体のデプロイは CDK ではなく AgentCore CLI（後述）。

```bash
cd cdk
pnpm install
# 命名は agentcore-mv-director-{アカウントID}。-c bucket_suffix=YYYYMMDD で差し替え可。
pnpm exec cdk deploy -c bucket_suffix=20260623
```

デプロイ後、APIキーを Secrets Manager に投入：

```bash
aws secretsmanager put-secret-value \
  --secret-id agentcore-mv-director-api-keys \
  --secret-string '{"FAL_KEY":"...","ELEVENLABS_API_KEY":"..."}'
```

出力（Outputs）の `RuntimePolicyArn` を AgentCore Runtime の実行ロールにアタッチする。

片付け（放置コスト回避）：

```bash
pnpm exec cdk destroy
```

## デプロイ（AgentCore CLI）

エージェント本体は AgentCore CLI（`@aws/agentcore`）でデプロイ。※npm/npx は使わず pnpm を使用。

```bash
pnpm add -g @aws/agentcore
agentcore deploy
agentcore invoke '{"concept": "夜の東京を舞台にしたシティポップのMV"}'
```

## Observability（思考トレースの可視化）

AgentCore Runtime にデプロイしたエージェントは OpenTelemetry で自動計装され、
絵コンテ判断・モデル選択・ツール呼び出しのトレースを CloudWatch で確認できます。

1. アカウントで一度だけ CloudWatch Transaction Search を有効化（初回のみ）：
   ```bash
   aws xray update-trace-segment-destination --destination CloudWatchLogs
   ```
   （コンソールの場合：CloudWatch → Settings → Transaction Search → Enable）
2. `agentcore deploy` でデプロイ（OTel 自動計装。追加ライブラリ不要）
3. CloudWatch コンソールの「GenAI Observability」→ Trace View で、エージェントの
   思考過程・ツール呼び出しのタイムラインを確認

ログは `/aws/bedrock-agentcore/runtimes/<agent_id>-<endpoint>/...` に出力されます。

## コストと注意

- 動画生成は試行回数でコストが伸びます。実API実行前に生成回数・上限を決めてください。
- AgentCore は消費ベース課金（I/O待機は無課金）。常駐課金はありません。
- 生成楽曲は MV 内 BGM 用途のみ。音楽配信サービスへの楽曲投稿は不可（ElevenLabs 規約）。
