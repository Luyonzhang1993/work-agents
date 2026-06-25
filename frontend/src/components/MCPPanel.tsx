import { useEffect, useState } from "react";
import type { MCPTool } from "../types";
import { listMCPTools } from "../api/client";

export default function MCPPanel() {
  const [tools, setTools] = useState<MCPTool[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listMCPTools()
      .then(setTools)
      .catch((err) => setError(err.message));
  }, []);

  const grouped = tools.reduce<Record<string, MCPTool[]>>((acc, tool) => {
    (acc[tool.service] ??= []).push(tool);
    return acc;
  }, {});

  return (
    <div className="mcp-panel">
      <h3>MCP Tools</h3>
      {error && <div className="error-box">{error}</div>}

      {Object.entries(grouped).map(([service, svcTools]) => (
        <div key={service} className="mcp-service">
          <h4 className="mcp-service-name">{service}</h4>
          {svcTools.map((tool) => (
            <div key={tool.id} className="mcp-tool">
              <div className="mcp-tool-header">
                <code>{tool.name}</code>
                <span className="mcp-tool-id">{tool.id}</span>
              </div>
              <p className="hint">{tool.description}</p>
              <details className="mcp-schema">
                <summary>Schema</summary>
                <pre>{JSON.stringify(tool.inputSchema, null, 2)}</pre>
              </details>
            </div>
          ))}
        </div>
      ))}

      {tools.length === 0 && !error && (
        <p className="hint">加载中...</p>
      )}
    </div>
  );
}
