"""AgentCore Runtime にデプロイする Director Agent（入口②）。

コンセプト → Bedrock(Claude) が絵コンテ＋作詞を生成 → 共通 pipeline で MV 化する。
頭脳は src/director.py に分離（ローカル検証は scripts/agent_local.py）。
デプロイは AgentCore CLI: `agentcore deploy`。
"""
from bedrock_agentcore.runtime import BedrockAgentCoreApp
from .director import generate_storyboard
from .pipeline import run_pipeline

app = BedrockAgentCoreApp()


@app.entrypoint
def invoke(payload: dict) -> dict:
    concept = payload.get("concept", "夜の東京を舞台にしたシティポップのMV")
    sb = generate_storyboard(concept)        # Bedrock が絵コンテ＋作詞
    result = run_pipeline(sb)                 # ローカルと同じ pipeline で MV 化
    return {"title": sb.title, "mv_path": str(result["mv"]), "s3_uri": result["s3_uri"]}


if __name__ == "__main__":
    app.run()
