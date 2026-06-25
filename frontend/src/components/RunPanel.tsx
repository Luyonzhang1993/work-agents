import { useCallback, useState } from "react";
import type { RunEvent, RunRecord } from "../types";
import { getRun, getRunEvents } from "../api/client";

export default function RunPanel() {
  const [runId, setRunId] = useState("");
  const [run, setRun] = useState<RunRecord | null>(null);
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleLookup = useCallback(async () => {
    const id = runId.trim();
    if (!id) return;

    setLoading(true);
    setError(null);
    setRun(null);
    setEvents([]);

    try {
      const [runData, eventData] = await Promise.all([
        getRun(id),
        getRunEvents(id),
      ]);
      setRun(runData);
      setEvents(eventData);
    } catch (err) {
      setError(err instanceof Error ? err.message : "查询失败");
    } finally {
      setLoading(false);
    }
  }, [runId]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") handleLookup();
  };

  return (
    <div className="run-panel">
      <h3>Run 检查</h3>
      <p className="hint">输入 run_id 查看执行记录和事件流</p>

      <div className="run-search">
        <input
          type="text"
          value={runId}
          onChange={(e) => setRunId(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="run_id (e.g. r_abc123)"
        />
        <button
          className="btn-primary"
          onClick={handleLookup}
          disabled={loading || !runId.trim()}
        >
          {loading ? "查询中..." : "查询"}
        </button>
      </div>

      {error && <div className="error-box">{error}</div>}

      {run && (
        <div className="run-detail">
          <h4>Run Record</h4>
          <table className="run-table">
            <tbody>
              {Object.entries(run).map(([key, value]) => (
                <tr key={key}>
                  <td className="run-key">{key}</td>
                  <td className="run-value">
                    {typeof value === "string" && value.length > 200 ? (
                      <details>
                        <summary>
                          {value.substring(0, 200)}...
                        </summary>
                        <pre>{value}</pre>
                      </details>
                    ) : (
                      String(value ?? "-")
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {events.length > 0 && (
        <div className="run-events">
          <h4>Events ({events.length})</h4>
          <div className="events-list">
            {events.map((evt) => (
              <div key={evt.id} className="event-item">
                <span className="event-seq">#{evt.sequence}</span>
                <span className="event-type">{evt.event_type}</span>
                <span className="event-time">
                  {new Date(evt.created_at).toLocaleTimeString()}
                </span>
                <details className="event-data">
                  <summary>data</summary>
                  <pre>
                    {(() => {
                      try {
                        return JSON.stringify(
                          JSON.parse(evt.data),
                          null,
                          2,
                        );
                      } catch {
                        return evt.data;
                      }
                    })()}
                  </pre>
                </details>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
