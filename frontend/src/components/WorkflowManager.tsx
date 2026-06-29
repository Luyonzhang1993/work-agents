import { useCallback, useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import type { WorkflowDef } from "../api/client";
import {
  listManagedWorkflows,
  createManagedWorkflow,
  updateManagedWorkflow,
  deleteManagedWorkflow,
} from "../api/client";
import WorkflowVisualEditor from "./WorkflowVisualEditor";
import WorkflowFlowEditor from "./WorkflowFlowEditor";

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
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const isNew = id === "new";
  const isEditing = !!id && !isNew;

  const [workflows, setWorkflows] = useState<WorkflowDef[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [visualDef, setVisualDef] = useState<Record<string, unknown>>({ ...EXAMPLE_DEFINITION });
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [wfId, setWfId] = useState("");
  const [useFlowEditor, setUseFlowEditor] = useState(true);

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

  // When entering edit mode via URL, fetch + populate
  useEffect(() => {
    if (isNew) {
      setWfId("");
      setName("");
      setDesc("");
      setVisualDef({ ...EXAMPLE_DEFINITION });
    } else if (isEditing && id) {
      const wf = workflows.find((w) => w.id === id);
      if (wf) {
        setWfId(wf.id);
        setName(wf.name);
        setDesc(wf.description);
        const def = typeof wf.definition === "string"
          ? JSON.parse(wf.definition)
          : wf.definition;
        setVisualDef(def && typeof def === "object" ? { ...def } as Record<string, unknown> : { ...EXAMPLE_DEFINITION });
      }
    }
  }, [id, isNew, isEditing, workflows]);

  const goList = () => navigate("/manage");

  const handleSave = async () => {
    const definition = visualDef;

    try {
      if (isNew) {
        await createManagedWorkflow({
          id: wfId,
          name,
          description: desc,
          definition,
          enabled: true,
          created_at: "",
          updated_at: "",
        });
      } else if (isEditing && id) {
        await updateManagedWorkflow(id, {
          name,
          description: desc,
          definition,
        });
      }
      goList();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    }
  };

  const handleDelete = async (wfId: string) => {
    if (!confirm(`确定删除 workflow "${wfId}"？`)) return;
    try {
      await deleteManagedWorkflow(wfId);
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

  // ── Editor view ──
  if (isNew || isEditing) {
    return (
      <div className="workflow-manager">
        <div className="wm-header">
          <h3>
            <button className="btn-sm" onClick={goList} title="返回列表">
              ← 返回
            </button>
            {" "}
            {isNew ? "新建 Workflow" : `编辑: ${wfId}`}
          </h3>
        </div>

        {error && (
          <div className="error-box">
            {error}
            <button onClick={() => setError(null)}>✕</button>
          </div>
        )}

        <div className="wm-editor">
          <div className="form-field">
            <label>ID (英文小写+数字+下划线)</label>
            <input
              type="text"
              value={wfId}
              onChange={(e) => setWfId(e.target.value)}
              disabled={!isNew}
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

          <div style={{ marginBottom: 10 }}>
            <label className="toggle-label" style={{ display: 'inline-flex', cursor: 'pointer' }}>
              <input type="checkbox" checked={useFlowEditor}
                onChange={(e) => setUseFlowEditor(e.target.checked)} />
              {" "}画布拖拽编辑
            </label>
          </div>

          {useFlowEditor ? (
            <WorkflowFlowEditor
              value={visualDef as never}
              onChange={(d) => setVisualDef(d as never)}
            />
          ) : (
            <WorkflowVisualEditor
              value={visualDef as never}
              onChange={(d) => setVisualDef(d as never)}
            />
          )}

          <div className="wm-editor-actions">
            <button className="btn-primary" onClick={handleSave}>
              保存
            </button>
            <button className="btn-sm" onClick={goList}>
              取消
            </button>
          </div>
        </div>
      </div>
    );
  }

  // ── List view ──
  return (
    <div className="workflow-manager">
      <div className="wm-header">
        <h3>Workflow 管理</h3>
        <button className="btn-primary" onClick={() => navigate("/manage/new")}>
          + 新建
        </button>
      </div>

      {error && (
        <div className="error-box">
          {error}
          <button onClick={() => setError(null)}>✕</button>
        </div>
      )}

      <div className="wm-list">
        {workflows.length === 0 && (
          <p className="hint">暂无 workflow，点击"新建"创建</p>
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
              <button className="btn-sm" onClick={() => navigate(`/manage/${wf.id}`)}>
                编辑
              </button>
              <button className="btn-sm btn-danger" onClick={() => handleDelete(wf.id)}>
                删除
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
