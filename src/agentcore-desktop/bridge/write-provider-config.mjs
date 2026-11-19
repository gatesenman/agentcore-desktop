// Pre-seed provider config so the Host UI sees the gateway model before the first agent spawn.
process.argv.push("--write-config-only");
await import("./agent-bridge.mjs");
