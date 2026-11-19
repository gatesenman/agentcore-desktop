# AgentCore Desktop

基于 **ZCode**（智谱开源 AI 编程工作台，Electron + React）前端体系，接入**可插拔 Agent 后端**的跨平台桌面应用：
AgentScope（阿里开源）、阿里云 AgentCore（托管模型）、AG-UI 协议服务、任意 OpenAI 兼容服务，以及离线 mock。

## 架构

```
ZCode UI (React, 桌面/Web 共用)
  └─ ZCode Host / Server（packages/services）
       └─ [后端开关] bridge/agent-bridge.mjs   ← stdio 适配器（协议帧原样透传）
            ├─ ZCode Agent Runtime（产生 ZCode Protocol v4，负责工具执行：Read/Bash/Edit…）
            │    └─ 模型 Provider「Agent Gateway」(OpenAI 兼容, 127.0.0.1:18765)
            └─ agent-service（Python FastAPI 网关，打包后为 PyInstaller 可执行文件）
                 └─ Backend 插件：mock | agentscope | agentcore | agui | openai | <你的框架>
```

- ZCode 的工具调用以 OpenAI `tools / tool_calls` 透传到后端：后端只负责“下一步说什么/调哪个工具”，工具由 ZCode 执行。
- 网关同时提供 `/v1/chat/completions`（OpenAI 兼容）、`/agui`（AG-UI 事件流）、`/settings`（后端选择页面）。

## 目录

| 路径 | 说明 |
| --- | --- |
| `agent-service/` | Python 网关与后端插件（`agent_gateway/backends/*`） |
| `bridge/` | stdio 适配器、首启配置写入脚本 |
| `patches/zcode-agentcore.patch` | 对 ZCode 的全部改动（后端开关、品牌、打包） |
| `ZCODE_COMMIT` | 补丁对应的 ZCode 上游 commit |
| `.github/workflows/build-desktop.yml` | Win/Mac/Linux 构建工作流（未运行） |
| `screenshots/` | 验证截图 |

## 安装（开发环境）

```bash
# 1. 前端
git clone https://github.com/zai-org/ZCode.git && cd ZCode
git checkout $(cat ../ZCODE_COMMIT) && git apply ../patches/zcode-agentcore.patch
curl https://mise.run | sh && mise trust && mise install      # Node 24.14.0 + pnpm 10.33.2
sudo apt-get install -y build-essential                        # Linux 编译 node-pty
mise exec -- pnpm install
cd ..

# 2. Python 网关（Python ≥ 3.11）
cd agent-service
uv venv -p 3.12 .venv
uv pip install -p .venv/bin/python "agentscope>=2" alibabacloud-agentcore-sdk fastapi uvicorn httpx
cp gateway.example.json gateway.json   # 可选
```

## 配置密钥（`agent-service/.env`，已 gitignore，切勿提交）

```ini
# 任选其一；都不填时自动使用 mock 后端
SILICONFLOW_API_KEY=sk-...
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
SILICONFLOW_MODEL=Qwen/Qwen2.5-72B-Instruct      # 需工具调用时请选支持 function calling 的模型
# DASHSCOPE_API_KEY=sk-...                        # 阿里云百炼
# OPENAI_COMPAT_BASE_URL / OPENAI_COMPAT_API_KEY / OPENAI_COMPAT_MODEL  # 通用 OpenAI 兼容
```
打包版从 `~/.agentcore-desktop/.env` 读取同样的变量，后端选择保存在 `~/.agentcore-desktop/gateway.json`。

## 运行

```bash
export ZCODE_DATA_BASE_DIR=$HOME/.zcode-agentcore      # 建议隔离数据目录
node bridge/write-provider-config.mjs                   # 写入 Agent Gateway 模型 + 跳过智谱登录/引导
cd ZCode
ZCODE_AGENT_BACKEND=gateway AGENT_BACKEND=agentscope mise exec -- pnpm dev:web      # 浏览器 http://localhost:5173
ZCODE_AGENT_BACKEND=gateway AGENT_BACKEND=agentscope mise exec -- pnpm dev:desktop  # 桌面版
# 命令行冒烟测试
AGENT_BACKEND=openai node ../bridge/agent-bridge.mjs --prompt "你好"
```
后端切换：环境变量 `AGENT_BACKEND`，或打开 http://127.0.0.1:18765/settings 选择（热切换并持久化）。
`ZCODE_AGENT_BACKEND=zcode` 可回退到 ZCode 原生 Agent。

## 后端说明

