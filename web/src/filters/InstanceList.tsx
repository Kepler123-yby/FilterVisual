import type { ExperimentConfig, FilterConfig } from "../api/types";
import { COLORS, Field, NumberField, Toggle } from "../app/components";
import { cloneFilter } from "../experiments/validation";
import ParameterEditor from "./ParameterEditor";

export default function InstanceList({
  config,
  onChange,
}: {
  config: ExperimentConfig;
  onChange: (config: ExperimentConfig) => void;
}) {
  const update = (i: number, f: FilterConfig) =>
    onChange({
      ...config,
      filters: config.filters.map((v, j) => (i === j ? f : v)),
    });
  function add(kind: FilterConfig["kind"]) {
    const base =
      config.filters.find((f) => f.kind === kind) ?? config.filters[0];
    if (!base) return;
    const copied = cloneFilter(base);
    onChange({
      ...config,
      filters: [
        ...config.filters,
        {
          ...copied,
          kind,
          name: `${kind.toUpperCase()} ${config.filters.length + 1}`,
        },
      ],
    });
  }
  return (
    <>
      <div className="instance-add">
        <span>添加比较实例</span>
        {(["ekf", "ukf", "imm"] as const).map((kind) => (
          <button key={kind} onClick={() => add(kind)}>
            ＋ {kind.toUpperCase()}
          </button>
        ))}
      </div>
      {config.filters.map((f, i) => (
        <details className="instance" key={f.id} open={i === 0}>
          <summary>
            <i style={{ background: COLORS[i % COLORS.length] }} />
            <strong>{f.name}</strong>
            <small>
              {f.kind.toUpperCase()} / {f.frequency_hz} Hz
            </small>
          </summary>
          <div className="instance-body">
            <Toggle
              label="参与此实验"
              checked={f.enabled ?? true}
              onChange={(enabled) => update(i, { ...f, enabled })}
            />
            <Field label="实例名称">
              <input
                value={f.name}
                onChange={(e) => update(i, { ...f, name: e.target.value })}
              />
            </Field>
            <div className="field-grid">
              <Field label="算法">
                <select
                  value={f.kind}
                  onChange={(e) =>
                    update(i, {
                      ...f,
                      kind: e.target.value as FilterConfig["kind"],
                    })
                  }
                >
                  <option value="ekf">EKF</option>
                  <option value="ukf">UKF</option>
                  <option value="imm">IMM</option>
                </select>
              </Field>
              <NumberField
                label={`${f.name} 更新频率（Hz）`}
                value={f.frequency_hz}
                min={0.1}
                onChange={(frequency_hz) => update(i, { ...f, frequency_hz })}
              />
            </div>
            <div className="instance-actions">
              <button
                className="text-button"
                onClick={() =>
                  onChange({
                    ...config,
                    filters: [...config.filters, cloneFilter(f)],
                  })
                }
              >
                复制实例
              </button>
              <button
                className="text-button danger"
                disabled={config.filters.length === 1}
                onClick={() =>
                  onChange({
                    ...config,
                    filters: config.filters.filter((_, j) => i !== j),
                  })
                }
              >
                删除
              </button>
            </div>
            <ParameterEditor
              filter={f}
              geometry={config.geometry}
              onChange={(next) => update(i, next)}
            />
          </div>
        </details>
      ))}
    </>
  );
}
