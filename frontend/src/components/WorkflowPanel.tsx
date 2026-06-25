import { useCallback, useEffect, useState } from "react";
import type { WorkflowCatalogItem, WorkflowRunResponse } from "../types";
import { listWorkflows, runWorkflow } from "../api/client";

interface FormField {
  key: string;
  type: string;
  label: string;
  defaultValue: string;
  enum?: string[];
}

function extractFormFields(item: WorkflowCatalogItem): FormField[] {
  const props = (item.parameters as Record<string, unknown>)?.properties as
    | Record<string, { type: string; description?: string; default?: unknown; enum?: string[] }>
    | undefined;
  if (!props) return [];

  return Object.entries(props).map(([key, schema]) => ({
    key,
    type: schema.type || "string",
    label: schema.description || key,
    defaultValue:
      schema.default !== undefined ? String(schema.default) : "",
    enum: schema.enum,
  }));
}

export default function WorkflowPanel() {
  const [workflows, setWorkflows] = useState<WorkflowCatalogItem[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [formValues, setFormValues] = useState<Record<string, string>>({});
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<WorkflowRunResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    listWorkflows()
      .then(setWorkflows)
      .catch(() => setError("加载工作流列表失败"));
  }, []);

  const selectedWorkflow = workflows.find((w) => w.id === selected);
  const fields = selectedWorkflow ? extractFormFields(selectedWorkflow) : [];

  const handleSelect = useCallback((id: string) => {
    setSelected(id);
    setResult(null);
    setError(null);
    setFormValues({});
  }, []);

  const handleRun = useCallback(async () => {
    if (!selectedWorkflow) return;
    setRunning(true);
    setResult(null);
    setError(null);

    // Build arguments from form values
    const args: Record<string, unknown> = {};
    for (const field of fields) {
      const val = formValues[field.key];
      if (val !== undefined && val !== "") {
        if (field.type === "integer") {
          args[field.key] = parseInt(val, 10) || 0;
        } else if (field.type === "array") {
          args[field.key] = val
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean);
        } else {
          args[field.key] = val;
        }
      }
    }

    try {
      const res = await runWorkflow(selectedWorkflow.id, args);
      setResult(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "执行失败");
    } finally {
      setRunning(false);
    }
  }, [selectedWorkflow, formValues, fields]);

  return (
    <div className="workflow-panel">
      <div className="panel-sidebar">
        <h3>工作流</h3>
        {workflows.length === 0 && <p className="hint">加载中...</p>}
        {workflows.map((w) => (
          <button
            key={w.id}
            className={`wf-item ${selected === w.id ? "wf-item-active" : ""}`}
            onClick={() => handleSelect(w.id)}
          >
            <div className="wf-item-name">{w.name}</div>
            <div className="wf-item-desc">{w.description}</div>
          </button>
        ))}
      </div>

      <div className="panel-content">
        {!selectedWorkflow && (
          <div className="panel-empty">← 选择一个工作流</div>
        )}

        {selectedWorkflow && (
          <>
            <h3>{selectedWorkflow.name}</h3>
            <p className="hint">{selectedWorkflow.description}</p>

            {fields.length > 0 && (
              <div className="wf-form">
                {fields.map((field) => (
                  <div key={field.key} className="form-field">
                    <label>{field.label}</label>
                    {field.enum ? (
                      <select
                        value={formValues[field.key] || field.defaultValue}
                        onChange={(e) =>
                          setFormValues((prev) => ({
                            ...prev,
                            [field.key]: e.target.value,
                          }))
                        }
                      >
                        {field.enum.map((v) => (
                          <option key={v} value={v}>
                            {v}
                          </option>
                        ))}
                      </select>
                    ) : field.type === "array" ? (
                      <input
                        type="text"
                        placeholder="逗号分隔, e.g. local_food,culture"
                        value={formValues[field.key] ?? field.defaultValue}
                        onChange={(e) =>
                          setFormValues((prev) => ({
                            ...prev,
                            [field.key]: e.target.value,
                          }))
                        }
                      />
                    ) : (
                      <input
                        type={field.type === "integer" ? "number" : "text"}
                        value={formValues[field.key] ?? field.defaultValue}
                        onChange={(e) =>
                          setFormValues((prev) => ({
                            ...prev,
                            [field.key]: e.target.value,
                          }))
                        }
                      />
                    )}
                  </div>
                ))}

                <button
                  className="btn-primary"
                  onClick={handleRun}
                  disabled={running}
                >
                  {running ? "执行中..." : "▶ 执行"}
                </button>
              </div>
            )}

            {error && <div className="error-box">{error}</div>}

            {result && (
              <div className="result-box">
                <div className="result-header">
                  状态:{" "}
                  <span className={`badge badge-${result.status}`}>
                    {result.status}
                  </span>
                </div>

                {result.steps.length > 0 && (
                  <div className="steps-list">
                    <h4>执行步骤</h4>
                    {result.steps.map((step) => (
                      <div
                        key={step.id}
                        className={`step-item step-${step.status}`}
                      >
                        <span className="step-name">{step.name}</span>
                        <span className="step-status">{step.status}</span>
                      </div>
                    ))}
                  </div>
                )}

                {result.report && (
                  <div className="report">
                    <h4>报告</h4>
                    <pre>{result.report}</pre>
                  </div>
                )}

                {result.error && (
                  <div className="error-box">
                    {JSON.stringify(result.error, null, 2)}
                  </div>
                )}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
