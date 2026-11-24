AgentCore Desktop 仓库说明
========================

本 GitHub 仓库提供源代码（含 bridge / agent-service / patches / 已适配的 ZCode 与 agentscope）。
仓库内不包含安装包，也不应把 .env、gateway.json 或 API Key 提交进来。

测试（无需云端密钥，与 CI 相同）：

  ./scripts/run-tests.sh

开发与构建的准确步骤、以及“什么已测 / 什么未测”见：

  docs/开发与构建.md
  docs/迭代记录.md
  agent-service/README.md

Windows / macOS / Linux 安装包需要在对应系统上按 ZCode 桌面打包流程另行构建，
并在目标机器上手工验证。请勿假设本仓库已附带可安装的 Setup.exe。
