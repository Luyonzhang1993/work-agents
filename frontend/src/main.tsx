import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import AppLayout from "./App";
import ChatPanel from "./components/ChatPanel";
import WorkflowPanel from "./components/WorkflowPanel";
import MCPPage from "./components/MCPPage";
import RunPanel from "./components/RunPanel";
import WorkflowManager from "./components/WorkflowManager";
import "./index.css";

const router = createBrowserRouter([
  {
    path: "/",
    element: <AppLayout />,
    children: [
      { index: true, element: <Navigate to="/chat" replace /> },
      { path: "chat", element: <ChatPanel /> },
      { path: "workflows", element: <WorkflowPanel /> },
      { path: "mcp", element: <MCPPage /> },
      { path: "runs", element: <RunPanel /> },
      { path: "manage", element: <WorkflowManager /> },
      { path: "manage/:id", element: <WorkflowManager /> },
    ],
  },
]);

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <RouterProvider router={router} />
  </StrictMode>,
);
