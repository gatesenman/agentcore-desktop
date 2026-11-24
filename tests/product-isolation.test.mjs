import assert from "node:assert/strict";
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, it } from "node:test";

import {
  isAgentCoreDesktopIdentityEnabled,
  resolveDesktopProductIdentity,
  resolveDesktopProtocolScheme,
  resolveProductHomeDataDirName,
  resolveWindowsAppUserModelId,
  resolveWindowsAppUserModelIdForFlavor,
} from "../ZCode/packages/desktop/scripts/desktop-product-identity.mjs";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

describe("AgentCore 与 ZCode 身份/数据/协议隔离", () => {
  it("默认身份是 com.agentcore.desktop，而不是 dev.zcode.app", () => {
    assert.equal(isAgentCoreDesktopIdentityEnabled({}), true);
    const identity = resolveDesktopProductIdentity({ ZCODE_ENV: "production" });
    assert.equal(identity.appId, "com.agentcore.desktop");
    assert.equal(identity.productName, "AgentCore Desktop");
    assert.equal(identity.linuxExecutableName, "agentcore-desktop");
    assert.notEqual(identity.appId, "dev.zcode.app");
  });

  it("打包态 AUMID 与 appId 一致，开发态使用独立 dev AUMID", () => {
    assert.equal(resolveWindowsAppUserModelId({ ZCODE_ENV: "production" }), "com.agentcore.desktop");
    assert.equal(
      resolveWindowsAppUserModelIdForFlavor("production", { isPackaged: true }, {}),
      "com.agentcore.desktop",
    );
    assert.equal(resolveWindowsAppUserModelId({}, { isPackaged: false }), "com.agentcore.desktop.dev");
  });

  it("默认协议为 agentcore，家目录数据为 .agentcore-desktop", () => {
    assert.equal(resolveDesktopProtocolScheme({}), "agentcore");
    assert.equal(resolveProductHomeDataDirName({}), ".agentcore-desktop");
    assert.equal(resolveDesktopProtocolScheme({ AGENTCORE_DESKTOP_IDENTITY: "0" }), "zcode");
    assert.equal(resolveProductHomeDataDirName({ AGENTCORE_DESKTOP_IDENTITY: "0" }), ".zcode");
  });

  it("构建配置与数据根源码使用同一套产品目录/协议辅助函数", () => {
    const builder = readFileSync(join(root, "ZCode/packages/desktop/electron-builder.config.js"), "utf8");
    assert.match(builder, /resolveDesktopProtocolScheme/);
    assert.doesNotMatch(builder, /schemes:\s*\[\s*"zcode"\s*\]/);

    const paths = readFileSync(join(root, "ZCode/packages/services/src/paths.ts"), "utf8");
    assert.match(paths, /export function getProductHomeDataDirName/);
    assert.match(paths, /AGENTCORE_HOME_DATA_DIR_NAME = "\.agentcore-desktop"/);
    assert.match(paths, /getDataBaseDir\(\),\s*getProductHomeDataDirName\(\)/);

    const linux = readFileSync(
      join(root, "ZCode/packages/desktop/src/main/desktopLinuxDeepLinkRegistration.ts"),
      "utf8",
    );
    assert.match(linux, /agentcore-desktop\.desktop/);
    assert.match(linux, /x-scheme-handler\/agentcore/);
    assert.doesNotMatch(linux, /LINUX_DEEP_LINK_MIME_TYPE = "x-scheme-handler\/zcode"/);
  });

  it("gitignore 排除密钥文件，示例配置不含真实 key", () => {
    const ignore = readFileSync(join(root, ".gitignore"), "utf8") + readFileSync(join(root, "agent-service/.gitignore"), "utf8");
    assert.match(ignore, /\.env/);
    assert.match(ignore, /gateway\.json/);
    const example = readFileSync(join(root, "agent-service/.env.example"), "utf8");
    assert.doesNotMatch(example, /sk-[A-Za-z0-9]{8,}/);
    assert.doesNotMatch(example, /(?<![A-Z0-9_])=(?!$|\s|#)[A-Za-z0-9_\-]{20,}/);
    const gwExample = readFileSync(join(root, "agent-service/gateway.example.json"), "utf8");
    assert.doesNotMatch(gwExample, /sk-[A-Za-z0-9]{8,}/);
    const docs = readdirSync(join(root, "docs"));
    assert.ok(docs.includes("兼容性矩阵.md"), `docs should include 兼容性矩阵.md, got ${docs.join(",")}`);
  });
});
