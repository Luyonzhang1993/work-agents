import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import type { ChatMessage, WSEvent } from "../types";
import { createChatSocket, sendChat } from "../api/client";
import {
  listConversations,
  createConversation,
  getConversation,
  deleteConversation,
  addMessage,
  type Conversation,
} from "../api/client";

type Role = "user" | "assistant" | "system";

interface DisplayMessage {
  role: Role;
  content: string;
  steps?: WorkflowStepItem[];
  streaming?: boolean;
}

interface WorkflowStepItem {
  id: string;
  name: string;
  emoji: string;
  status: "running" | "completed" | "failed";
  message?: string;
}

export default function ChatPanel() {
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [useWS, setUseWS] = useState(true);
  const [wsStatus, setWsStatus] = useState<string>("disconnected");
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeConvId, setActiveConvId] = useState<string | null>(null);
  const [searchParams, setSearchParams] = useSearchParams();
  const [showSidebar, setShowSidebar] = useState(true);
  const wsRef = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const convIdRef = useRef<string | null>(null);

  const streamingRef = useRef<{
    active: boolean;
    msgIndex: number;
    steps: WorkflowStepItem[];
    content: string;
  }>({ active: false, msgIndex: -1, steps: [], content: "" });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // Load conversations on mount, auto-select from URL param
  useEffect(() => {
    listConversations()
      .then((convs) => {
        setConversations(convs);
        const convParam = searchParams.get("conv");
        if (convParam && convs.some((c) => c.id === convParam)) {
          selectConversation(convParam);
        }
      })
      .catch(() => {});
  }, []);

  // WebSocket
  useEffect(() => {
    if (!useWS) {
      wsRef.current?.close();
      wsRef.current = null;
      setWsStatus("disconnected");
      return;
    }
    const ws = createChatSocket();
    wsRef.current = ws;
    ws.onopen = () => setWsStatus("connected");
    ws.onclose = () => setWsStatus("disconnected");
    ws.onerror = () => setWsStatus("error");
    ws.onmessage = (event) => handleWSEvent(JSON.parse(event.data));
    return () => { ws.close(); wsRef.current = null; };
  }, [useWS]);

  const handleWSEvent = useCallback((evt: WSEvent) => {
    const s = streamingRef.current;
    const cid = convIdRef.current;

    switch (evt.type) {
      case "ready":
        setWsStatus("ready");
        break;
      case "accepted":
        setWsStatus("processing");
        break;
      case "responding":
        setWsStatus("processing");
        setMessages((prev) => [
          ...prev,
          { role: "system", content: String(evt.data.message || "正在处理...") },
        ]);
        if (cid) addMessage(cid, "system", String(evt.data.message || ""), { type: "responding" }).catch(() => {});
        break;
      case "workflow.routed":
        setMessages((prev) => [
          ...prev,
          { role: "system", content: `📌 ${String(evt.data.workflow_name || evt.data.workflow_id || "")}` },
        ]);
        if (cid) addMessage(cid, "system", `📌 ${String(evt.data.workflow_name || evt.data.workflow_id || "")}`, { type: "workflow.routed", workflow_id: evt.data.workflow_id }).catch(() => {});
        break;
      case "workflow.started":
        setMessages((prev) => {
          const idx = prev.length;
          streamingRef.current = { active: true, msgIndex: idx, steps: [], content: "" };
          return [...prev, { role: "assistant", content: "", steps: [], streaming: true }];
        });
        break;
      case "workflow.step.started": {
        const step: WorkflowStepItem = {
          id: String(evt.data.step_id || ""),
          name: String(evt.data.name || evt.data.step_id || ""),
          emoji: String(evt.data.emoji || "⚙️"),
          status: "running",
          message: String(evt.data.message || ""),
        };
        if (s.active) {
          s.steps = s.steps.filter((st) => st.id !== step.id).concat(step);
          setMessages((prev) => { const copy = [...prev]; const msg = copy[s.msgIndex]; if (msg) copy[s.msgIndex] = { ...msg, steps: [...s.steps] }; return copy; });
        }
        break;
      }
      case "workflow.step.completed":
        if (s.active) {
          s.steps = s.steps.map((st) => st.id === String(evt.data.step_id || "") ? { ...st, status: "completed" as const } : st);
          setMessages((prev) => { const copy = [...prev]; const msg = copy[s.msgIndex]; if (msg) copy[s.msgIndex] = { ...msg, steps: [...s.steps] }; return copy; });
        }
        break;
      case "assistant.message.delta":
        if (s.active) {
          s.content += String(evt.data.content || "");
          setMessages((prev) => { const copy = [...prev]; const msg = copy[s.msgIndex]; if (msg) copy[s.msgIndex] = { ...msg, content: s.content }; return copy; });
        }
        break;
      case "assistant.message.completed": {
        const fullText = String(evt.data.content || "");
        if (s.active) {
          s.content = fullText;
          s.active = false;
          setMessages((prev) => {
            const copy = [...prev];
            const msg = copy[s.msgIndex];
            if (msg) copy[s.msgIndex] = { ...msg, content: fullText, streaming: false };
            return copy;
          });
          // Persist assistant message with steps metadata
          if (cid) addMessage(cid, "assistant", fullText, { type: "workflow_result", steps: s.steps.filter((st) => st.status === "completed") }).catch(() => {});
        }
        break;
      }
      case "workflow.completed":
      case "run.completed":
        setWsStatus("ready");
        setLoading(false);
        if (s.active) { s.active = false; setMessages((prev) => { const copy = [...prev]; const msg = copy[s.msgIndex]; if (msg) copy[s.msgIndex] = { ...msg, streaming: false }; return copy; }); }
        break;
      case "workflow.failed":
        setWsStatus("error");
        setLoading(false);
        s.active = false;
        setMessages((prev) => [...prev, { role: "assistant", content: `❌ ${String(evt.data.error || "未知错误")}` }]);
        break;
      case "completed": {
        // Direct LLM
        setWsStatus("ready");
        setLoading(false);
        s.active = false;
        const data = evt.data as unknown as { message: string; model: string; tool_calls: Array<{ name: string }> };
        const text = data.message + (data.tool_calls?.length ? `\n\n---\n🔧 ${data.tool_calls.map((tc) => tc.name).join(", ")}` : "");
        setMessages((prev) => [...prev, { role: "assistant", content: text }]);
        if (cid) addMessage(cid, "assistant", data.message).catch(() => {});
        break;
      }
      case "error":
        setWsStatus("error");
        setLoading(false);
        s.active = false;
        setMessages((prev) => [...prev, { role: "assistant", content: `❌ ${String(evt.data.message || evt.data.code || "未知错误")}` }]);
        break;
    }
  }, []);

  // ── Conversation management ──

  const startNewChat = useCallback(async () => {
    setSearchParams({});
    setActiveConvId(null);
    convIdRef.current = null;
    setMessages([]);
  }, [setSearchParams]);

  const selectConversation = useCallback(async (convId: string) => {
    setActiveConvId(convId);
    convIdRef.current = convId;
    setSearchParams({ conv: convId });
    try {
      const conv = await getConversation(convId);
      const msgs: DisplayMessage[] = (conv.messages || []).map((m) => {
        const msg: DisplayMessage = { role: m.role as Role, content: m.content };
        // Restore workflow steps from metadata
        const meta = (m as unknown as Record<string, unknown>).metadata;
        if (meta && typeof meta === "string") {
          try {
            const parsed = JSON.parse(meta);
            if (parsed.steps) msg.steps = parsed.steps;
          } catch {}
        } else if (meta && typeof meta === "object") {
          const obj = meta as Record<string, unknown>;
          if (obj.steps) msg.steps = obj.steps as WorkflowStepItem[];
        }
        return msg;
      });
      setMessages(msgs);
    } catch {
      setMessages([]);
    }
  }, [setSearchParams]);

  const handleDeleteConv = useCallback(async (convId: string) => {
    if (!confirm("删除此对话？")) return;
    try {
      await deleteConversation(convId);
      setConversations((prev) => prev.filter((c) => c.id !== convId));
      if (activeConvId === convId) {
        setActiveConvId(null);
        convIdRef.current = null;
        setMessages([]);
      }
    } catch {}
  }, [activeConvId]);

  // Reload conv list after new messages
  const reloadConvs = useCallback(() => {
    listConversations().then(setConversations).catch(() => {});
  }, []);

  // ── Send ──

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;

    // Create conversation if none active
    let cid = convIdRef.current;
    if (!cid) {
      try {
        const conv = await createConversation();
        cid = conv.id;
        convIdRef.current = cid;
        setActiveConvId(cid);
        setConversations((prev) => [conv, ...prev]);
      } catch {
        return;
      }
    }

    const userMsg: DisplayMessage = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    // Persist user message
    addMessage(cid, "user", text).catch(() => {});
    reloadConvs();

    if (useWS && wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        message: text,
        history: messages.map((m) => ({ role: m.role, content: m.content })),
        use_tools: true,
      }));
      return;
    }

    // REST fallback
    try {
      const res = await sendChat(text, messages.map((m) => ({ role: m.role, content: m.content })));
      const toolInfo = res.tool_calls.length ? `\n\n---\n🔧 ${res.tool_calls.map((tc) => tc.name).join(", ")}` : "";
      setMessages((prev) => [...prev, { role: "assistant", content: res.message + toolInfo }]);
      addMessage(cid, "assistant", res.message).catch(() => {});
    } catch (err) {
      setMessages((prev) => [...prev, { role: "assistant", content: `❌ ${err instanceof Error ? err.message : "请求失败"}` }]);
    } finally {
      setLoading(false);
    }
  }, [input, loading, messages, useWS, reloadConvs]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); handleSend(); }
  };

  return (
    <div className="chat-panel">
      {/* Conversation sidebar */}
      <div className={`chat-sidebar ${showSidebar ? "" : "chat-sidebar-hidden"}`}>
        <div className="chat-sidebar-header">
          <button className="btn-primary btn-sm" onClick={startNewChat}>+ 新对话</button>
          <button className="btn-sm" onClick={() => setShowSidebar(false)}>✕</button>
        </div>
        <div className="chat-sidebar-list">
          {conversations.map((c) => (
            <div
              key={c.id}
              className={`chat-conv-item ${c.id === activeConvId ? "chat-conv-active" : ""}`}
              onClick={() => selectConversation(c.id)}
            >
              <span className="chat-conv-title">{c.title}</span>
              <button
                className="btn-sm btn-danger chat-conv-del"
                onClick={(e) => { e.stopPropagation(); handleDeleteConv(c.id); }}
              >
                ✕
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* Toggle sidebar button when hidden */}
      {!showSidebar && (
        <button className="chat-sidebar-toggle" onClick={() => setShowSidebar(true)}>
          ☰
        </button>
      )}

      {/* Main chat area */}
      <div className="chat-main">
        <div className="chat-toolbar">
          <label className="toggle-label">
            <input type="checkbox" checked={useWS} onChange={(e) => setUseWS(e.target.checked)} />
            WebSocket <span className={`ws-badge ws-${wsStatus}`}>{wsStatus}</span>
          </label>
        </div>

        <div className="chat-messages">
          {messages.length === 0 && (
            <div className="chat-empty">
              <p>👋 开始新对话或选择历史对话</p>
              <p className="hint">试试 "帮我规划杭州 3 天旅行" 或 "生成 AMD 金融报告"</p>
            </div>
          )}
          {messages.map((msg, i) => (
            <div key={i} className={`message message-${msg.role}`}>
              <div className="message-role">{msg.role === "user" ? "🧑" : msg.role === "system" ? "📡" : "🤖"}</div>
              <div className="message-content">
                {msg.steps && msg.steps.length > 0 && (
                  <div className="workflow-steps-inline">
                    {msg.steps.map((step) => (
                      <div key={step.id} className={`step-inline step-${step.status}`}>
                        <span className="step-emoji">{step.emoji}</span>
                        <span className="step-name">{step.name}</span>
                        {step.message && <span className="step-hint">{step.message}</span>}
                        <span className={`step-badge badge-${step.status}`}>
                          {step.status === "running" ? "⏳" : step.status === "completed" ? "✓" : "✗"}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
                {msg.content && msg.content.split("\n").map((line, j) => (
                  <p key={j}>{line || "\u00A0"}{msg.streaming && j === msg.content.split("\n").length - 1 && <span className="cursor-blink">▌</span>}</p>
                ))}
                {msg.streaming && !msg.content && (
                  <span className="typing-indicator"><span /><span /><span /></span>
                )}
              </div>
            </div>
          ))}
          {loading && !streamingRef.current.active && (
            <div className="message message-assistant">
              <div className="message-role">🤖</div>
              <div className="message-content"><span className="typing-indicator"><span /><span /><span /></span></div>
            </div>
          )}
          <div ref={bottomRef} />
        </div>

        <div className="chat-input-area">
          <textarea className="chat-input" value={input} onChange={(e) => setInput(e.target.value)} onKeyDown={handleKeyDown}
            placeholder="输入消息... (Enter 发送)" rows={3} disabled={loading}
          />
          <button className="btn-send" onClick={handleSend} disabled={loading || !input.trim()}>
            {loading ? "..." : "发送"}
          </button>
        </div>
      </div>
    </div>
  );
}
