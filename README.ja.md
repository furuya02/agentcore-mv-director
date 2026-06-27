# agentcore-mv-director

Amazon Bedrock AgentCore 上で動く「クリエイティブ・ディレクター」AIエージェント。
S3 に画像を置いて空のペイロードを送るだけで、エージェントが自動でコンセプトを生成し、
複数カットの動画＋楽曲を生成して1本のMVに仕上げます（PoC）。

- **コンセプト自動生成**: Claude vision が入力画像を分析してMVコンセプトを自動生成
- **リップシンク自動判定**: Claude vision が各画像を分析し、人物がカメラ目線でアップに映っているカットのみリップシンクを適用（ファイル名の命名規則不要）
- **作詞**: Bedrock（Claude）がコンセプトに合う英語歌詞をオリジナルで生成
- **楽曲**: ElevenLabs Music v2（デフォルトは女性ボーカル）
- **動画**: fal.ai PixVerse v5 image-to-video（カット別）
- **リップシンク**: fal.ai Kling LipSync（フルミックス対応・ステム分離不要）
- **連結**: FFmpeg
- **出力**: Amazon S3（`output/mv.mp4`）
- **Observability**: CloudWatch ログ＋ OpenTelemetry トレース（AgentCore 組み込み）
- **二重実行防止**: S3 ロックファイルで並列 invocation をブロック（fal.ai / ElevenLabs の課金保護）

## アーキテクチャ

![アーキテクチャ](docs/architecture-agentcore.png)

## 構成

```
main_agentcore.py   # AgentCore エントリポイント（@app.entrypoint）
src/
  director.py       # Bedrock（Claude）— コンセプト生成・リップシンク判定・絵コンテ・作詞
  pipeline.py       # 絵コンテ → MV のオーケストレーション
  schema.py         # 絵コンテ(Storyboard)スキーマ・検証
  config.py         # 設定（キー無しなら自動ドライラン）
  tools/            # music / video / lipsync / assemble / storage（S3）
cdk/                # S3 / Secrets Manager / IAM / AgentCore Runtime（TypeScript）
```

## セットアップ

### 1. Clone & CDK デプロイ

```bash
git clone https://github.com/furuya02/agentcore-mv-director.git
cd agentcore-mv-director/cdk
pnpm install
pnpm run cdk deploy -- --require-approval never
```

### 2. APIキーを Secrets Manager に投入

```bash
aws secretsmanager put-secret-value \
  --secret-id agentcore-mv-director-api-keys \
  --secret-string '{"FAL_KEY":"...","ELEVENLABS_API_KEY":"..."}'
```

### 3. 入力画像を S3 にアップロード

```bash
aws s3 cp input/ s3://agentcore-mv-director-<ACCOUNT_ID>/input/ --recursive
```

ファイル名は自由です。Claude vision が各画像を分析してリップシンク対象を自動判定するため、
`_sing` などの命名規則は不要です。

## 実行

```bash
echo '{}' > /tmp/payload.json

aws bedrock-agentcore invoke-agent-runtime \
  --agent-runtime-arn "<RUNTIME_ARN>" \
  --payload fileb:///tmp/payload.json \
  --cli-read-timeout 0 \
  --region ap-northeast-1 \
  /tmp/response.json && cat /tmp/response.json
```

空ペイロード `{}` のデフォルト動作：

| ステップ | 内容 |
|---------|------|
| 画像 | `s3://<bucket>/input/` から自動取得 |
| コンセプト | Claude vision が全画像を分析して自動生成 |
| リップシンク | Claude vision が各画像を判定 — カメラ目線のアップ → リップシンク適用 |
| 作詞 | Bedrock がコンセプトに合う英語歌詞をオリジナル生成 |
| ボーカル | 女性ボーカル |

### ペイロードパラメータ（全て省略可能）

| パラメータ | デフォルト | 説明 |
|-----------|-----------|------|
| `concept` | 自動生成（画像から） | コンセプトを手動で指定する場合 |
| `images_s3_prefix` | `s3://<bucket>/input/` | 入力画像の S3 プレフィックス |
| `ai_lyrics` | `true` | Bedrock で歌詞を自動生成 |
| `vocal` | `"female"` | `"male"` または `"female"` |
| `length` | `24` | MV の長さ（秒）単一画像モード時 |

## Observability

```bash
aws logs tail "/aws/bedrock-agentcore/runtimes/<agent_id>-DEFAULT" \
  --follow --format short --region ap-northeast-1
```

## 片付け（放置コスト回避）

```bash
cd cdk && pnpm run cdk destroy
```

## コスト

- 動画生成: カットあたり $0.05〜0.10（fal.ai PixVerse v5）
- リップシンク: 歌唱カットあたり $0.05（fal.ai Kling）
- 楽曲生成: 1トラックあたり $0.03（ElevenLabs Music v2）
- AgentCore: 消費ベース課金（I/O 待機は無課金）
- 生成楽曲はMV内BGM用途のみ。音楽配信サービスへの楽曲投稿は不可（ElevenLabs 規約）
