import { useCallback, useEffect, useRef, useState } from "react";
import type { ChatMessage, WSEvent } from "../types";
import { createChatSocket, sendChat } from "../api/client";

// ── Message types for the chat display ──
type Role = "user" | "assistant" | "system";

interface DisplayMessage {
  role: Role;
  content: string;
  /** Sub-items for workflow steps, shown inline */
  steps?: WorkflowStepItem[];
  /** True while streaming content is being accumulated */
  streaming?: boolean;
}

interface WorkflowStepItem {
  id: string;
  name: string;
  emoji: string;
  status: "running" | "completed" | "failed";
  message?: string;
}

// Emoji fallback
const DEFAULT_EMOJI = "⚙️";

export default function ChatPanel() {
  const [messages, setMessages] = useState<DisplayMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [useWS, setUseWS] = useState(true);
  const [wsStatus, setWsStatus] = useState<string>("disconnected");
  const wsRef = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  // Track streaming state across event callbacks
  const streamingRef = useRef<{
    active: boolean;
    msgIndex: number;
    steps: WorkflowStepItem[];
    content: string;
  }>({ active: false, msgIndex: -1, steps: [], content: "" });

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  // WebSocket connection
  useEffect(() => {
    if (!useWS) {
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
      setWsStatus("disconnected");
      return;
    }

    const ws = createChatSocket();
    wsRef.current = ws;

    ws.onopen = () => setWsStatus("connected");
    ws.onclose = () => setWsStatus("disconnected");
    ws.onerror = () => setWsStatus("error");

    ws.onmessage = (event) => {
      const evt: WSEvent = JSON.parse(event.data);
      handleWSEvent(evt);
    };

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [useWS]);

  const handleWSEvent = useCallback((evt: WSEvent) => {
    const s = streamingRef.current;

    switch (evt.type) {
      case "ready":
        setWsStatus("ready");
        break;

      case "accepted":
        setWsStatus("processing");
        break;

      case "responding":
        setWsStatus("processing");
        // Add a system message about routing
        setMessages((prev) => [
          ...prev,
          {
            role: "system",
            content: String(evt.data.message || "正在处理..."),
          },
        ]);
        break;

      case "workflow.routed": {
        const wfName = String(evt.data.workflow_name || evt.data.workflow_id || "");
        setMessages((prev) => [
          ...prev,
          {
            role: "system",
            content: `📌 已匹配 workflow: ${wfName}`,
          },
        ]);
        break;
      }

      case "workflow.started": {
        // Start a new streaming assistant message with steps
        // Use functional updater to get the real index (not stale closure)
        setMessages((prev) => {
          const idx = prev.length;
          streamingRef.current = { active: true, msgIndex: idx, steps: [], content: "" };
          return [
            ...prev,
            {
              role: "assistant",
              content: "",
              steps: [],
              streaming: true,
            },
          ];
        });
        break;
      }

      case "workflow.step.started": {
        const step: WorkflowStepItem = {
          id: String(evt.data.step_id || ""),
          name: String(evt.data.name || evt.data.step_id || ""),
          emoji: String(evt.data.emoji || DEFAULT_EMOJI),
          status: "running",
          message: String(evt.data.message || ""),
        };
        if (s.active) {
          const updated = s.steps.filter((st) => st.id !== step.id);
          updated.push(step);
          s.steps = updated;
          setMessages((prev) => {
            const copy = [...prev];
            const msg = copy[s.msgIndex];
            if (msg) {
              copy[s.msgIndex] = { ...msg, steps: [...updated] };
            }
            return copy;
          });
        }
        break;
      }

      case "workflow.step.completed": {
        if (!s.active) break;
        const stepId = String(evt.data.step_id || "");
        const updated = s.steps.map((st) =>
          st.id === stepId ? { ...st, status: "completed" as const } : st,
        );
        s.steps = updated;
        setMessages((prev) => {
          const copy = [...prev];
          const msg = copy[s.msgIndex];
          if (msg) {
            copy[s.msgIndex] = { ...msg, steps: [...updated] };
          }
          return copy;
        });
        break;
      }

      case "assistant.message.delta": {
        const token = String(evt.data.content || "");
        if (s.active) {
          s.content += token;
          setMessages((prev) => {
            const copy = [...prev];
            const msg = copy[s.msgIndex];
            if (msg) {
              copy[s.msgIndex] = { ...msg, content: s.content };
            }
            return copy;
          });
        }
        break;
      }

      case "assistant.message.completed": {
        const fullText = String(evt.data.content || "");
        if (s.active) {
          s.content = fullText;
          s.active = false;
          setMessages((prev) => {
            const copy = [...prev];
            const msg = copy[s.msgIndex];
            if (msg) {
              copy[s.msgIndex] = {
                ...msg,
                content: fullText,
                streaming: false,
              };
            }
            return copy;
          });
        }
        break;
      }

      case "workflow.completed":
      case "run.completed":
        setWsStatus("ready");
        setLoading(false);
        // Finalize any active streaming
        if (s.active) {
          s.active = false;
          setMessages((prev) => {
            const copy = [...prev];
            const msg = copy[s.msgIndex];
            if (msg) {
              copy[s.msgIndex] = { ...msg, streaming: false };
            }
            return copy;
          });
        }
        break;

      case "workflow.failed": {
        setWsStatus("error");
        setLoading(false);
        s.active = false;
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: `❌ Workflow 执行失败: ${String(
              evt.data.error || "未知错误",
            )}`,
          },
        ]);
        break;
      }

      case "completed": {
        // Direct LLM response (no workflow)
        setWsStatus("ready");
        setLoading(false);
        s.active = false;
        const data = evt.data as unknown as {
          message: string;
          model: string;
          tool_calls: Array<{ name: string }>;
        };
        const toolInfo =
          data.tool_calls && data.tool_calls.length > 0
            ? `\n\n---\n🔧 工具调用: ${data.tool_calls
                .map((tc) => tc.name)
                .join(", ")}`
            : "";
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: data.message + toolInfo,
          },
        ]);
        break;
      }

      case "error": {
        setWsStatus("error");
        setLoading(false);
        s.active = false;
        setMessages((prev) => [
          ...prev,
          {
            role: "assistant",
            content: `❌ 错误: ${String(
              evt.data.message || evt.data.code || "未知错误",
            )}`,
          },
        ]);
        break;
      }
    }
  }, []);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || loading) return;

    const userMsg: DisplayMessage = { role: "user", content: text };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    if (useWS && wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(
        JSON.stringify({
          message: text,
          history: messages.map((m) => ({
            role: m.role,
            content: m.content,
          })),
          use_tools: true,
        }),
      );
      return;
    }

    // REST fallback
    try {
      const res = await sendChat(
        text,
        messages.map((m) => ({ role: m.role, content: m.content })),
        true,
      );
      const toolInfo =
        res.tool_calls.length > 0
          ? `\n\n---\n🔧 工具调用: ${res.tool_calls
              .map((tc) => tc.name)
              .join(", ")}`
          : "";
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: res.message + toolInfo },
      ]);
    } catch (err) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: `❌ 错误: ${err instanceof Error ? err.message : "请求失败"}`,
        },
      ]);
    } finally {
      setLoading(false);
    }
  }, [input, loading, messages, useWS]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="chat-panel">
      <div className="chat-toolbar">
        <label className="toggle-label">
          <input
            type="checkbox"
            checked={useWS}
            onChange={(e) => setUseWS(e.target.checked)}
          />
          WebSocket{" "}
          <span className={`ws-badge ws-${wsStatus}`}>{wsStatus}</span>
        </label>
      </div>

      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <p>👋 发送消息开始对话</p>
            <p className="hint">
              试试 "帮我规划杭州 3 天旅行" 或 "生成 AMD 金融报告"
            </p>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={i} className={`message message-${msg.role}`}>
            <div className="message-role">
              {msg.role === "user" ? "🧑" : msg.role === "system" ? "📡" : "🤖"}
            </div>
            <div className="message-content">
              {/* Workflow steps */}
              {msg.steps && msg.steps.length > 0 && (
                <div className="workflow-steps-inline">
                  {msg.steps.map((step) => (
                    <div
                      key={step.id}
                      className={`step-inline step-${step.status}`}
                    >
                      <span className="step-emoji">{step.emoji}</span>
                      <span className="step-name">{step.name}</span>
                      {step.message && (
                        <span className="step-hint">{step.message}</span>
                      )}
                      <span className={`step-badge badge-${step.status}`}>
                        {step.status === "running"
                          ? "⏳"
                          : step.status === "completed"
                            ? "✓"
                            : "✗"}
                      </span>
                    </div>
                  ))}
                </div>
              )}

              {/* Text content */}
              {msg.content &&
                msg.content.split("\n").map((line, j) => (
                  <p key={j}>
                    {line || "\u00A0"}
                    {msg.streaming && j === msg.content.split("\n").length - 1 && (
                      <span className="cursor-blink">▌</span>
                    )}
                  </p>
                ))}

              {/* Streaming indicator when no content yet */}
              {msg.streaming && !msg.content && (
                <span className="typing-indicator">
                  <span />
                  <span />
                  <span />
                </span>
              )}
            </div>
          </div>
        ))}

        {loading && !streamingRef.current.active && (
          <div className="message message-assistant">
            <div className="message-role">🤖</div>
            <div className="message-content">
              <span className="typing-indicator">
                <span />
                <span />
                <span />
              </span>
            </div>
          </div>
        )}

        <div ref={bottomRef} />
      </div>

      <div className="chat-input-area">
        <textarea
          className="chat-input"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="输入消息... (Enter 发送, Shift+Enter 换行)"
          rows={3}
          disabled={loading}
        />
        <button
          className="btn-send"
          onClick={handleSend}
          disabled={loading || !input.trim()}
        >
          {loading ? "..." : "发送"}
        </button>
      </div>
    </div>
  );
}
