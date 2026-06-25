// ── Chat ──
export interface ChatMessage {
  role: "system" | "user" | "assistant";
  content: string;
}

export interface ToolCallResult {
  name: string;
  arguments: Record<string, unknown>;
  result: Record<string, unknown>;
}

export interface ChatResponse {
  message: string;
  model: string;
  tool_calls: ToolCallResult[];
}

// ── Workflow ──
export interface WorkflowCatalogItem {
  id: string;
  name: string;
  description: string;
  parameters: Record<string, unknown>;
}

export interface WorkflowStep {
  id: string;
  name: string;
  type: string;
  tool?: string;
}

export interface WorkflowDefinition {
  id: string;
  name: string;
  description: string;
  steps: WorkflowStep[];
}

export interface WorkflowStepResult {
  id: string;
  name: string;
  status: string;
  output: Record<string, unknown>;
}

export interface WorkflowRunResponse {
  workflow_id: string;
  status: string;
  steps: WorkflowStepResult[];
  report: string;
  error?: Record<string, unknown>;
}

// ── MCP ──
export interface MCPTool {
  id: string;
  service: string;
  name: string;
  description: string;
  inputSchema: Record<string, unknown>;
}

// ── Runs ──
export interface RunRecord {
  run_id: string;
  workflow_id: string;
  conversation_id: string;
  status: string;
  arguments: string;
  result?: string;
  error?: string;
  created_at: string;
  updated_at: string;
}

export interface RunEvent {
  id: number;
  run_id: string;
  sequence: number;
  event_type: string;
  data: string;
  created_at: string;
}

// ── WebSocket ──
export interface WSEvent {
  type: string;
  data: Record<string, unknown>;
}
