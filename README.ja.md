# agentcore-mv-director

Amazon Bedrock AgentCore 上で動く「クリエイティブ・ディレクター」AIエージェント。
S3 に画像を置いて空のペイロードを送るだけで、**Strands Agent（Claude）が自律的にオーケストレーション**し、コンセプト生成・作詞・マルチカット動画・楽曲を1本のMVに仕上げます（PoC）。

- **AIオーケストレーション**: Strands Agent（Claude）がどのツールをいつ呼ぶかを自律的に判断
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
main_agentcore.py             # AgentCore エントリポイント — Strands Agent + 4ツール
  ├─ download_input_images    # S3 input/ から画像をダウンロード
  ├─ generate_mv_concept      # Claude vision → MVコンセプト生成
  ├─ generate_music_and_lyrics # Claude → 楽曲スタイル＋歌詞生成
  └─ produce_music_video      # 絵コンテ組み立て＋パイプライン実行 → S3出力
src/
  director.py       # Bedrock（Claude）— コンセプト生成・リップシンク判定・絵コンテ・作詞
  pipeline.py       # 絵コンテ → MV のパイプライン
  schema.py         # 絵コンテ(Storyboard)スキーマ・検証
  config.py         # 設定（キー無しなら自動ドライラン）
  tools/            # music / video / lipsync / assemble / storage（S3）
cdk/                # S3 / Secrets Manager / IAM / AgentCore Runtime（TypeScript）
scripts/            # ローカル実行（開発・テスト用）
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

ファイル名はカットの順番通りに連番（`1.jpg`, `2.jpg`, …）にしてください。
Claude vision が各画像を分析してリップシンク対象を自動判定するため、命名規則は不要です。

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

ペイロードは空の `{}` だけで十分です。Strands Agent（Claude）が全てを自律的に処理します：

| ステップ | Claude が判断する内容 |
|---------|-------------------|
| 画像 | `s3://<bucket>/input/` からファイル名の数字順に取得 |
| コンセプト | Claude vision が全画像を分析して自動生成 |
| 楽曲・歌詞 | Claude がコンセプトに合う楽曲スタイルと英語歌詞を生成 |
| リップシンク | Claude vision が各画像を判定 — カメラ目線のアップ → リップシンク適用 |
| ボーカル | 女性ボーカル（固定） |

## Observability

```bash
aws logs tail "/aws/bedrock-agentcore/runtimes/<agent_id>-DEFAULT" \
  --follow --format short --region ap-northeast-1
```

各ツールは開始・判断内容・結果を詳細にログ出力します。例：

```
============================================================
[tool:start] generate_mv_concept
  対象画像: 3枚
[tool:done] generate_mv_concept
  → コンセプト: A cinematic journey through sun-drenched streets...
============================================================
[tool:start] produce_music_video
  [絵コンテ完成] 3カット / 総尺 24秒
    cut1: 8秒 [✓ リップシンク対象] portrait of woman looking directly at camera...
    cut2: 8秒 [  映像のみ        ] panoramic view of golden hills at sunset...
[tool:done] produce_music_video
  → S3 URI: s3://agentcore-mv-director-<ACCOUNT_ID>/output/mv.mp4
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
