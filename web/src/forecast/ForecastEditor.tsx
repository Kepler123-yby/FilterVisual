import type { ForecastConfig } from "../api/types";
import { NumberField, Toggle } from "../app/components";
export function resizeLeads(leads: number[], count: number) {
  const n = Math.min(16, Math.max(1, Math.round(count)));
  return Array.from(
    { length: n },
    (_, i) =>
      leads[i] ??
      Number(((leads.at(-1) ?? 0) + 0.1 * (i - leads.length + 1)).toFixed(3)),
  );
}
export default function ForecastEditor({
  value,
  onChange,
}: {
  value: ForecastConfig;
  onChange: (value: ForecastConfig) => void;
}) {
  return (
    <div className="forecast-editor">
      <Toggle
        label="每次观测更新后附带纯预测"
        checked={value.enabled}
        onChange={(enabled) => onChange({ ...value, enabled })}
      />
      {value.enabled && (
        <>
          <p className="help">
            每项从同一后验快照出发，预测未来 τ 秒后的状态，主滤波继续正常运行。
          </p>
          <div className="inline-fields">
            <NumberField
              label="附带预测次数 N"
              value={value.leads_s.length}
              min={1}
              max={16}
              step={1}
              onChange={(n) =>
                onChange({ ...value, leads_s: resizeLeads(value.leads_s, n) })
              }
            />
            <button
              onClick={() =>
                onChange({
                  ...value,
                  leads_s: Array.from(
                    { length: value.leads_s.length },
                    (_, i) =>
                      Number(((i + 1) * (value.leads_s[0] || 0.1)).toFixed(3)),
                  ),
                })
              }
            >
              等间隔生成
            </button>
          </div>
          <div className="lead-list">
            {value.leads_s.map((lead, i) => (
              <NumberField
                key={i}
                label={`提前量 ${i + 1}（秒）`}
                value={lead}
                min={0.001}
                step={0.01}
                onChange={(n) =>
                  onChange({
                    ...value,
                    leads_s: value.leads_s.map((v, j) => (i === j ? n : v)),
                  })
                }
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
