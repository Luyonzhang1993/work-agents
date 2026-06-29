import { useEffect, useState } from "react";
import { listMCPTools, type MCPTool } from "../api/client";

// ── Types ──

interface ParamDef {
  key: string;
  type: string;
  description: string;
  required: boolean;
  default: string;
}

interface StepDef {
  id: string;
  name: string;
  type: string;
  system_prompt: string;
  user_prompt: string;
  temperature: number;
  tool_name?: string;
  tool_id?: string;
}

interface EdgeDef {
  from: string;
  to: string;
}

interface VisualDef {
  parameters: {
    type: "object";
    properties: Record<string, { type: string; description: string; default?: unknown }>;
    required: string[];
    additionalProperties: false;
  };
  steps: StepDef[];
  edges: EdgeDef[];
}

const STEP_TYPES = [
  { value: "llm_call", label: "LLM 调用" },
  { value: "mcp_tool", label: "MCP 工具" },
  { value: "pass_through", label: "数据传递" },
];

const PARAM_TYPES = ["string", "integer", "number", "boolean", "array"];

interface Props {
  value: VisualDef;
  onChange: (def: VisualDef) => void;
}

export default function WorkflowVisualEditor({ value, onChange }: Props) {
  const [showPreview, setShowPreview] = useState(false);
  const [mcpTools, setMcpTools] = useState<MCPTool[]>([]);

  useEffect(() => {
    listMCPTools().then(setMcpTools).catch(() => {});
  }, []);

  const def = value;

  const notify = (updated: VisualDef) => onChange({ ...updated });

  // ── Parameters ──
  const params = Object.entries(def.parameters?.properties || {}).map(
    ([key, prop]) => ({
      key,
      type: typeof prop === "object" ? (prop as Record<string, unknown>).type as string || "string" : "string",
      description: typeof prop === "object" ? (prop as Record<string, unknown>).description as string || "" : "",
      required: def.parameters?.required?.includes(key) || false,
      default: typeof prop === "object" ? String((prop as Record<string, unknown>).default ?? "") : "",
    })
  );

  const updateParams = (newParams: ParamDef[]) => {
    const properties: Record<string, { type: string; description: string; default?: unknown }> = {};
    const required: string[] = [];
    for (const p of newParams) {
      const prop: { type: string; description: string; default?: unknown } = {
        type: p.type,
        description: p.description,
      };
      if (p.default !== "") prop.default = p.default;
      properties[p.key] = prop;
      if (p.required) required.push(p.key);
    }
    notify({
      ...def,
      parameters: { type: "object", properties, required, additionalProperties: false },
    });
  };

  const addParam = () => {
    updateParams([...params, { key: "", type: "string", description: "", required: false, default: "" }]);
  };

  const removeParam = (idx: number) => {
    updateParams(params.filter((_, i) => i !== idx));
  };

  const changeParam = (idx: number, field: keyof ParamDef, val: string | boolean) => {
    const copy = [...params];
    (copy[idx] as Record<string, unknown>)[field] = val;
    updateParams(copy);
  };

  // ── Steps ──
  const steps: StepDef[] = def.steps || [];

  const updateSteps = (newSteps: StepDef[]) => {
    notify({ ...def, steps: newSteps });
  };

  const addStep = () => {
    const id = `step_${Date.now()}`;
    updateSteps([
      ...steps,
      { id, name: "", type: "llm_call", system_prompt: "", user_prompt: "", temperature: 0.7 },
    ]);
  };

  const removeStep = (idx: number) => {
    updateSteps(steps.filter((_, i) => i !== idx));
  };

  const changeStep = (idx: number, fields: Partial<StepDef>) => {
    const copy = steps.map((s, i) => (i === idx ? { ...s, ...fields } : { ...s }));
    updateSteps(copy);
  };

  // ── Edges ──
  const edges: EdgeDef[] = def.edges || [];
  const nodeIds = ["start", ...steps.map((s) => s.id || "?").filter(Boolean), "end"];

  const updateEdges = (newEdges: EdgeDef[]) => {
    notify({ ...def, edges: newEdges });
  };

  const addEdge = () => {
    updateEdges([...edges, { from: "start", to: "end" }]);
  };

  const removeEdge = (idx: number) => {
    updateEdges(edges.filter((_, i) => i !== idx));
  };

  const changeEdge = (idx: number, field: "from" | "to", val: string) => {
    const copy = edges.map((e) => ({ ...e }));
    copy[idx][field] = val;
    updateEdges(copy);
  };

  return (
    <div className="visual-editor">
      {/* ── Parameters ── */}
      <section className="ve-section">
        <div className="ve-section-header">
          <h4>输入参数</h4>
          <button className="btn-sm" onClick={addParam}>+ 添加</button>
        </div>
        {params.length === 0 && <p className="hint">暂无参数，点击添加</p>}
        {params.map((p, i) => (
          <div key={i} className="ve-row">
            <input
              className="ve-input-sm"
              placeholder="参数名"
              value={p.key}
              onChange={(e) => changeParam(i, "key", e.target.value)}
            />
            <select
              className="ve-select-sm"
              value={p.type}
              onChange={(e) => changeParam(i, "type", e.target.value)}
            >
              {PARAM_TYPES.map((t) => (
                <option key={t} value={t}>{t}</option>
              ))}
            </select>
            <input
              className="ve-input-sm"
              placeholder="描述"
              value={p.description}
              onChange={(e) => changeParam(i, "description", e.target.value)}
            />
            <input
              className="ve-input-xs"
              placeholder="默认值"
              value={p.default}
              onChange={(e) => changeParam(i, "default", e.target.value)}
            />
            <label className="ve-check">
              <input
                type="checkbox"
                checked={p.required}
                onChange={(e) => changeParam(i, "required", e.target.checked)}
              />
              必填
            </label>
            <button className="btn-sm btn-danger" onClick={() => removeParam(i)}>✕</button>
          </div>
        ))}
      </section>

      {/* ── Steps ── */}
      <section className="ve-section">
        <div className="ve-section-header">
          <h4>步骤 ({steps.length})</h4>
          <button className="btn-sm" onClick={addStep}>+ 添加步骤</button>
        </div>
        {steps.length === 0 && <p className="hint">暂无步骤，点击添加</p>}
        {steps.map((s, i) => (
          <div key={i} className="ve-card">
            <div className="ve-card-header">
              <span className="step-emoji">{i + 1}️⃣</span>
              <input
                className="ve-input"
                placeholder="步骤ID (英文)"
                value={s.id}
                onChange={(e) => changeStep(i, { id: e.target.value })}
              />
              <input
                className="ve-input"
                placeholder="步骤名称"
                value={s.name}
                onChange={(e) => changeStep(i, { name: e.target.value })}
              />
              <select
                className="ve-select"
                value={s.type}
                onChange={(e) => changeStep(i, { type: e.target.value as StepDef["type"] })}
              >
                {STEP_TYPES.map((t) => (
                  <option key={t.value} value={t.value}>{t.label}</option>
                ))}
              </select>
              <button className="btn-sm btn-danger" onClick={() => removeStep(i)}>删除</button>
            </div>

            {s.type === "llm_call" && (
              <div className="ve-card-body">
                <label>System Prompt</label>
                <textarea
                  className="ve-textarea"
                  rows={3}
                  value={s.system_prompt}
                  onChange={(e) => changeStep(i, { system_prompt: e.target.value })}
                  placeholder="You are a helpful assistant."
                />
                <label>User Prompt <span className="hint">（可用 {"{变量名}"} 引用前序步骤输出）</span></label>
                <textarea
                  className="ve-textarea"
                  rows={4}
                  value={s.user_prompt}
                  onChange={(e) => changeStep(i, { user_prompt: e.target.value })}
                  placeholder="请处理: {message}"
                />
                <label>Temperature</label>
                <input
                  className="ve-input-sm"
                  type="number"
                  min={0}
                  max={2}
                  step={0.1}
                  value={s.temperature}
                  onChange={(e) => changeStep(i, { temperature: parseFloat(e.target.value) || 0.7 })}
                />
              </div>
            )}

            {s.type === "mcp_tool" && (
              <div className="ve-card-body">
                <label>选择 MCP 工具</label>
                <select
                  className="ve-select"
                  value={s.tool_id || ""}
                  onChange={(e) => {
                    const toolId = e.target.value;
                    const tool = mcpTools.find((t) => t.id === toolId);
                    changeStep(i, {
                      tool_id: toolId,
                      tool_name: tool ? `${tool.service}.${tool.name}` : "",
                    });
                  }}
                >
                  <option value="">-- 选择工具 --</option>
                  {mcpTools.map((t) => (
                    <option key={t.id} value={t.id}>
                      {t.service}/{t.name} — {t.description}
                    </option>
                  ))}
                </select>
              </div>
            )}

            {s.type === "pass_through" && (
              <div className="ve-card-body">
                <label>来源步骤 ID（从哪个步骤取输出）</label>
                <input
                  className="ve-input"
                  value={(s as unknown as Record<string,string>).source || ""}
                  onChange={(e) => {
                    const copy = steps.map((s2, i2) =>
                      i2 === i ? { ...s2, source: e.target.value } : { ...s2 }
                    );
                    updateSteps(copy as StepDef[]);
                  }}
                  placeholder="步骤ID"
                />
              </div>
            )}
          </div>
        ))}
      </section>

      {/* ── Edges ── */}
      <section className="ve-section">
        <div className="ve-section-header">
          <h4>执行顺序</h4>
          <button className="btn-sm" onClick={addEdge}>+ 添加边</button>
        </div>
        {edges.length === 0 && <p className="hint">暂无边，点击添加。节点: {nodeIds.join(" → ")}</p>}
        {edges.map((e, i) => (
          <div key={i} className="ve-row">
            <select
              className="ve-select-sm"
              value={e.from}
              onChange={(ev) => changeEdge(i, "from", ev.target.value)}
            >
              {nodeIds.map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
            <span className="hint">→</span>
            <select
              className="ve-select-sm"
              value={e.to}
              onChange={(ev) => changeEdge(i, "to", ev.target.value)}
            >
              {nodeIds.map((n) => (
                <option key={n} value={n}>{n}</option>
              ))}
            </select>
            <button className="btn-sm btn-danger" onClick={() => removeEdge(i)}>✕</button>
          </div>
        ))}
        {edges.length > 0 && (
          <button
            className="btn-sm"
            style={{ marginTop: 8 }}
            onClick={() => {
              // Auto-generate linear edges
              const ids = ["start", ...steps.map((s) => s.id).filter(Boolean), "end"];
              const autoEdges: EdgeDef[] = [];
              for (let i = 0; i < ids.length - 1; i++) {
                autoEdges.push({ from: ids[i], to: ids[i + 1] });
              }
              updateEdges(autoEdges);
            }}
          >
            自动生成线性连接
          </button>
        )}
      </section>

      {/* ── Preview ── */}
      <section className="ve-section">
        <button className="btn-sm" onClick={() => setShowPreview(!showPreview)}>
          {showPreview ? "隐藏 JSON 预览" : "📄 JSON 预览"}
        </button>
        {showPreview && (
          <pre className="ve-preview">{JSON.stringify(def, null, 2)}</pre>
        )}
      </section>
    </div>
  );
}
