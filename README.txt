AgentCore Desktop 交付说明
========================

1) AgentCore-Desktop-source.zip
   - 源代码（含 bridge / agent-service / patches / README / 已打补丁的 ZCode + agentscope）
   - 已排除 node_modules、dist、.venv、.git、.env、mock-cdn 等

2) AgentCore-Desktop-3.15.1-linux-amd64.deb
   - Linux amd64 安装包（.deb）
   - 注意：这是 Linux 安装包，不能直接在 Windows 上安装。
   - 可在 WSL / Ubuntu 等 Linux 环境中安装使用。
   - Windows 安装包需另行在 Windows 上构建或通过 CI 打包。

配置与密钥请参考源码包内 README，勿把 API Key 提交进仓库。
