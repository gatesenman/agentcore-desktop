// AgentCore Desktop：Agent 后端选择与配置（mock / agentscope / openai / agui / agentcore）。
// 配置由本机 Agent Gateway 持久化（~/.agentcore-desktop/gateway.json 或 agent-service/gateway.json），
// 保存后网关热切换，下一条消息即生效。密钥只写不读：留空表示保持原值。
import { useCallback, useEffect, useState } from "react";
import { Button } from "@/components/ui/button.js";
import { SettingsGroupCard, SettingsRow } from "@/settings/SettingsPageParts.js";

export const AGENT_GATEWAY_ORIGIN = "http://127.0.0.1:18765";

type FieldKind = "text" | "secret" | "select";
interface FieldSpec { key: string; label: string; kind?: FieldKind; placeholder?: string; options?: string[] }

const BACKENDS: Record<string, { label: string; description: string; fields: FieldSpec[] }> = {
  mock: { label: "Mock（离线回显）", description: "无需密钥，用于调试界面与流程。", fields: [] },
  agentscope: {
    label: "AgentScope",
    description: "阿里开源 AgentScope 2.x Agent；模型可用百炼 DashScope 或任意 OpenAI 兼容服务。",
    fields: [
      { key: "model_provider", label: "模型来源", kind: "select", options: ["openai", "dashscope"] },
      { key: "base_url", label: "Base URL（OpenAI 兼容）", placeholder: "https://api.siliconflow.cn/v1" },
      { key: "api_key", label: "API Key", kind: "secret" },
      { key: "model", label: "模型", placeholder: "Qwen/Qwen2.5-72B-Instruct" },
      { key: "sys_prompt", label: "系统提示词（无工具时生效）" },
    ],
  },
  openai: {
    label: "OpenAI 兼容（通用）",
    description: "透传任意 OpenAI Chat Completions 服务（含工具调用）。",
    fields: [
      { key: "base_url", label: "Base URL", placeholder: "https://api.siliconflow.cn/v1" },
      { key: "api_key", label: "API Key", kind: "secret" },
      { key: "upstream_model", label: "模型", placeholder: "Qwen/Qwen2.5-72B-Instruct" },
    ],
  },
  agui: {
    label: "AG-UI 协议",
    description: "对接任意 AG-UI Agent 服务（AgentCore、LangGraph、CrewAI、Mastra 等）。",
    fields: [
      { key: "url", label: "AG-UI 端点 URL", placeholder: "http://127.0.0.1:8000/agui" },
      { key: "token", label: "Bearer Token", kind: "secret" },
    ],
  },
  agentcore: {
    label: "阿里云 AgentCore",
    description: "AgentScope + AgentCore 托管模型资源（alibabacloud-agentcore-sdk）。",
    fields: [
      { key: "model_resource", label: "模型资源名", placeholder: "my-model-resource" },
      { key: "model", label: "模型（可选）" },
      { key: "access_key_id", label: "AccessKey ID", kind: "secret" },
      { key: "access_key_secret", label: "AccessKey Secret", kind: "secret" },
      { key: "debug_token", label: "调试令牌（可选）", kind: "secret" },
      { key: "control_plane_endpoint", label: "控制面 Endpoint（可选）" },
    ],
  },
};

const inputClass =
  "h-8 w-full rounded-md border border-border bg-background px-2 text-ui-base text-foreground outline-none focus:border-foreground-subtle";

