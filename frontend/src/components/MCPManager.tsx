import { useCallback, useEffect, useState } from "react";

interface MCPService {
  id: string; name: string; description: string;
  module: string; command?: string; timeout: number; enabled: boolean;
}

const BASE = "/api/manage/mcp";

export default function MCPManager() {
  const [services, setServices] = useState<MCPService[]>([]);
  const [editing, setEditing] = useState<MCPService | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Form state
  const [fId, setFId] = useState("");
  const [fName, setFName] = useState("");
  const [fDesc, setFDesc] = useState("");
  const [fModule, setFModule] = useState("");
  const [fCommand, setFCommand] = useState("");
  const [fTimeout, setFTimeout] = useState(10);

  const load = useCallback(async () => {
    try {
      const res = await fetch(BASE);
      if (!res.ok) throw new Error("Failed");
      setServices(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const resetForm = () => {
    setFId(""); setFName(""); setFDesc(""); setFModule("");
    setFCommand(""); setFTimeout(10);
  };

  const startCreate = () => {
    setCreating(true); setEditing(null); resetForm();
  };

  const startEdit = (s: MCPService) => {
    setCreating(false); setEditing(s);
    setFId(s.id); setFName(s.name); setFDesc(s.description);
    setFModule(s.module); setFCommand(s.command || ""); setFTimeout(s.timeout);
  };

  const cancel = () => { setCreating(false); setEditing(null); };

  const save = async () => {
    const data = {
      name: fName, module: fModule, description: fDesc,
      command: fCommand || null, timeout: fTimeout,
    };
    try {
      const res = await fetch(creating ? BASE : `${BASE}/${fId}`, {
        method: creating ? "POST" : "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(creating ? { ...data, id: fId, enabled: true } : data),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: "Failed" }));
        throw new Error(err.detail || "Failed");
      }
      cancel();
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "保存失败");
    }
  };

  const remove = async (id: string) => {
    if (!confirm(`删除 MCP 服务 "${id}"？`)) return;
    try {
      await fetch(`${BASE}/${id}`, { method: "DELETE" });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "删除失败");
    }
  };

  const toggle = async (s: MCPService) => {
    try {
      await fetch(`${BASE}/${s.id}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: !s.enabled }),
      });
      load();
    } catch {}
  };

  return (
    <div className="workflow-manager">
      <div className="wm-header">
        <h3>MCP Services</h3>
        <button className="btn-primary" onClick={startCreate}>+ 新增</button>
      </div>

      {error && <div className="error-box">{error}<button onClick={() => setError(null)}>✕</button></div>}

      {!editing && !creating && (
        <div className="wm-list">
          {services.length === 0 && <p className="hint">暂无</p>}
          {services.map((s) => (
            <div key={s.id} className="wm-item">
              <div className="wm-item-info">
                <div className="wm-item-name">
                  <code>{s.id}</code>
                  <span className={`badge ${s.enabled ? "badge-completed" : "badge-failed"}`}>
                    {s.enabled ? "启用" : "禁用"}
                  </span>
                </div>
                <div className="wm-item-title">{s.name}</div>
                <div className="wm-item-desc">
                  module: <code>{s.module}</code>
                  {s.command && <> | command: <code>{s.command}</code></>}
                  {" "}| timeout: {s.timeout}s
                </div>
                {s.description && <div className="wm-item-desc">{s.description}</div>}
              </div>
              <div className="wm-item-actions">
                <button className="btn-sm" onClick={() => toggle(s)}>
                  {s.enabled ? "禁用" : "启用"}
                </button>
                <button className="btn-sm" onClick={() => startEdit(s)}>编辑</button>
                <button className="btn-sm btn-danger" onClick={() => remove(s.id)}>删除</button>
              </div>
            </div>
          ))}
        </div>
      )}

      {(editing || creating) && (
        <div className="wm-editor">
          <h4>{creating ? "新增 MCP 服务" : `编辑: ${fId}`}</h4>
          <div className="form-field">
            <label>ID</label>
            <input value={fId} onChange={(e) => setFId(e.target.value)} disabled={!creating} placeholder="e.g. my_service" />
          </div>
          <div className="form-field">
            <label>名称</label>
            <input value={fName} onChange={(e) => setFName(e.target.value)} />
          </div>
          <div className="form-field">
            <label>模块 (Python import path)</label>
            <input value={fModule} onChange={(e) => setFModule(e.target.value)} placeholder="e.g. app.mcp_server.arithmetic" />
          </div>
          <div className="form-field">
            <label>命令 (可选，替代模块)</label>
            <input value={fCommand} onChange={(e) => setFCommand(e.target.value)} placeholder="e.g. python -m my_mcp" />
          </div>
          <div className="form-field">
            <label>超时 (秒)</label>
            <input type="number" value={fTimeout} onChange={(e) => setFTimeout(parseFloat(e.target.value) || 10)} />
          </div>
          <div className="form-field">
            <label>描述</label>
            <input value={fDesc} onChange={(e) => setFDesc(e.target.value)} />
          </div>
          <div className="wm-editor-actions">
            <button className="btn-primary" onClick={save}>保存</button>
            <button className="btn-sm" onClick={cancel}>取消</button>
          </div>
        </div>
      )}
    </div>
  );
}
