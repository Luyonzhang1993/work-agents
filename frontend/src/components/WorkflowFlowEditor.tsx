import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ReactFlow,
  Controls,
  Background,
  MiniMap,
  addEdge,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
  type Connection,
  MarkerType,
  Handle,
  Position,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { listMCPTools, type MCPTool } from "../api/client";

// ── Types ──

interface ParamDef { key: string; type: string; description: string; required: boolean; default: string; }
interface StepDef {
  id: string; name: string; type: string; system_prompt: string;
  user_prompt: string; temperature: number; tool_name?: string; tool_id?: string;
  field?: string; default?: string;
}
interface EdgeDef { from: string; to: string; condition?: string; }

interface VisualDef {
  parameters: {
    type: "object"; properties: Record<string, { type: string; description: string; default?: unknown }>;
    required: string[]; additionalProperties: false;
  };
  steps: StepDef[];
  edges: EdgeDef[];
}

interface Props { value: VisualDef; onChange: (def: VisualDef) => void; }

const STEP_TYPES = [
  { value: "llm_call", label: "LLM 调用" },
  { value: "condition", label: "条件分支" },
  { value: "mcp_tool", label: "MCP 工具" },
  { value: "pass_through", label: "数据传递" },
];
const PARAM_TYPES = ["string", "integer", "number", "boolean", "array"];

const NODE_COLORS: Record<string, string> = {
  start: "#3fb950", end: "#f85149",
  llm_call: "#58a6ff", condition: "#bc8cff",
  mcp_tool: "#d2991d", pass_through: "#8b949e",
};

const NODE_ICONS: Record<string, string> = {
  start: "▶", end: "⏹", llm_call: "🤖", condition: "🔀", mcp_tool: "🔧", pass_through: "➡",
};

// ── Custom Node ──

function StepNode({ data }: { data: { label: string; stepType: string; isSelected: boolean } }) {
  const color = NODE_COLORS[data.stepType] || "#58a6ff";
  return (
    <div className="flow-node" style={{
      borderColor: data.isSelected ? "#fff" : color,
      background: data.isSelected ? `${color}22` : "#161b22",
    }}>
      <Handle type="target" position={Position.Left}
        style={{ width: 12, height: 12, border: `2px solid ${color}`, background: "#161b22" }} />
      <div className="flow-node-icon">{NODE_ICONS[data.stepType] || "⚙"}</div>
      <div className="flow-node-label">{data.label || data.stepType}</div>
      <div className="flow-node-type">{data.stepType}</div>
      <Handle type="source" position={Position.Right}
        style={{ width: 12, height: 12, border: `2px solid ${color}`, background: "#161b22" }} />
    </div>
  );
}

const nodeTypes = { stepNode: StepNode };

