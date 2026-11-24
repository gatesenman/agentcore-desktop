#!/usr/bin/env node
// ZCode ↔ pluggable agent backends stdio bridge.
// ZCode Host spawns this instead of the stock agent (ZCODE_AGENT_BACKEND=gateway).
// It (1) starts the Python Agent Gateway (AgentScope / OpenAI-compatible / mock / ...),
// (2) writes a personal provider config pointing ZCode at that gateway,
// (3) runs the ZCode agent runtime with stdio inherited, so ZCode Protocol v4 framing
//     stays byte-exact (no re-implementation of the 3.5k-line v4 gateway).
// NOTE: stdout is the protocol channel — log only to stderr.
import { spawn } from "node:child_process";
import { mkdirSync, writeFileSync, existsSync, readFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { homedir } from "node:os";
import { checkGatewayHealth, createGatewaySupervisor } from "./gateway-supervisor.mjs";
import { resolveProductHomeDataDirName } from "../ZCode/packages/desktop/scripts/desktop-product-identity.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const root = resolve(here, "..");
const zcode = process.env.ZCODE_REPO ?? join(root, "ZCode");
const svc = process.env.AGENT_SERVICE_DIR ?? join(root, "agent-service");
const port = Number(process.env.AGENT_GATEWAY_PORT ?? 18765);
const log = (...a) => process.stderr.write(`[agent-bridge] ${a.join(" ")}\n`);

const configOnly = process.argv.includes("--write-config-only");
// --prestart：桌面主进程启动时调用，拉起网关（设置页可用）+ 写配置 + 跳过登录，然后退出。
const prestart = process.argv.includes("--prestart");
// 1) gateway (skip if already up)
let gw = null;
const healthUrl = `http://127.0.0.1:${port}/healthz`;
const up = async () => (await checkGatewayHealth(healthUrl)).ok;

function resolveGatewayCommand() {
  // 打包态：resources/agent-gateway/agent-gateway（PyInstaller）；开发态：agent-service/.venv
  const res = process.env.AGENTCORE_RESOURCES;
  const frozen = process.env.AGENT_GATEWAY_BIN ||
    (res && [join(res, "agent-gateway", "agent-gateway"), join(res, "agent-gateway", "agent-gateway.exe")].find(existsSync));
  if (frozen) {
    return { cmd: frozen, args: ["--port", String(port)], cwd: dirname(frozen), detached: true };
  }
  const python = process.platform === "win32"
    ? join(svc, ".venv", "Scripts", "python.exe")
    : join(svc, ".venv", "bin", "python");
  return {
    cmd: python,
    args: ["-m", "uvicorn", "agent_gateway.server:app", "--host", "127.0.0.1", "--port", String(port)],
    cwd: svc,
    detached: false,
  };
}

async function startGateway() {
  const resolved = resolveGatewayCommand();
  if (gw && !gw.killed) {
    try { gw.kill(); } catch { /* already gone */ }
  }
  gw = spawn(resolved.cmd, resolved.args, {
    cwd: resolved.cwd,
    stdio: ["ignore", "ignore", "inherit"],
    env: process.env,
    detached: resolved.detached,
    windowsHide: true,
  });
  if (resolved.detached) {
    gw.unref();
    gw = null;
  }
  for (let i = 0; i < 100 && !(await up()); i++) await new Promise((r) => setTimeout(r, 200));
  return up();
}

if (!configOnly && !(await up())) {
  await startGateway();
}
if (!configOnly) {
  try {
    log("gateway", JSON.stringify((await checkGatewayHealth(healthUrl)).body ?? { ok: await up() }));
  } catch {
    log("gateway", "healthz-unreadable");
  }
  const supervisor = createGatewaySupervisor({
    intervalMs: Number(process.env.AGENT_GATEWAY_HEALTH_INTERVAL_MS ?? 10_000),
    failThreshold: Number(process.env.AGENT_GATEWAY_HEALTH_FAILS ?? 2),
    check: () => checkGatewayHealth(healthUrl),
    start: startGateway,
    log,
  });
  supervisor.startWatching();
}

// 2) provider config
const providerId = "agent-gateway";
const modelId = "agent-gateway";
// 写到 ZCode 默认 Personal Provider 路径，Host(UI 模型列表) 与 Agent 读到同一份配置。
// 默认写入 ~/.agentcore-desktop/v2，避免覆盖 ~/.zcode 下的个人配置。
const dir = process.env.AGENT_BRIDGE_PROVIDER_DIR ?? join(process.env.ZCODE_DATA_BASE_DIR ?? homedir(), resolveProductHomeDataDirName(), "v2");
mkdirSync(dir, { recursive: true });
const providerFile = join(dir, "provider_config.json");
writeFileSync(providerFile, JSON.stringify({
  schemaVersion: 1,
  config: {
    providerOrder: [providerId],
    providerConfigRules: { providerRules: [{
      providerId, providerName: "Agent Gateway", enabled: true,
      config: {
        group: "standard-personal",
        access: { type: "api-key", apiKey: "local" },
        api: { type: "openai-chat-completions", baseUrl: `http://127.0.0.1:${port}/v1` },
        personalModelIds: [modelId],
      },
    }] },
    // 模型元数据：上下文窗口与图片输入能力（后端模型不支持视觉时设 AGENT_GATEWAY_VISION=0）。
    modelConfigRules: {
      providerModelRules: [{
        providerId, modelId,
        config: { properties: {
          contextWindow: Number(process.env.AGENT_GATEWAY_CONTEXT_WINDOW ?? 128000),
          inputFormat: { supportsImage: process.env.AGENT_GATEWAY_VISION !== "0" },
        } },
      }],
      manualProviderModelRules: [],
    },
    defaultModelSelection: { providerId, modelId },
  },
}, null, 2));

// 2b) 跳过智谱账号登录 / onboarding：预置“已跳过登录”和“onboarding 已完成”状态（仅在缺失时写入）。
function seedFirstRun(base) {
  const v2 = join(base, ".zcode", "v2");
  mkdirSync(v2, { recursive: true });
  const settingFile = join(v2, "setting.json");
  let settings = {};
  try { settings = JSON.parse(readFileSync(settingFile, "utf8")); } catch {}
  if (!settings.providerFamilyDomainMigrated) {
    Object.assign(settings, { providerFamilyDomain: "zai", providerFamilyDomainUpdatedAt: Date.now(), providerFamilyDomainMigrated: true });
    writeFileSync(settingFile, JSON.stringify(settings, null, 2));
  }
  const onboardingFile = join(v2, "onboarding-record.json");
  if (!existsSync(onboardingFile)) {
    writeFileSync(onboardingFile, JSON.stringify({ version: 2, deviceMid: "agentcore-desktop", entries: [{
      userId: null, occupation: null, interfaceMode: null, memoryEnabled: null, proactiveSuggestionsEnabled: null,
      completedAt: new Date().toISOString(), uploadState: "pending" }], decisions: [] }, null, 2));
  }
}
if (process.env.AGENTCORE_SKIP_LOGIN !== "0") {
  for (const base of new Set([process.env.ZCODE_DATA_BASE_DIR ?? homedir(), homedir()])) seedFirstRun(base);
}
if (configOnly || prestart) { log("wrote", providerFile); gw?.unref?.(); process.exit(0); }
// 3) ZCode agent runtime on inherited stdio
const dist = join(zcode, "apps/zcode-cli/packages/cli/dist/zcode.cjs");
const [cmd, args] = process.env.ZCODE_AGENT_ENTRY
  ? [process.execPath, [process.env.ZCODE_AGENT_ENTRY]]
  : existsSync(dist)
  ? [process.execPath, [dist]]
  : [join(zcode, "node_modules/.bin/tsx"), [join(zcode, "apps/zcode-cli/packages/cli/src/main.ts")]];
const child = spawn(cmd, [...args, ...(process.argv.slice(2).length ? process.argv.slice(2) : ["app-server", "--stdio"])], {
  stdio: "inherit",
  env: { ...process.env, ELECTRON_RUN_AS_NODE: "1", ZCODE_PERSONAL_PROVIDER_CONFIG_FILE: providerFile },
});
const stop = () => { child.kill(); gw?.kill(); };
process.on("SIGTERM", stop); process.on("SIGINT", stop);
child.on("exit", (code) => { gw?.kill(); process.exit(code ?? 0); });
