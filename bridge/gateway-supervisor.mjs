/**
 * 网关健康检查与自动拉起。可被 agent-bridge 使用，也可单独做单元测试。
 * 默认每 10s 探测一次 /healthz，连续失败 2 次后调用 start()。
 */
export async function checkGatewayHealth(url, fetchImpl = fetch, timeoutMs = 3000) {
  try {
    const response = await fetchImpl(url, { signal: AbortSignal.timeout(timeoutMs) });
    if (!response.ok) {
      return { ok: false, status: response.status };
    }
    const body = await response.json();
    return { ok: Boolean(body?.ok), body };
  } catch (error) {
    const name = error instanceof Error ? error.name : "Error";
    const reason = name === "TimeoutError" || name === "AbortError" ? "timeout" : "unreachable";
    return { ok: false, reason };
  }
}

export function createGatewaySupervisor(options) {
  const intervalMs = options.intervalMs ?? 10_000;
  const failThreshold = options.failThreshold ?? 2;
  const check = options.check;
  const start = options.start;
  const log = options.log ?? (() => {});
  let fails = 0;
  let timer = null;

  async function tick() {
    const result = await check();
    if (result.ok) {
      fails = 0;
      return { ok: true, restarted: false, fails };
    }
    fails += 1;
    log("health-fail", String(fails), result.reason ?? String(result.status ?? "down"));
    if (fails >= failThreshold) {
      log("restart-gateway", `after ${fails} failed checks`);
      await start();
      fails = 0;
      return { ok: false, restarted: true, fails: 0 };
    }
    return { ok: false, restarted: false, fails };
  }

  function startWatching() {
    if (timer) return;
    timer = setInterval(() => {
      void tick();
    }, intervalMs);
    if (typeof timer.unref === "function") timer.unref();
  }

  function stopWatching() {
    if (timer) {
      clearInterval(timer);
      timer = null;
    }
  }

  return { tick, startWatching, stopWatching, getFails: () => fails };
}
