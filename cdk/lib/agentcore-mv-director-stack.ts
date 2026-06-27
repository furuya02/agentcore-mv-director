import * as path from "path";
import { Stack, StackProps, RemovalPolicy, CfnOutput } from "aws-cdk-lib";
import { Construct } from "constructs";
import * as s3 from "aws-cdk-lib/aws-s3";
import * as secretsmanager from "aws-cdk-lib/aws-secretsmanager";
import * as iam from "aws-cdk-lib/aws-iam";
import * as agentcore from "aws-cdk-lib/aws-bedrockagentcore";

const PROJECT = "agentcore-mv-director";

export class AgentcoreMvDirectorStack extends Stack {
  constructor(scope: Construct, id: string, props?: StackProps) {
    super(scope, id, props);

    // 命名規約: {プロジェクト名}-{アカウントID}。-c bucket_suffix=YYYYMMDD で差し替え可（差し替えた場合はその値を使用）。
    const suffix: string = this.node.tryGetContext("bucket_suffix") ?? this.account;

    const dryRun: string = this.node.tryGetContext("dry_run") ?? "0";

    // 完成MVの出力先（放置コスト回避: 破棄しやすく）
    const bucket = new s3.Bucket(this, "MvBucket", {
      bucketName: `${PROJECT}-${suffix}`,
      removalPolicy: RemovalPolicy.DESTROY,
      autoDeleteObjects: true,
      blockPublicAccess: s3.BlockPublicAccess.BLOCK_ALL,
    });

    // APIキー保管（デプロイ後に aws secretsmanager put-secret-value で実値を投入）
    const secret = new secretsmanager.Secret(this, "ApiKeys", {
      secretName: `${PROJECT}-api-keys`,
      description: "FAL_KEY / ELEVENLABS_API_KEY for agentcore-mv-director",
    });

    // AgentCore Runtime 実行ロール
    const role = new iam.Role(this, "RuntimeRole", {
      roleName: `${PROJECT}-runtime-role`,
      assumedBy: new iam.ServicePrincipal("bedrock-agentcore.amazonaws.com"),
      inlinePolicies: {
        S3Access: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              actions: ["s3:PutObject", "s3:GetObject", "s3:DeleteObject", "s3:ListBucket"],
              resources: [bucket.bucketArn, `${bucket.bucketArn}/*`],
            }),
          ],
        }),
        SecretAccess: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              actions: ["secretsmanager:GetSecretValue"],
              resources: [secret.secretArn],
            }),
          ],
        }),
        BedrockAccess: new iam.PolicyDocument({
          statements: [
            new iam.PolicyStatement({
              actions: ["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
              resources: ["*"],
            }),
          ],
        }),
      },
    });

    // コンテナイメージ：リポジトリ直下を buildContext にして mvcore/ を直接 COPY
    const artifact = agentcore.AgentRuntimeArtifact.fromAsset(
      path.join(__dirname, "..", ".."),  // リポジトリ直下（cdk/lib/ → cdk/ → ./）
    );

    // AgentCore Runtime
    const runtime = new agentcore.Runtime(this, "MvDirectorRuntime", {
      runtimeName: "agentcore_mv_director",
      agentRuntimeArtifact: artifact,
      executionRole: role,
      environmentVariables: {
        DRY_RUN: dryRun,
        S3_BUCKET: bucket.bucketName,
        SECRET_ARN: secret.secretArn,
        OUTPUT_DIR: "/tmp/output",
      },
    });

    new CfnOutput(this, "BucketName", { value: bucket.bucketName });
    new CfnOutput(this, "SecretArn", { value: secret.secretArn });
    new CfnOutput(this, "RuntimeArn", { value: runtime.agentRuntimeArn });
  }
}
