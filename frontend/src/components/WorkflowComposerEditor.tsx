import { useEffect, useMemo, useState } from "react";
import { listMCPTools, type MCPTool } from "../api/client";

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
  system_prompt?: string;
  user_prompt?: string;
  temperature?: number;
  tool_name?: string;
  tool_id?: string;
  arguments?: Record<string, unknown>;
  source?: string;
  value?: unknown;
  field?: string;
  default?: string;
}

interface EdgeDef {
  from: string;
  to: string;
  condition?: string;
}

interface DynamicDefinition {
  parameters?: {
    type: "object";
    properties: Record<string, { type: string; description: string; default?: unknown }>;
    required?: string[];
    additionalProperties?: false;
  };
  steps?: StepDef[];
  edges?: EdgeDef[];
  report_from?: string;
}

interface Props {
  value: Record<string, unknown>;
  onChange: (def: Record<string, unknown>) => void;
}

const STEP_TYPES = [
  { value: "llm_call", label: "LLM" },
  { value: "mcp_tool", label: "MCP" },
  { value: "condition", label: "条件" },
  { value: "pass_through", label: "传递" },
];

const PARAM_TYPES = ["string", "integer", "number", "boolean", "array", "object"];

function asDynamicDefinition(value: Record<string, unknown>): DynamicDefinition {
  return value as DynamicDefinition;
}

function newStep(type: string): StepDef {
  const id = `step_${Date.now()}`;
  if (type === "condition") {
    return { id, name: "条件判断", type, field: "", default: "" };
  }
  if (type === "mcp_tool") {
    return { id, name: "调用工具", type, tool_id: "", tool_name: "", arguments: {} };
  }
  if (type === "pass_through") {
    return { id, name: "传递数据", type, source: "", value: {} };
  }
  return {
    id,
    name: "LLM 调用",
    type: "llm_call",
    system_prompt: "你是一个有用的助手。",
    user_prompt: "请处理：{message}",
    temperature: 0.2,
  };
}

