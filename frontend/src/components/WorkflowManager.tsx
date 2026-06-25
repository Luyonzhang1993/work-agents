import { useCallback, useEffect, useState } from "react";
import type { WorkflowDef } from "../api/client";
import {
  listManagedWorkflows,
  createManagedWorkflow,
  updateManagedWorkflow,
  deleteManagedWorkflow,
} from "../api/client";

const EMPTY_DEF: WorkflowDef = {
  id: "",
  name: "",
  description: "",
  definition: {},
  enabled: true,
  created_at: "",
  updated_at: "",
};

const EXAMPLE_DEFINITION = {
  parameters: {
    type: "object",
    properties: {
      message: { type: "string", description: "输入信息" },
    },
    required: ["message"],
  },
  steps: [
    {
      id: "analyze",
      name: "分析内容",
      type: "llm_call",
      system_prompt: "你是一个有用的助手。",
      user_prompt: "请分析以下内容：{message}",
      temperature: 0.7,
    },
    {
      id: "summarize",
      name: "总结输出",
      type: "llm_call",
      system_prompt: "你是一个总结专家。",
      user_prompt: "总结以下分析结果：{analyze}",
      temperature: 0.3,
    },
  ],
  edges: [
    { from: "start", to: "analyze" },
    { from: "analyze", to: "summarize" },
    { from: "summarize", to: "end" },
  ],
};

export default function WorkflowManager() {
  const [workflows, setWorkflows] = useState<WorkflowDef[]>([]);
  const [editing, setEditing] = useState<WorkflowDef | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [defText, setDefText] = useState("");
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [wfId, setWfId] = useState("");
  const [enabled, setEnabled] = useState(true);

  const load = useCallback(async () => {
    try {
      const data = await listManagedWorkflows();
      setWorkflows(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const startCreate = () => {
    setCreating(true);
    setEditing(null);
    setWfId("");
    setName("");
    setDesc("");
    setDefText(JSON.stringify(EXAMPLE_DEFINITION, null, 2));
    setEnabled(true);
    setJsonError(null);
  };

  const startEdit = (wf: WorkflowDef) => {
    setCreating(false);
    setEditing(wf);
    setWfId(wf.id);
    setName(wf.name);
    setDesc(wf.description);
    setDefText(JSON.stringify(wf.definition, null, 2));
    setEnabled(wf.enabled);
    setJsonError(null);
  };

  const cancelEdit = () => {
    setCreating(false);
    setEditing(null);
  };

  const handleSave = async () => {
    let definition: Record<string, unknown>;
    try {
      definition = JSON.parse(defText);
    } catch {
      setJsonError("JSON 格式错误");
      return;
    }
    setJsonError(null);

    try {
      if (creating) {
        await createManagedWorkflow({
          id: wfId,
          name,
          description: desc,
          definition,
          enabled,
          created_at: "",
          updated_at: "",
        });
      } else if (editing) {
        await updateManagedWorkflow(editing.id, {
          name,
          description: desc,
          definition,
          enabled,
        });
      }
      cancelEdit();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm(`确定删除 workflow "${id}"？`)) return;
    try {
      await deleteManagedWorkflow(id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    }
  };

  const handleToggle = async (wf: WorkflowDef) => {
    try {
      await updateManagedWorkflow(wf.id, { enabled: !wf.enabled });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "操作失败");
    }
  };

  return (
    <div className="workflow-manager">
      <div className="wm-header">
        <h3>Workflow 管理</h3>
        <button className="btn-primary" onClick={startCreate}>
          + 新建
        </button>
      </div>

      {error && (
        <div className="error-box">
          {error}
          <button onClick={() => setError(null)}>✕</button>
        </div>
      )}

      {/* List */}
      {!editing && !creating && (
        <div className="wm-list">
          {workflows.length === 0 && (
            <p className="hint">暂无自定义 workflow，点击"新建"创建</p>
          )}
          {workflows.map((wf) => (
            <div key={wf.id} className="wm-item">
              <div className="wm-item-info">
                <div className="wm-item-name">
                  <code>{wf.id}</code>
                  <span className={`badge ${wf.enabled ? "badge-completed" : "badge-failed"}`}>
                    {wf.enabled ? "启用" : "禁用"}
                  </span>
                </div>
                <div className="wm-item-title">{wf.name}</div>
                <div className="wm-item-desc">{wf.description}</div>
                <div className="wm-item-meta">
                  更新于 {new Date(wf.updated_at).toLocaleString()}
                </div>
              </div>
              <div className="wm-item-actions">
                <button className="btn-sm" onClick={() => handleToggle(wf)}>
                  {wf.enabled ? "禁用" : "启用"}
                </button>
                <button className="btn-sm" onClick={() => startEdit(wf)}>
                  编辑
                </button>
                <button className="btn-sm btn-danger" onClick={() => handleDelete(wf.id)}>
                  删除
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Editor */}
      {(editing || creating) && (
        <div className="wm-editor">
          <h4>{creating ? "新建 Workflow" : `编辑: ${wfId}`}</h4>

          <div className="form-field">
            <label>ID (英文小写+数字+下划线)</label>
            <input
              type="text"
              value={wfId}
              onChange={(e) => setWfId(e.target.value)}
              disabled={!creating}
              placeholder="e.g. my_custom_workflow"
            />
          </div>

          <div className="form-field">
            <label>名称</label>
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Workflow 显示名称"
            />
          </div>

          <div className="form-field">
            <label>描述</label>
            <input
              type="text"
              value={desc}
              onChange={(e) => setDesc(e.target.value)}
              placeholder="简要描述"
            />
          </div>

          <div className="form-field">
            <label>
              <input
                type="checkbox"
                checked={enabled}
                onChange={(e) => setEnabled(e.target.checked)}
              />
              {" "}启用
            </label>
          </div>

          <div className="form-field">
            <label>Definition (JSON)</label>
            <textarea
              className="wm-def-editor"
              value={defText}
              onChange={(e) => {
                setDefText(e.target.value);
                setJsonError(null);
              }}
              rows={25}
              spellCheck={false}
            />
            {jsonError && <div className="error-box">{jsonError}</div>}
          </div>

          <div className="wm-editor-actions">
            <button className="btn-primary" onClick={handleSave}>
              保存
            </button>
            <button className="btn-sm" onClick={cancelEdit}>
              取消
            </button>
          </div>

          <details className="wm-help">
            <summary>Definition 格式说明</summary>
            <pre>{`{
  "parameters": {           // 输入参数 schema
    "type": "object",
    "properties": {
      "message": {"type": "string"}
    }
  },
  "steps": [                 // 步骤列表
    {
      "id": "step1",         // 唯一 ID
      "name": "分析",        // 步骤名
      "type": "llm_call",    // llm_call | mcp_tool
      "system_prompt": "...",
      "user_prompt": "处理: {message}",
      "temperature": 0.7
    }
  ],
  "edges": [                 // 执行顺序
    {"from": "start", "to": "step1"},
    {"from": "step1", "to": "end"}
  ]
}`}</pre>
          </details>
        </div>
      )}
    </div>
  );
}