| 名称 | 说明 | 关键配置 |
| --- | --- | --- |
| `mock` | 离线回显，无需密钥 | — |
| `agentscope` | AgentScope 2.x Agent；带工具时由 AgentScope 模型层生成 tool_calls | `DASHSCOPE_API_KEY` 或 SiliconFlow/OpenAI 兼容变量；`model_provider`=`dashscope`/`openai` |
| `agentcore` | AgentScope + 阿里云 AgentCore 托管模型资源（alibabacloud-agentcore-sdk） | 见下节 |
| `agui` | 对接任意 AG-UI 协议 Agent 服务（AgentCore AG-UI、LangGraph/CrewAI/Mastra 等） | `AGUI_URL`、`AGUI_TOKEN` |
| `openai` | 透传任意 OpenAI Chat Completions 服务（含 tools 流式透传） | `OPENAI_COMPAT_*` 或 SiliconFlow 变量 |

### AgentCore 配置（填好凭据即可运行）

```ini
AGENT_BACKEND=agentcore
AGENTCORE_MODEL_RESOURCE=<工作空间中的模型资源名>
AGENTCORE_MODEL=<可选，具体模型>
ALIBABA_CLOUD_ACCESS_KEY_ID=...
ALIBABA_CLOUD_ACCESS_KEY_SECRET=...
# 本地调试也可用控制台签发的调试令牌，或运行时配置文件：
# AGENTCORE_DEBUG_TOKEN=...  /  AGENTCORE_CONFIG_PATH=... AGENTCORE_ENV_PATH=...
# AGENTCORE_CONTROL_PLANE_ENDPOINT=...
```
参考：https://help.aliyun.com/zh/agentcore/agentcore-python-sdk-user-guide 。当前未用真实凭据验证。

### 新增一个框架

1. 新建 `agent-service/agent_gateway/backends/xxx.py`，继承 `AgentBackend`：
   - 只需文本：实现 `async def stream(messages, model)`，逐段 `yield` 文本；
   - 需要工具：重写 `async def chat(body)`，`yield {"content": ...}` 或 `{"tool_calls": [...]}`（OpenAI delta 格式）。
2. 在 `backends/__init__.py` 的 `REGISTRY` 中注册。
3. 已提供 OpenAI 兼容或 AG-UI 接口的框架无需写代码，直接用 `openai` / `agui` 后端。

## 打包

```bash
# Python 网关 → agent-service/dist/agent-gateway/
cd agent-service && uv pip install -p .venv/bin/python pyinstaller
.venv/bin/pyinstaller -y agent-gateway.spec   # 跨平台 spec，Windows 下产出 agent-gateway.exe
# 桌面安装包（网关与 bridge 通过 extraResources 打入 resources/agent-gateway、resources/agentcore）
cd ../ZCode && mise exec -- pnpm bundle:desktop -- --os linux --arch x64   # 产物在 packages/desktop/dist/
```
Linux 目标默认 `AppImage,deb`（`AGENTCORE_LINUX_TARGETS` 可改）。Windows/macOS 用 GitHub Actions 工作流构建；未配置签名，产物未签名/未公证。

## 品牌与登录

- 产品名/AppId：`AgentCore Desktop` / `com.agentcore.desktop`（`AGENTCORE_DESKTOP_IDENTITY=0` 回退 ZCode）。
- 界面文案中的 “ZCode” 已替换为 “AgentCore Desktop”（中英文）。
- 首次启动时主进程先运行 `agent-bridge.mjs --prestart`：拉起网关并写入“已跳过登录、引导已完成”状态（`AGENTCORE_SKIP_LOGIN=0` 关闭），无需智谱账号。
- 图标（`packages/desktop/build`、`branding/icon-1024.png`）、窗口/托盘/菜单/深链/更新提示、Agent 自我介绍均已改为 AgentCore Desktop。

## 设置页：Agent 后端

「设置 → Agent 后端」可选择 mock / agentscope / openai / agui / agentcore，并填写 Base URL、API Key、模型等；保存即热切换，写入 `~/.agentcore-desktop/gateway.json`（权限 600，密钥只写不回显）。网关也读取 `~/.agentcore-desktop/.env`。
功能兼容性见 [docs/兼容性矩阵.md](docs/兼容性矩阵.md)。

## 已知限制

- 智谱云功能（用量统计、营销位、官方 MCP 配额、分享、插件市场、OAuth）已全部指向本地网关桩（返回 404，不外连），界面中这些入口显示为空/不可用。
- 自动更新默认关闭；设置 `AGENTCORE_UPDATE_URL`（electron-updater generic 源）后启用。
- AgentScope 带工具时使用 AgentScope 的模型层单步决策，多步循环由 ZCode 驱动；无工具时走完整 AgentScope Agent。
- 许可：ZCode 与 AgentScope 均为 Apache-2.0，分发时保留其 LICENSE/NOTICE。
