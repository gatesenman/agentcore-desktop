# AgentCore 桌面端

**3.15.1** · 基于 ZCode 前端、可插拔 Agent 后端的跨平台桌面应用，可接入 AgentScope、阿里云 AgentCore、AG-UI 以及 OpenAI 兼容服务。

## 界面截图

![桌面端启动](screenshots/desktop-start.png)

*桌面端启动 / Desktop start screen*

![桌面对话回复](screenshots/desktop-chat-reply.png)

*桌面对话回复 / Desktop chat reply*

![Agent 后端设置](screenshots/settings-agent-backend.png)

*Agent 后端设置 / Agent backend settings*

![Web 端对话](screenshots/web-chat-reply.png)

*Web 端对话 / Web chat reply*

## 功能特性

- ZCode（Electron + React）桌面 / Web 共用界面，通过桥接接入多种 Agent 后端。
- 后端插件：mock、AgentScope、阿里云 AgentCore、AG-UI、OpenAI 兼容网关，可按需扩展。
- 内置工具执行（读文件、终端、编辑等）与流式对话、审计/历史记录。
- 配套 `agent-service` Python 网关（可打包为独立可执行文件）。

## 技术栈

- 前端：ZCode（Electron, React, TypeScript）
- 网关：Python / FastAPI（AgentScope 等）
- 包管理：pnpm（ZCode 工作区）

## 从源码运行

源码在仓库根目录。本仓库不包含安装包。开发与构建请以仓库中的说明为准：

```bash
# 详见其中 README：ZCode 前端通常使用 pnpm，Agent 服务使用 Python
```
ZCode 本体在 `ZCode/`。

## 文档

- [ZCode README](ZCode/README.md)
- [ZCode README (English)](ZCode/README.en.md)
- [AgentScope](agentscope/README_zh.md)


## 贡献

欢迎通过 Issue 和 Pull Request 参与，详见 [CONTRIBUTING.md](CONTRIBUTING.md)。安全问题请按 [SECURITY.md](SECURITY.md) 私下报告。参与时请遵守 [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)。

## 许可证

ZCode 在 `ZCode/package.json` 与 `ZCode/LICENSE` 中声明为 Apache-2.0。请同时查看 ZCode 的第三方声明。

---

## English

# AgentCore Desktop

**3.15.1** · A cross-platform desktop app built on the ZCode frontend with pluggable agent backends: AgentScope, Alibaba Cloud AgentCore, AG-UI, and OpenAI-compatible services.

## Screenshots

![Desktop start screen](screenshots/desktop-start.png)

*桌面端启动 / Desktop start screen*

![Desktop chat reply](screenshots/desktop-chat-reply.png)

*桌面对话回复 / Desktop chat reply*

![Agent backend settings](screenshots/settings-agent-backend.png)

*Agent 后端设置 / Agent backend settings*

![Web chat reply](screenshots/web-chat-reply.png)

*Web 端对话 / Web chat reply*

## Features

- Shared ZCode (Electron + React) UI for desktop and web, bridged to multiple agent backends.
- Backend plugins: mock, AgentScope, Alibaba Cloud AgentCore, AG-UI, and OpenAI-compatible gateways.
- Built-in tool execution (files, shell, edits), streaming chat, and audit/history views.
- Includes an `agent-service` Python gateway that can be packaged as a standalone executable.

## Tech stack

- 前端：ZCode（Electron, React, TypeScript）
- 网关：Python / FastAPI（AgentScope 等）
- 包管理：pnpm（ZCode 工作区）

## Getting started

Source is at the repository root. This repository does not include installers. Follow the in-tree README for development and builds:

```bash
# See that README: the ZCode UI typically uses pnpm; the agent service uses Python
```
ZCode itself lives in `ZCode/`.

## Documentation

- [ZCode README](ZCode/README.md)
- [ZCode README (English)](ZCode/README.en.md)
- [AgentScope](agentscope/README_zh.md)


## Contributing

Issues and pull requests are welcome. See [CONTRIBUTING.md](CONTRIBUTING.md). Please report vulnerabilities privately via [SECURITY.md](SECURITY.md). This project follows [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## License

ZCode is licensed Apache-2.0 (`ZCode/LICENSE` and `package.json`). Also see ZCode third-party notices.