export default function WorkflowFlowEditor({ value, onChange }: Props) {
  const [mcpTools, setMcpTools] = useState<MCPTool[]>([]);
  const [selectedStep, setSelectedStep] = useState<string | null>(null);
  const [selectedEdge, setSelectedEdge] = useState<number | null>(null);
  const [showPreview, setShowPreview] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);

  useEffect(() => { listMCPTools().then(setMcpTools).catch(() => {}); }, []);

  const def = value;
  const steps = def.steps || [];
  const edges = def.edges || [];

  const stepMap = useMemo(() => { const m: Record<string, StepDef> = {}; for (const s of steps) m[s.id] = s; return m; }, [steps]);
  const selected = selectedStep ? stepMap[selectedStep] : null;

  const notify = (updated: VisualDef) => onChange({ ...updated });

  // ── ReactFlow nodes/edges ──

  const initialNodes: Node[] = useMemo(() => {
    const nodes: Node[] = [
      { id: "start", type: "stepNode", position: { x: 50, y: 250 },
        data: { label: "开始", stepType: "start", isSelected: selectedStep === "start" }, draggable: true },
    ];
    steps.forEach((s, i) => {
      nodes.push({ id: s.id, type: "stepNode", position: { x: 300, y: 50 + i * 140 },
        data: { label: s.name || s.id, stepType: s.type, isSelected: selectedStep === s.id }, draggable: true });
    });
    nodes.push({ id: "end", type: "stepNode", position: { x: 600, y: 250 },
      data: { label: "结束", stepType: "end", isSelected: selectedStep === "end" }, draggable: true });
    return nodes;
  }, [steps, selectedStep]);

  const initialEdges: Edge[] = useMemo(() => {
    return edges.map((e, i) => ({
      id: `e${i}`, source: e.from, target: e.to,
      animated: true, style: { stroke: e.condition ? "#bc8cff" : "#58a6ff", strokeWidth: 2 },
      markerEnd: { type: MarkerType.ArrowClosed, color: e.condition ? "#bc8cff" : "#58a6ff" },
      data: { edgeIndex: i, condition: e.condition || "" },
    }));
  }, [edges]);

  const [rfNodes, setRfNodes, onNodesChange] = useNodesState(initialNodes);
  const [rfEdges, setRfEdges, onEdgesChange] = useEdgesState(initialEdges);

  useEffect(() => { setRfNodes(initialNodes); }, [initialNodes, setRfNodes]);
  useEffect(() => { setRfEdges(initialEdges); }, [initialEdges, setRfEdges]);

  // Sync definition edges ← ReactFlow edges (catches keyboard deletes)
  const handleEdgesChange = useCallback(
    (changes: Parameters<typeof onEdgesChange>[0]) => {
      onEdgesChange(changes);
      // After ReactFlow processes the change, sync removals back
      setTimeout(() => {
        setRfEdges((currentEdges) => {
          const newDefEdges: EdgeDef[] = currentEdges.map((e) => ({
            from: e.source,
            to: e.target,
            condition: (e.data as Record<string, unknown> | undefined)?.condition as string | undefined,
          }));
          notify({ ...def, edges: newDefEdges });
          return currentEdges;
        });
      }, 0);
    },
    [def, notify, onEdgesChange, setRfEdges],
  );

  // ── Connection handler ──

  const onConnect = useCallback((conn: Connection) => {
    // Check for duplicate
    const exists = edges.some((e) => e.from === conn.source && e.to === conn.target);
    if (exists) return;
    const newEdge: EdgeDef = { from: conn.source, to: conn.target };
    setRfEdges((eds) => {
      const updated = addEdge({
        ...conn,
        data: { condition: "" },
        animated: true,
        style: { stroke: "#58a6ff", strokeWidth: 2 },
        markerEnd: { type: MarkerType.ArrowClosed, color: "#58a6ff" },
      } as Connection & { data?: Record<string, unknown> }, eds);
      return updated;
    });
    notify({ ...def, edges: [...edges, newEdge] });
  }, [def, edges, notify, setRfEdges]);

  const onNodeClick = useCallback((_: React.MouseEvent, node: Node) => {
    const id = node.id;
    setSelectedStep(id === "start" || id === "end" ? null : id);
    setSelectedEdge(null);
  }, []);

  const onEdgeClick = useCallback((_: React.MouseEvent, edge: Edge) => {
    const idx = (edge.data as Record<string, unknown> | undefined)?.edgeIndex;
    if (typeof idx === "number") {
      setSelectedEdge(idx);
      setSelectedStep(null);
    }
  }, []);

  const onPaneClick = useCallback(() => { setSelectedStep(null); setSelectedEdge(null); }, []);

  // ── Step mutations ──

  const updateStep = (id: string, fields: Partial<StepDef>) => {
    const updated = steps.map((s) => (s.id === id ? { ...s, ...fields } : s));
    notify({ ...def, steps: updated });
  };

  const addStep = (type: string) => {
    const id = `step_${Date.now()}`;
    const base: StepDef = { id, name: "", type, system_prompt: "", user_prompt: "", temperature: 0.7 };
    if (type === "condition") { base.field = ""; base.default = ""; }
    notify({ ...def, steps: [...steps, base] });
    setSelectedStep(id);
  };

  const removeStep = (id: string) => {
    notify({ ...def, steps: steps.filter((s) => s.id !== id), edges: edges.filter((e) => e.from !== id && e.to !== id) });
    setSelectedStep(null);
  };

  const autoEdges = () => {
    const ids = ["start", ...steps.map((s) => s.id), "end"];
    const newEdges: EdgeDef[] = [];
    for (let i = 0; i < ids.length - 1; i++) newEdges.push({ from: ids[i], to: ids[i + 1] });
    notify({ ...def, edges: newEdges });
  };

  // ── Edge mutations ──

  const updateEdge = (idx: number, fields: Partial<EdgeDef>) => {
    const updated = edges.map((e, i) => (i === idx ? { ...e, ...fields } : e));
    notify({ ...def, edges: updated });
  };

  const removeEdge = (idx: number) => {
    notify({ ...def, edges: edges.filter((_, i) => i !== idx) });
    setSelectedEdge(null);
  };

  // ── Parameters ──

  const params: ParamDef[] = Object.entries(def.parameters?.properties || {}).map(([key, prop]) => ({
    key, type: (prop as Record<string, unknown>).type as string || "string",
    description: (prop as Record<string, unknown>).description as string || "",
    required: def.parameters?.required?.includes(key) || false,
    default: String((prop as Record<string, unknown>).default ?? ""),
  }));

  const updateParams = (newParams: ParamDef[]) => {
    const props: Record<string, { type: string; description: string; default?: unknown }> = {};
    const req: string[] = [];
    for (const p of newParams) {
      const prop: { type: string; description: string; default?: unknown } = { type: p.type, description: p.description };
      if (p.default !== "") prop.default = p.default;
      props[p.key] = prop;
      if (p.required) req.push(p.key);
    }
    notify({ ...def, parameters: { type: "object", properties: props, required: req, additionalProperties: false } });
  };

  const cls = fullscreen ? "flow-editor flow-editor-fullscreen" : "flow-editor";

  return (
    <div className={cls}>
      {/* Toolbar */}
      <div className="flow-toolbar">
        {STEP_TYPES.map((t) => (
          <button key={t.value} className="btn-sm" onClick={() => addStep(t.value)}>
            + {t.label}
          </button>
        ))}
        <span className="flow-sep" />
        <button className="btn-sm" onClick={autoEdges}>🔗 自动连线</button>
        <button className="btn-sm" onClick={() => setShowPreview(!showPreview)}>
          {showPreview ? "隐藏 JSON" : "📄 JSON"}
        </button>
        <span className="flow-sep" />
        <button className="btn-sm" onClick={() => setFullscreen(!fullscreen)}>
          {fullscreen ? "⤓ 退出全屏" : "⤢ 全屏"}
        </button>
      </div>

      {/* Body */}
      <div className="flow-body">
        <div className="flow-canvas">
          <ReactFlow
            nodes={rfNodes} edges={rfEdges}
            onNodesChange={onNodesChange}            onEdgesChange={handleEdgesChange}
            onConnect={onConnect} onNodeClick={onNodeClick} onEdgeClick={onEdgeClick}
            onPaneClick={onPaneClick} nodeTypes={nodeTypes}
            fitView deleteKeyCode={["Backspace", "Delete"]}
            connectionLineStyle={{ stroke: "#58a6ff", strokeWidth: 2 }}
            defaultEdgeOptions={{ animated: true }}
            snapToGrid
          >
            <Controls />
            <Background gap={20} color="#30363d" />
            <MiniMap nodeColor={(n) => NODE_COLORS[(n.data as { stepType: string }).stepType] || "#58a6ff"}
              maskColor="rgba(0,0,0,0.7)" />
          </ReactFlow>
        </div>

        {/* Sidebar */}
        <div className="flow-sidebar">
          {/* Step editing */}
          {selected && (
            <>
              <div className="flow-sidebar-header">
                <h4>{NODE_ICONS[selected.type] || ""} {selected.name || selected.id}</h4>
                <button className="btn-sm btn-danger" onClick={() => removeStep(selected.id)}>删除</button>
              </div>
              <div className="form-field">
                <label>ID</label>
                <input value={selected.id} onChange={(e) => updateStep(selected.id, { id: e.target.value })} />
              </div>
              <div className="form-field">
                <label>名称</label>
                <input value={selected.name} onChange={(e) => updateStep(selected.id, { name: e.target.value })} />
              </div>

              {selected.type === "llm_call" && (
                <>
                  <div className="form-field">
                    <label>System Prompt</label>
                    <textarea rows={3} value={selected.system_prompt}
                      onChange={(e) => updateStep(selected.id, { system_prompt: e.target.value })} />
                  </div>
                  <div className="form-field">
                    <label>User Prompt</label>
                    <textarea rows={4} value={selected.user_prompt}
                      onChange={(e) => updateStep(selected.id, { user_prompt: e.target.value })} />
                  </div>
                  <div className="form-field">
                    <label>Temperature</label>
                    <input type="number" min={0} max={2} step={0.1} value={selected.temperature}
                      onChange={(e) => updateStep(selected.id, { temperature: parseFloat(e.target.value) || 0.7 })} />
                  </div>
                </>
              )}

              {selected.type === "condition" && (
                <>
                  <div className="form-field">
                    <label>判断字段 (state中的key)</label>
                    <input value={selected.field || ""} placeholder="e.g. budget_level"
                      onChange={(e) => updateStep(selected.id, { field: e.target.value })} />
                  </div>
                  <div className="form-field">
                    <label>默认值</label>
                    <input value={selected.default || ""} placeholder="e.g. comfort"
                      onChange={(e) => updateStep(selected.id, { default: e.target.value })} />
                  </div>
                  <p className="hint">
                    从此节点连出的线上设置 condition 值，匹配的才会执行。无条件值的边作为默认路径。
                  </p>
                </>
              )}

              {selected.type === "mcp_tool" && (
                <div className="form-field">
                  <label>MCP 工具</label>
                  <select value={selected.tool_id || ""} onChange={(e) => {
                    const t = mcpTools.find((x) => x.id === e.target.value);
                    updateStep(selected.id, { tool_id: e.target.value, tool_name: t ? `${t.service}.${t.name}` : "" });
                  }}>
                    <option value="">-- 选择 --</option>
                    {mcpTools.map((t) => (
                      <option key={t.id} value={t.id}>{t.service}/{t.name}</option>
                    ))}
                  </select>
                </div>
              )}
            </>
          )}

          {/* Edge editing */}
          {selectedEdge !== null && edges[selectedEdge] && (
            <>
              <div className="flow-sidebar-header">
                <h4>🔗 连线条件</h4>
                <button className="btn-sm btn-danger" onClick={() => removeEdge(selectedEdge!)}>删除</button>
              </div>
              <div className="form-field">
                <label>来源</label>
                <input value={edges[selectedEdge].from} disabled />
              </div>
              <div className="form-field">
                <label>目标</label>
                <input value={edges[selectedEdge].to} disabled />
              </div>
              <div className="form-field">
                <label>条件值 (条件分支时填写，留空为默认路径)</label>
                <input
                  value={edges[selectedEdge].condition || ""}
                  onChange={(e) => updateEdge(selectedEdge!, { condition: e.target.value || undefined })}
                  placeholder="e.g. budget / comfort / premium"
                />
              </div>
            </>
          )}

          {/* Default: parameters */}
          {!selected && selectedEdge === null && (
            <div className="flow-sidebar-empty">
              <p>👆 点击步骤节点或连线进行编辑</p>
              <hr />
              <h4>输入参数</h4>
              <button className="btn-sm" onClick={() => updateParams([...params, { key: "", type: "string", description: "", required: false, default: "" }])}>
                + 添加
              </button>
              {params.map((p, i) => (
                <div key={i} className="flow-param-row">
                  <input className="flow-param-input" placeholder="参数名" value={p.key}
                    onChange={(e) => { const cp = [...params]; cp[i].key = e.target.value; updateParams(cp); }} />
                  <select value={p.type}
                    onChange={(e) => { const cp = [...params]; cp[i].type = e.target.value; updateParams(cp); }}>
                    {PARAM_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                  <label><input type="checkbox" checked={p.required}
                    onChange={(e) => { const cp = [...params]; cp[i].required = e.target.checked; updateParams(cp); }} />必填</label>
                  <button className="btn-sm btn-danger" onClick={() => updateParams(params.filter((_, j) => j !== i))}>✕</button>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {showPreview && (
        <div className="flow-preview"><pre>{JSON.stringify(def, null, 2)}</pre></div>
      )}
    </div>
  );
}
