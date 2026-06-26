import type {
  ChatMessage,
  ChatResponse,
  MCPTool,
  RunEvent,
  RunRecord,
  WorkflowCatalogItem,
  WorkflowDefinition,
  WorkflowRunResponse,
} from "../types";

export type { MCPTool };

const BASE = "/api";

// ── Chat ──

export async function sendChat(
  message: string,
  history: ChatMessage[] = [],
  useTools = true,
): Promise<ChatResponse> {
  const res = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message, history, use_tools: useTools }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Chat failed");
  }
  return res.json();
}

// ── Workflows ──

export async function listWorkflows(): Promise<WorkflowCatalogItem[]> {
  const res = await fetch(`${BASE}/workflows`);
  if (!res.ok) throw new Error("Failed to list workflows");
  const data = await res.json();
  return data.workflows ?? [];
}

export async function getWorkflowDefinition(
  workflowId: string,
): Promise<WorkflowDefinition> {
  const name = workflowId.replace("workflow:", "");
  const res = await fetch(`${BASE}/workflows/${name}`);
  if (!res.ok) throw new Error("Failed to get workflow definition");
  return res.json();
}

export async function runWorkflow(
  workflowId: string,
  args: Record<string, unknown>,
): Promise<WorkflowRunResponse> {
  const name = workflowId.replace("workflow:", "");
  const res = await fetch(`${BASE}/workflows/${name}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(args),
  });
  if (!res.ok) throw new Error("Failed to run workflow");
  return res.json();
}

// ── MCP Tools ──

export async function listMCPTools(): Promise<MCPTool[]> {
  const res = await fetch(`${BASE}/mcp/tools`);
  if (!res.ok) throw new Error("Failed to list MCP tools");
  const data = await res.json();
  return data.tools ?? [];
}

// ── Runs ──

export async function getRun(runId: string): Promise<RunRecord> {
  const res = await fetch(`${BASE}/runs/${runId}`);
  if (!res.ok) throw new Error("Run not found");
  return res.json();
}

export async function getRunEvents(runId: string): Promise<RunEvent[]> {
  const res = await fetch(`${BASE}/runs/${runId}/events`);
  if (!res.ok) throw new Error("Failed to get run events");
  const data = await res.json();
  return data.events ?? [];
}

// ── WebSocket ──

export function createChatSocket(): WebSocket {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const url = `${proto}//${window.location.host}/api/ws/chat`;
  return new WebSocket(url);
}

// ── Manage Workflows ──

export interface WorkflowDef {
  id: string;
  name: string;
  description: string;
  definition: Record<string, unknown>;
  enabled: boolean;
  created_at: string;
  updated_at: string;
}

export async function listManagedWorkflows(): Promise<WorkflowDef[]> {
  const res = await fetch(`${BASE}/manage/workflows`);
  if (!res.ok) throw new Error("Failed to list workflows");
  return res.json();
}

export async function createManagedWorkflow(
  data: WorkflowDef,
): Promise<{ id: string; status: string }> {
  const res = await fetch(`${BASE}/manage/workflows`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Create failed");
  }
  return res.json();
}

export async function updateManagedWorkflow(
  id: string,
  data: Partial<WorkflowDef>,
): Promise<{ id: string; status: string }> {
  const res = await fetch(`${BASE}/manage/workflows/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Update failed");
  }
  return res.json();
}

export async function deleteManagedWorkflow(
  id: string,
): Promise<{ id: string; status: string }> {
  const res = await fetch(`${BASE}/manage/workflows/${id}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || "Delete failed");
  }
  return res.json();
}

// ── Conversations ──

export interface Conversation {
  id: string;
  title: string;
  created_at: string;
  updated_at: string;
  messages?: ConvMessage[];
}

export interface ConvMessage {
  role: string;
  content: string;
  created_at: string;
}

export async function listConversations(): Promise<Conversation[]> {
  const res = await fetch(`${BASE}/conversations`);
  if (!res.ok) throw new Error("Failed to list conversations");
  return res.json();
}

export async function createConversation(title?: string): Promise<Conversation> {
  const res = await fetch(`${BASE}/conversations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ title: title || "New Chat" }),
  });
  if (!res.ok) throw new Error("Failed to create conversation");
  return res.json();
}

export async function getConversation(id: string): Promise<Conversation> {
  const res = await fetch(`${BASE}/conversations/${id}`);
  if (!res.ok) throw new Error("Conversation not found");
  return res.json();
}

export async function deleteConversation(id: string): Promise<void> {
  const res = await fetch(`${BASE}/conversations/${id}`, { method: "DELETE" });
  if (!res.ok) throw new Error("Failed to delete conversation");
}

export async function addMessage(
  convId: string,
  role: string,
  content: string,
): Promise<void> {
  const res = await fetch(`${BASE}/conversations/${convId}/messages`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role, content }),
  });
  if (!res.ok) throw new Error("Failed to save message");
}