export function AgentBackendSection() {
  const [status, setStatus] = useState<"loading" | "ready" | "offline">("loading");
  const [current, setCurrent] = useState<string>("");
  const [backend, setBackend] = useState<string>("mock");
  const [values, setValues] = useState<Record<string, string>>({});
  const [secretsSet, setSecretsSet] = useState<string[]>([]);
  const [message, setMessage] = useState<string>("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async (name?: string) => {
    try {
      const res = await fetch(`${AGENT_GATEWAY_ORIGIN}/admin/backend${name ? `?name=${encodeURIComponent(name)}` : ""}`);
      const data = (await res.json()) as { backend: string; selected: string; config: Record<string, string>; secrets_set?: string[] };
      setCurrent(data.backend);
      setBackend(data.selected ?? data.backend);
      setValues(Object.fromEntries(Object.entries(data.config ?? {}).map(([k, v]) => [k, String(v ?? "")])));
      setSecretsSet(data.secrets_set ?? []);
      setStatus("ready");
    } catch {
      setStatus("offline");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async () => {
    setSaving(true);
    setMessage("");
    try {
      const spec = BACKENDS[backend];
      const config: Record<string, string> = {};
      for (const f of spec?.fields ?? []) {
        const v = values[f.key]?.trim() ?? "";
        if (f.kind === "secret" && !v) continue; // 留空=保持原值
        config[f.key] = v;
      }
      const res = await fetch(`${AGENT_GATEWAY_ORIGIN}/admin/backend`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ backend, config }),
      });
      if (!res.ok) throw new Error(await res.text());
      setMessage("已保存并切换，下一条消息生效。");
      await load();
    } catch (error) {
      setMessage(`保存失败：${error instanceof Error ? error.message : String(error)}`);
    } finally {
      setSaving(false);
    }
  };

  const test = async () => {
    setMessage("测试中…");
    try {
      const res = await fetch(`${AGENT_GATEWAY_ORIGIN}/v1/chat/completions`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ messages: [{ role: "user", content: "回复 OK" }] }),
      });
      const data = (await res.json()) as { choices?: { message?: { content?: string } }[] };
      setMessage(res.ok ? `连接成功：${data.choices?.[0]?.message?.content ?? ""}` : `连接失败：HTTP ${res.status}`);
    } catch (error) {
      setMessage(`连接失败：${error instanceof Error ? error.message : String(error)}`);
    }
  };

  if (status === "loading") return <div className="text-ui-base text-foreground-subtle">加载中…</div>;
  if (status === "offline")
    return (
      <SettingsGroupCard>
        <SettingsRow
          label="Agent 网关未运行"
          description={`未能连接 ${AGENT_GATEWAY_ORIGIN}。新建一个任务或发送一条消息会自动启动网关，然后点击重试。`}
          control={<Button variant="outline" size="sm" onClick={() => void load()}>重试</Button>}
        />
      </SettingsGroupCard>
    );

  const spec = BACKENDS[backend];
  return (
    <div className="space-y-4" data-testid="agent-backend-section">
      <SettingsGroupCard>
        <SettingsRow
          label="当前后端"
          description={`网关正在使用：${BACKENDS[current]?.label ?? current}`}
          control={
            <select
              data-testid="agent-backend-select"
              className={inputClass}
              value={backend}
              onChange={(e) => {
                setBackend(e.target.value);
                void load(e.target.value).then(() => setBackend(e.target.value));
              }}
            >
              {Object.entries(BACKENDS).map(([id, b]) => (
                <option key={id} value={id}>{b.label}</option>
              ))}
            </select>
          }
        />
        <div className="px-4 pb-3 text-ui-base text-foreground-subtle">{spec?.description}</div>
      </SettingsGroupCard>
      {spec && spec.fields.length > 0 ? (
        <SettingsGroupCard>
          {spec.fields.map((f) => (
            <SettingsRow
              key={f.key}
              label={f.label}
              controlLayout="wide"
              description={f.kind === "secret" && secretsSet.includes(f.key) ? "已设置（留空保持不变）" : undefined}
              control={
                f.kind === "select" ? (
                  <select
                    className={inputClass}
                    value={values[f.key] ?? f.options?.[0] ?? ""}
                    onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
                  >
                    {f.options?.map((o) => <option key={o} value={o}>{o}</option>)}
                  </select>
                ) : (
                  <input
                    data-testid={`agent-backend-field-${f.key}`}
                    className={inputClass}
                    type={f.kind === "secret" ? "password" : "text"}
                    placeholder={f.placeholder}
                    value={f.kind === "secret" ? (values[f.key] ?? "") : (values[f.key] ?? "")}
                    onChange={(e) => setValues((v) => ({ ...v, [f.key]: e.target.value }))}
                  />
                )
              }
            />
          ))}
        </SettingsGroupCard>
      ) : null}
      <div className="flex items-center gap-2">
        <Button size="sm" data-testid="agent-backend-save" disabled={saving} onClick={() => void save()}>
          保存并切换
        </Button>
        <Button size="sm" variant="outline" onClick={() => void test()}>测试连接</Button>
        <span className="text-ui-base text-foreground-subtle" data-testid="agent-backend-message">{message}</span>
      </div>
    </div>
  );
}