export default function WorkflowComposerEditor({ value, onChange }: Props) {
  const [mcpTools, setMcpTools] = useState<MCPTool[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [showJson, setShowJson] = useState(false);
  const def = asDynamicDefinition(value);
  const steps = def.steps || [];
  const edges = def.edges || [];
  const selected = steps.find((step) => step.id === selectedId) || steps[0] || null;
  const nodeIds = useMemo(() => ["start", ...steps.map((step) => step.id), "end"], [steps]);

  useEffect(() => {
    listMCPTools().then(setMcpTools).catch(() => {});
  }, []);

  useEffect(() => {
    if (!selectedId && steps[0]) setSelectedId(steps[0].id);
  }, [selectedId, steps]);

  const notify = (next: DynamicDefinition) => onChange(next as Record<string, unknown>);

  const params = useMemo<ParamDef[]>(() => {
    const properties = def.parameters?.properties || {};
    const required = def.parameters?.required || [];
    return Object.entries(properties).map(([key, prop]) => ({
      key,
      type: prop.type || "string",
      description: prop.description || "",
      required: required.includes(key),
      default: String(prop.default ?? ""),
    }));
  }, [def.parameters]);

  const updateParams = (newParams: ParamDef[]) => {
    const properties: Record<string, { type: string; description: string; default?: unknown }> = {};
    const required: string[] = [];
    for (const param of newParams) {
      if (!param.key.trim()) continue;
      const prop: { type: string; description: string; default?: unknown } = {
        type: param.type,
        description: param.description,
      };
      if (param.default !== "") prop.default = param.default;
      properties[param.key.trim()] = prop;
      if (param.required) required.push(param.key.trim());
    }
    notify({
      ...def,
      parameters: { type: "object", properties, required, additionalProperties: false },
    });
  };

  const addStep = (type: string) => {
    const step = newStep(type);
    notify({ ...def, steps: [...steps, step] });
    setSelectedId(step.id);
  };

  const updateStep = (id: string, patch: Partial<StepDef>) => {
    notify({
      ...def,
      steps: steps.map((step) => (step.id === id ? { ...step, ...patch } : step)),
    });
  };

  const updateStepId = (oldId: string, nextId: string) => {
    notify({
      ...def,
      steps: steps.map((step) => (step.id === oldId ? { ...step, id: nextId } : step)),
      edges: edges.map((edge) => ({
        ...edge,
        from: edge.from === oldId ? nextId : edge.from,
        to: edge.to === oldId ? nextId : edge.to,
      })),
    });
    setSelectedId(nextId);
  };

  const updateStepType = (id: string, type: string) => {
    const template = newStep(type);
    updateStep(id, {
      ...template,
      id,
      name: steps.find((step) => step.id === id)?.name || template.name,
      type,
    });
  };

  const removeStep = (id: string) => {
    const nextSteps = steps.filter((step) => step.id !== id);
    notify({
      ...def,
      steps: nextSteps,
      edges: edges.filter((edge) => edge.from !== id && edge.to !== id),
    });
    setSelectedId(nextSteps[0]?.id || null);
  };

  const moveStep = (id: string, direction: -1 | 1) => {
    const index = steps.findIndex((step) => step.id === id);
    const target = index + direction;
    if (index < 0 || target < 0 || target >= steps.length) return;
    const next = [...steps];
    const [item] = next.splice(index, 1);
    next.splice(target, 0, item);
    notify({ ...def, steps: next });
  };

  const autoLinearEdges = () => {
    const ids = ["start", ...steps.map((step) => step.id), "end"];
    const nextEdges = ids.slice(0, -1).map((from, index) => ({ from, to: ids[index + 1] }));
    notify({ ...def, edges: nextEdges });
  };

  const updateEdge = (index: number, patch: Partial<EdgeDef>) => {
    notify({
      ...def,
      edges: edges.map((edge, i) => (i === index ? { ...edge, ...patch } : edge)),
    });
  };

  return (
    <div className="composer">
      <div className="composer-toolbar">
        {STEP_TYPES.map((type) => (
          <button key={type.value} className="btn-sm" type="button" onClick={() => addStep(type.value)}>
            + {type.label}
          </button>
        ))}
        <button className="btn-sm" type="button" onClick={autoLinearEdges}>
          自动连线
        </button>
        <button className="btn-sm" type="button" onClick={() => setShowJson(!showJson)}>
          {showJson ? "隐藏 JSON" : "JSON"}
        </button>
      </div>

      <div className="composer-grid">
        <aside className="composer-steps">
          {steps.length === 0 && <p className="hint">暂无步骤</p>}
          {steps.map((step, index) => (
            <button
              key={step.id}
              type="button"
              className={`composer-step ${selected?.id === step.id ? "composer-step-active" : ""}`}
              onClick={() => setSelectedId(step.id)}
            >
              <span>{index + 1}</span>
              <strong>{step.name || step.id}</strong>
              <small>{step.type}</small>
            </button>
          ))}
        </aside>

        <main className="composer-main">
          {!selected && <p className="hint">添加一个步骤开始编排</p>}
          {selected && (
            <div className="composer-panel">
              <div className="cap-section-header">
                <h4>步骤</h4>
                <div className="composer-actions">
                  <button className="btn-sm" type="button" onClick={() => moveStep(selected.id, -1)}>上移</button>
                  <button className="btn-sm" type="button" onClick={() => moveStep(selected.id, 1)}>下移</button>
                  <button className="btn-sm btn-danger" type="button" onClick={() => removeStep(selected.id)}>删除</button>
                </div>
              </div>
              <div className="cap-grid">
                <div className="form-field">
                  <label>ID</label>
                  <input value={selected.id} onChange={(event) => updateStepId(selected.id, event.target.value)} />
                </div>
                <div className="form-field">
                  <label>名称</label>
                  <input value={selected.name || ""} onChange={(event) => updateStep(selected.id, { name: event.target.value })} />
                </div>
                <div className="form-field">
                  <label>类型</label>
                  <select value={selected.type} onChange={(event) => updateStepType(selected.id, event.target.value)}>
                    {STEP_TYPES.map((type) => (
                      <option key={type.value} value={type.value}>{type.label}</option>
                    ))}
                  </select>
                </div>
              </div>

              {selected.type === "llm_call" && (
                <>
                  <label className="composer-label">System Prompt</label>
                  <textarea className="ve-textarea" rows={4} value={selected.system_prompt || ""} onChange={(event) => updateStep(selected.id, { system_prompt: event.target.value })} />
                  <label className="composer-label">User Prompt</label>
                  <textarea className="ve-textarea" rows={6} value={selected.user_prompt || ""} onChange={(event) => updateStep(selected.id, { user_prompt: event.target.value })} />
                  <div className="form-field composer-temp">
                    <label>Temperature</label>
                    <input type="number" min={0} max={2} step={0.1} value={String(selected.temperature ?? 0.2)} onChange={(event) => updateStep(selected.id, { temperature: Number(event.target.value) })} />
                  </div>
                </>
              )}

              {selected.type === "mcp_tool" && (
                <>
                  <div className="form-field">
                    <label>MCP 工具</label>
                    <select
                      value={selected.tool_id || ""}
                      onChange={(event) => {
                        const tool = mcpTools.find((item) => item.id === event.target.value);
                        updateStep(selected.id, {
                          tool_id: event.target.value,
                          tool_name: tool?.name || "",
                        });
                      }}
                    >
                      <option value="">选择工具</option>
                      {mcpTools.map((tool) => (
                        <option key={tool.id} value={tool.id}>{tool.id}</option>
                      ))}
                    </select>
                  </div>
                  <label className="composer-label">Arguments JSON</label>
                  <textarea
                    className="ve-textarea"
                    rows={6}
                    value={JSON.stringify(selected.arguments || {}, null, 2)}
                    onChange={(event) => {
                      try {
                        updateStep(selected.id, { arguments: JSON.parse(event.target.value) });
                      } catch {
                        updateStep(selected.id, { arguments: selected.arguments || {} });
                      }
                    }}
                  />
                </>
              )}

              {selected.type === "condition" && (
                <div className="cap-grid">
                  <div className="form-field">
                    <label>字段</label>
                    <input value={selected.field || ""} onChange={(event) => updateStep(selected.id, { field: event.target.value })} />
                  </div>
                  <div className="form-field">
                    <label>默认值</label>
                    <input value={selected.default || ""} onChange={(event) => updateStep(selected.id, { default: event.target.value })} />
                  </div>
                </div>
              )}

              {selected.type === "pass_through" && (
                <div className="cap-grid">
                  <div className="form-field">
                    <label>来源</label>
                    <input value={selected.source || ""} onChange={(event) => updateStep(selected.id, { source: event.target.value })} />
                  </div>
                  <div className="form-field">
                    <label>固定值</label>
                    <input value={typeof selected.value === "string" ? selected.value : ""} onChange={(event) => updateStep(selected.id, { value: event.target.value })} />
                  </div>
                </div>
              )}
            </div>
          )}
        </main>

        <aside className="composer-side">
          <section className="cap-section">
            <div className="cap-section-header">
              <h4>参数</h4>
              <button className="btn-sm" type="button" onClick={() => updateParams([...params, { key: "", type: "string", description: "", required: false, default: "" }])}>+ 添加</button>
            </div>
            {params.map((param, index) => (
              <div key={index} className="composer-param">
                <input placeholder="参数名" value={param.key} onChange={(event) => {
                  const next = [...params];
                  next[index] = { ...param, key: event.target.value };
                  updateParams(next);
                }} />
                <select value={param.type} onChange={(event) => {
                  const next = [...params];
                  next[index] = { ...param, type: event.target.value };
                  updateParams(next);
                }}>
                  {PARAM_TYPES.map((type) => <option key={type} value={type}>{type}</option>)}
                </select>
                <button className="btn-sm btn-danger" type="button" onClick={() => updateParams(params.filter((_, i) => i !== index))}>删除</button>
              </div>
            ))}
          </section>

          <section className="cap-section">
            <div className="cap-section-header">
              <h4>连线</h4>
              <button className="btn-sm" type="button" onClick={() => notify({ ...def, edges: [...edges, { from: "start", to: "end" }] })}>+ 添加</button>
            </div>
            {edges.map((edge, index) => (
              <div key={index} className="composer-edge">
                <select value={edge.from} onChange={(event) => updateEdge(index, { from: event.target.value })}>
                  {nodeIds.map((id) => <option key={id} value={id}>{id}</option>)}
                </select>
                <select value={edge.to} onChange={(event) => updateEdge(index, { to: event.target.value })}>
                  {nodeIds.map((id) => <option key={id} value={id}>{id}</option>)}
                </select>
                <input placeholder="condition" value={edge.condition || ""} onChange={(event) => updateEdge(index, { condition: event.target.value })} />
                <button className="btn-sm btn-danger" type="button" onClick={() => notify({ ...def, edges: edges.filter((_, i) => i !== index) })}>删除</button>
              </div>
            ))}
          </section>

          <section className="cap-section">
            <div className="form-field">
              <label>Report From</label>
              <input value={def.report_from || ""} onChange={(event) => notify({ ...def, report_from: event.target.value })} />
            </div>
          </section>
        </aside>
      </div>

      {showJson && <pre className="ve-preview">{JSON.stringify(def, null, 2)}</pre>}
    </div>
  );
}
