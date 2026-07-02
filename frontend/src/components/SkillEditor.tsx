import { useMemo, useState } from "react";

interface ParamDef {
  key: string;
  type: string;
  description: string;
  required: boolean;
  default: string;
}

interface SkillDefinition {
  parameters?: {
    type: "object";
    properties: Record<string, { type: string; description: string; default?: unknown }>;
    required?: string[];
    additionalProperties?: false;
  };
  skill?: string;
  skill_path?: string;
  input_template?: string;
  temperature?: number;
}

interface Props {
  value: Record<string, unknown>;
  onChange: (def: Record<string, unknown>) => void;
}

const PARAM_TYPES = ["string", "integer", "number", "boolean", "array", "object"];

function asSkillDefinition(value: Record<string, unknown>): SkillDefinition {
  return value as SkillDefinition;
}

export default function SkillEditor({ value, onChange }: Props) {
  const [showJson, setShowJson] = useState(false);
  const def = asSkillDefinition(value);

  const params = useMemo<ParamDef[]>(() => {
    const properties = def.parameters?.properties || {};
    const required = def.parameters?.required || [];
    return Object.entries(properties).map(([key, prop]) => ({
      key,
      type: prop.type || "string",
      description: prop.description || "",
      required: required.includes(key),
      default: String(prop.default ?? ""),
    }));
  }, [def.parameters]);

  const notify = (next: SkillDefinition) => onChange(next as Record<string, unknown>);

  const updateParams = (newParams: ParamDef[]) => {
    const properties: Record<string, { type: string; description: string; default?: unknown }> = {};
    const required: string[] = [];
    for (const param of newParams) {
      if (!param.key.trim()) continue;
      const prop: { type: string; description: string; default?: unknown } = {
        type: param.type,
        description: param.description,
      };
      if (param.default !== "") prop.default = param.default;
      properties[param.key.trim()] = prop;
      if (param.required) required.push(param.key.trim());
    }
    notify({
      ...def,
      parameters: {
        type: "object",
        properties,
        required,
        additionalProperties: false,
      },
    });
  };

  const updateParam = (index: number, field: keyof ParamDef, val: string | boolean) => {
    const next = [...params];
    next[index] = { ...next[index], [field]: val };
    updateParams(next);
  };

  const addParam = () => {
    updateParams([
      ...params,
      { key: "", type: "string", description: "", required: false, default: "" },
    ]);
  };

  const removeParam = (index: number) => {
    updateParams(params.filter((_, i) => i !== index));
  };

  return (
    <div className="skill-editor">
      <section className="cap-section">
        <div className="cap-section-header">
          <h4>输入参数</h4>
          <button className="btn-sm" type="button" onClick={addParam}>
            + 添加
          </button>
        </div>
        {params.length === 0 && <p className="hint">暂无参数</p>}
        {params.map((param, index) => (
          <div key={index} className="cap-param-row">
            <input
              className="ve-input-sm"
              placeholder="参数名"
              value={param.key}
              onChange={(event) => updateParam(index, "key", event.target.value)}
            />
            <select
              className="ve-select-sm"
              value={param.type}
              onChange={(event) => updateParam(index, "type", event.target.value)}
            >
              {PARAM_TYPES.map((type) => (
                <option key={type} value={type}>
                  {type}
                </option>
              ))}
            </select>
            <input
              className="ve-input"
              placeholder="描述"
              value={param.description}
              onChange={(event) => updateParam(index, "description", event.target.value)}
            />
            <input
              className="ve-input-xs"
              placeholder="默认值"
              value={param.default}
              onChange={(event) => updateParam(index, "default", event.target.value)}
            />
            <label className="ve-check">
              <input
                type="checkbox"
                checked={param.required}
                onChange={(event) => updateParam(index, "required", event.target.checked)}
              />
              必填
            </label>
            <button className="btn-sm btn-danger" type="button" onClick={() => removeParam(index)}>
              删除
            </button>
          </div>
        ))}
      </section>

      <section className="cap-section">
        <div className="cap-section-header">
          <h4>Skill.md</h4>
          <button className="btn-sm" type="button" onClick={() => setShowJson(!showJson)}>
            {showJson ? "隐藏 JSON" : "JSON"}
          </button>
        </div>
        <textarea
          className="skill-markdown"
          rows={18}
          value={def.skill || ""}
          onChange={(event) => notify({ ...def, skill: event.target.value })}
          placeholder="# Skill&#10;&#10;## When to use&#10;...&#10;&#10;## Process&#10;...&#10;&#10;## Output&#10;..."
        />
      </section>

      <section className="cap-section cap-grid">
        <div className="form-field">
          <label>SKILL.md 路径</label>
          <input
            type="text"
            value={def.skill_path || ""}
            onChange={(event) => notify({ ...def, skill_path: event.target.value })}
            placeholder="skills/report/SKILL.md"
          />
        </div>
        <div className="form-field">
          <label>Temperature</label>
          <input
            type="number"
            min={0}
            max={2}
            step={0.1}
            value={String(def.temperature ?? 0.2)}
            onChange={(event) => notify({ ...def, temperature: Number(event.target.value) })}
          />
        </div>
      </section>

      <section className="cap-section">
        <div className="cap-section-header">
          <h4>输入模板</h4>
        </div>
        <textarea
          className="ve-textarea"
          rows={4}
          value={def.input_template || ""}
          onChange={(event) => notify({ ...def, input_template: event.target.value })}
          placeholder="请处理：{message}"
        />
      </section>

      {showJson && (
        <pre className="ve-preview">{JSON.stringify(def, null, 2)}</pre>
      )}
    </div>
  );
}
