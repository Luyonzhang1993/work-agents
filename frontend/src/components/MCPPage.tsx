import { useCallback, useEffect, useState } from "react";

interface MCPService {
  id: string; name: string; description: string;
  module: string; command?: string; timeout: number; enabled: boolean;
}

interface MCPTool {
  id: string; service: string; name: string; description: string;
}

const TOOLS_API = "/api/mcp/tools";
const SVC_API = "/api/manage/mcp";

export default function MCPPage() {
  const [tools, setTools] = useState<MCPTool[]>([]);
  const [services, setServices] = useState<MCPService[]>([]);
  const [search, setSearch] = useState("");
  const [selectedSvc, setSelectedSvc] = useState<string | null>(null);
  const [editing, setEditing] = useState<MCPService | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [fId, setFId] = useState(""); const [fName, setFName] = useState("");
  const [fDesc, setFDesc] = useState(""); const [fModule, setFModule] = useState("");
  const [fCommand, setFCommand] = useState(""); const [fTimeout, setFTimeout] = useState(10);

  const load = useCallback(async () => {
    try {
      const [t, s] = await Promise.all([
        fetch(TOOLS_API).then(r => r.json()),
        fetch(SVC_API).then(r => r.json()),
      ]);
      setTools(t.tools || []);
      setServices(s);
    } catch (err) {
      setError(err instanceof Error ? err.message : "加载失败");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  const resetForm = () => { setFId(""); setFName(""); setFDesc(""); setFModule(""); setFCommand(""); setFTimeout(10); };
  const startCreate = () => { setCreating(true); setEditing(null); resetForm(); };
  const startEdit = (s: MCPService) => {
    setCreating(false); setEditing(s);
    setFId(s.id); setFName(s.name); setFDesc(s.description);
    setFModule(s.module); setFCommand(s.command || ""); setFTimeout(s.timeout);
  };
  const cancel = () => { setCreating(false); setEditing(null); };

  const save = async () => {
    const data = { name: fName, module: fModule, description: fDesc, command: fCommand || null, timeout: fTimeout };
    try {
      const res = await fetch(creating ? SVC_API : `${SVC_API}/${fId}`, {
        method: creating ? "POST" : "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(creating ? { ...data, id: fId, enabled: true } : data),
      });
      if (!res.ok) { const err = await res.json().catch(() => ({ detail: "Failed" })); throw new Error(err.detail); }
      cancel(); load();
    } catch (err) { setError(err instanceof Error ? err.message : "保存失败"); }
  };

  const remove = async (id: string) => {
    if (!confirm(`删除 "${id}"？`)) return;
    await fetch(`${SVC_API}/${id}`, { method: "DELETE" }); load();
  };

  const toggle = async (s: MCPService) => {
    await fetch(`${SVC_API}/${s.id}`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ enabled: !s.enabled }) });
    load();
  };

  // Group tools by service
  const grouped = tools.reduce<Record<string, MCPTool[]>>((acc, t) => {
    (acc[t.service] ??= []).push(t); return acc;
  }, {});

  const filtered: Record<string, MCPTool[]> = search
    ? Object.fromEntries(
        Object.entries(grouped)
          .map(([svc, ts]) => [
            svc,
            ts.filter(
              (t: MCPTool) =>
                t.name.toLowerCase().includes(search.toLowerCase()) ||
                t.description.toLowerCase().includes(search.toLowerCase()),
            ),
          ] as [string, MCPTool[]])
          .filter(([, ts]) => ts.length > 0),
      )
    : grouped;

  return (
    <div className="mcp-page">
      <div className="mcp-sidebar">
        <div className="mcp-sidebar-header">
          <h3>MCP Services</h3>
          <button className="btn-sm" onClick={startCreate}>+ 新增</button>
        </div>
        {services.map((s) => (
          <div
            key={s.id}
            className={`mcp-svc-item ${selectedSvc === s.id ? "mcp-svc-active" : ""} ${!s.enabled ? "mcp-svc-disabled" : ""}`}
            onClick={() => setSelectedSvc(s.id === selectedSvc ? null : s.id)}
          >
            <div className="mcp-svc-name">
              <span className={`badge ${s.enabled ? "badge-completed" : "badge-failed"}`}>
                {s.enabled ? "●" : "○"}
              </span>
              {s.id}
            </div>
            <div className="mcp-svc-count">{grouped[s.id]?.length || 0} tools</div>
            <div className="mcp-svc-actions">
              <button className="btn-sm" onClick={(e) => { e.stopPropagation(); startEdit(s); }}>✎</button>
              <button className="btn-sm btn-danger" onClick={(e) => { e.stopPropagation(); remove(s.id); }}>✕</button>
            </div>
          </div>
        ))}
      </div>

      <div className="mcp-main">
        {/* Search */}
        <div className="mcp-toolbar">
          <input
            className="mcp-search"
            placeholder="搜索工具..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>

        {error && <div className="error-box">{error}<button onClick={() => setError(null)}>✕</button></div>}

        {/* Editor modal */}
        {(editing || creating) && (
          <div className="mcp-editor-overlay" onClick={cancel}>
            <div className="mcp-editor" onClick={(e) => e.stopPropagation()}>
              <h4>{creating ? "新增 MCP 服务" : `编辑: ${fId}`}</h4>
              <div className="form-field"><label>ID</label><input value={fId} onChange={e => setFId(e.target.value)} disabled={!creating} /></div>
              <div className="form-field"><label>名称</label><input value={fName} onChange={e => setFName(e.target.value)} /></div>
              <div className="form-field"><label>模块</label><input value={fModule} onChange={e => setFModule(e.target.value)} /></div>
              <div className="form-field"><label>命令 (可选)</label><input value={fCommand} onChange={e => setFCommand(e.target.value)} /></div>
              <div className="form-field"><label>超时 (秒)</label><input type="number" value={fTimeout} onChange={e => setFTimeout(parseFloat(e.target.value)||10)} /></div>
              <div className="form-field"><label>描述</label><input value={fDesc} onChange={e => setFDesc(e.target.value)} /></div>
              <div className="wm-editor-actions">
                <button className="btn-primary" onClick={save}>保存</button>
                <button className="btn-sm" onClick={cancel}>取消</button>
              </div>
            </div>
          </div>
        )}

        {/* Tools grid */}
        {Object.entries(filtered).map(([svc, ts]) => (
          <div key={svc} className="mcp-group">
            <div className="mcp-group-header" onClick={() => setSelectedSvc(selectedSvc === svc ? null : svc)}>
              <h4>{svc}</h4>
              <span className="mcp-group-count">{ts.length} tools</span>
              <span className="mcp-group-arrow">{selectedSvc === svc ? "▾" : "▸"}</span>
            </div>
            {(selectedSvc === svc || !selectedSvc) && (
              <div className="mcp-cards">
                {ts.map((t) => (
                  <div key={t.id} className="mcp-card">
                    <div className="mcp-card-header">
                      <code>{t.name}</code>
                    </div>
                    <div className="mcp-card-body">
                      <p>{t.description || "No description"}</p>
                    </div>
                    <div className="mcp-card-footer">
                      <code className="mcp-card-id">{t.id}</code>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        ))}

        {Object.keys(filtered).length === 0 && (
          <div className="mcp-empty">
            <p>{search ? "无匹配工具" : "暂无 MCP 服务"}</p>
            {!search && <p className="hint">点击左侧 "+ 新增" 添加 MCP 服务</p>}
          </div>
        )}
      </div>
    </div>
  );
}
