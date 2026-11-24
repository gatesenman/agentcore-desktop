import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { checkGatewayHealth, createGatewaySupervisor } from "../bridge/gateway-supervisor.mjs";

describe("gateway supervisor", () => {
  it("checkGatewayHealth 在探测失败时返回 ok=false 且不抛出", async () => {
    const result = await checkGatewayHealth("http://127.0.0.1:9/healthz", fetch, 200);
    assert.equal(result.ok, false);
    assert.ok(result.reason === "unreachable" || result.reason === "timeout");
  });

  it("checkGatewayHealth 在 200 且 body.ok 时返回成功", async () => {
    const fetchImpl = async () => ({
      ok: true,
      json: async () => ({ ok: true, backend: "mock" }),
    });
    const result = await checkGatewayHealth("http://example.invalid/healthz", fetchImpl);
    assert.equal(result.ok, true);
    assert.equal(result.body.backend, "mock");
  });

  it("连续失败达到阈值后调用 start 并清零计数", async () => {
    const calls = [];
    let healthy = false;
    const supervisor = createGatewaySupervisor({
      failThreshold: 2,
      check: async () => ({ ok: healthy }),
      start: async () => {
        calls.push("start");
        healthy = true;
      },
    });
    const first = await supervisor.tick();
    assert.equal(first.restarted, false);
    assert.equal(first.fails, 1);
    const second = await supervisor.tick();
    assert.equal(second.restarted, true);
    assert.deepEqual(calls, ["start"]);
    const third = await supervisor.tick();
    assert.equal(third.ok, true);
    assert.equal(third.restarted, false);
  });
});
