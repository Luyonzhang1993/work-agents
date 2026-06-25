import { useState } from "react";
import ChatPanel from "./components/ChatPanel";
import WorkflowPanel from "./components/WorkflowPanel";
import WorkflowManager from "./components/WorkflowManager";
import MCPPanel from "./components/MCPPanel";
import RunPanel from "./components/RunPanel";

type Tab = "chat" | "workflows" | "mcp" | "runs" | "manage";

const TABS: { id: Tab; label: string }[] = [
  { id: "chat", label: "Chat" },
  { id: "workflows", label: "Workflows" },
  { id: "mcp", label: "MCP Tools" },
  { id: "runs", label: "Runs" },
  { id: "manage", label: "Manage" },
];

export default function App() {
  const [tab, setTab] = useState<Tab>("chat");

  return (
    <div className="app">
      <header className="app-header">
        <h1 className="app-title">work-agents</h1>
        <span className="app-version">v0.1</span>
      </header>

      <nav className="tab-bar">
        {TABS.map((t) => (
          <button
            key={t.id}
            className={`tab ${tab === t.id ? "tab-active" : ""}`}
            onClick={() => setTab(t.id)}
          >
            {t.label}
          </button>
        ))}
      </nav>

      <main className="app-main">
        {tab === "chat" && <ChatPanel />}
        {tab === "workflows" && <WorkflowPanel />}
        {tab === "mcp" && <MCPPanel />}
        {tab === "runs" && <RunPanel />}
        {tab === "manage" && <WorkflowManager />}
      </main>
    </div>
  );
}
