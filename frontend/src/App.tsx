import { NavLink, Outlet, useLocation } from "react-router-dom";

const TABS = [
  { path: "/chat", label: "Chat" },
  { path: "/workflows", label: "Workflows" },
  { path: "/mcp", label: "MCP Tools" },
  { path: "/runs", label: "Runs" },
  { path: "/manage", label: "Manage" },
];

export default function AppLayout() {
  const location = useLocation();

  // Default redirect: if at "/", treat as "/chat"
  const active =
    location.pathname === "/"
      ? "/chat"
      : TABS.find((t) => location.pathname.startsWith(t.path))?.path || "";

  return (
    <div className="app">
      <header className="app-header">
        <h1 className="app-title">work-agents</h1>
        <span className="app-version">v0.2</span>
      </header>

      <nav className="tab-bar">
        {TABS.map((t) => (
          <NavLink
            key={t.path}
            to={t.path}
            className={`tab ${active === t.path ? "tab-active" : ""}`}
          >
            {t.label}
          </NavLink>
        ))}
      </nav>

      <main className="app-main">
        <Outlet />
      </main>
    </div>
  );
}
