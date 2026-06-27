#!/usr/bin/env node
import * as cdk from "aws-cdk-lib";
import { AgentcoreMvDirectorStack } from "../lib/agentcore-mv-director-stack";

const app = new cdk.App();
new AgentcoreMvDirectorStack(app, "AgentcoreMvDirectorStack", {
  env: {
    account: process.env.CDK_DEFAULT_ACCOUNT ?? process.env.AWS_ACCOUNT_ID,
    region: process.env.CDK_DEFAULT_REGION ?? process.env.AWS_DEFAULT_REGION ?? "ap-northeast-1",
  },
});
