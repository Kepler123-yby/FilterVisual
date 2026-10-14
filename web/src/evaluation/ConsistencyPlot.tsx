import { useMemo, useState } from "react";
import type { Data } from "plotly.js";
import type { RunPayload, Score } from "../api/types";
import {
  COLORS,
  EmptyPlot,
  Field,
  NumberField,
  formatNumber,
} from "../app/components";
import { Plot } from "../plots/Plot";
export function scoreLabel(score: Score) {
  return score.value == null
    ? (score.reason ?? "无可用指标")
    : `${formatNumber(score.value)} / dof ${score.dof}`;
}
export default function ConsistencyPlot({
  result,
  enabled,
  onTimeChange,
  confidence,
  onConfidenceChange,
}: {
  result: RunPayload | null;
  enabled: string[];
  onTimeChange: (t: number) => void;
  confidence: number;
  onConfidenceChange: (n: number) => void;
}) {
  const [kind, setKind] = useState<"nis" | "nees" | "forecast">("nis"),
    [lead, setLead] = useState(0.3);
  const instances =
    result?.instances.filter((i) => enabled.includes(i.id)) ?? [];
  const leads = [
    ...new Set(instances.flatMap((i) => i.forecasts.map((f) => f.lead_s))),
  ].sort((a, b) => a - b);
  const selectedLead = leads.includes(lead) ? lead : (leads[0] ?? 0.3);
  const data = useMemo(() => {
    const traces: Data[] = [];
    if (!result) return traces;
    instances.forEach((i) => {
      const points =
          kind === "nis"
            ? i.updates.map((u) => ({ t: u.t, score: u.nis }))
            : kind === "nees"
              ? i.samples.map((s) => ({ t: s.t, score: s.nees }))
              : i.forecasts
                  .filter((f) => Math.abs(f.lead_s - selectedLead) < 1e-8)
                  .map((f) => ({ t: f.origin_time, score: f.nees })),
        color =
          COLORS[
            result.instances.findIndex((v) => v.id === i.id) % COLORS.length
          ];
      traces.push({
        x: points.map((p) => p.t),
        y: points.map((p) => p.score.value),
        type: "scatter",
        mode: "lines",
        name: i.name,
        line: { color, width: 1.3 },
        customdata: points.map((p) => p.score.dof),
        hovertemplate:
          "t=%{x:.3f}s<br>值 %{y:.4f}<br>自由度 %{customdata}<extra>%{fullData.name}</extra>",
      });
      ["lower", "upper"].forEach((bound, j) =>
        traces.push({
          x: points.map((p) => p.t),
          y: points.map((p) => p.score.bounds?.[j] ?? null),
          name: `${i.name} ${bound === "lower" ? "下界" : "上界"}`,
          type: "scatter",
          mode: "lines",
          showlegend: false,
          hoverinfo: "skip",
          line: { color, dash: "dot", width: 0.7 },
        }),
      );
    });
    return traces;
  }, [result, enabled, kind, selectedLead]);
  return (
    <>
      <div className="plot-toolbar">
        <div className="segmented">
          <button
            className={kind === "nis" ? "active" : ""}
            onClick={() => setKind("nis")}
          >
            NIS
          </button>
          <button
            className={kind === "nees" ? "active" : ""}
            onClick={() => setKind("nees")}
          >
            NEES
          </button>
          <button
            className={kind === "forecast" ? "active" : ""}
            onClick={() => setKind("forecast")}
          >
            纯预测 NEES
          </button>
        </div>
        {kind === "forecast" && (
          <Field label="提前量">
            <select
              value={selectedLead}
              onChange={(e) => setLead(Number(e.target.value))}
            >
              {leads.map((l) => (
                <option key={l} value={l}>
                  +{l} s
                </option>
              ))}
            </select>
          </Field>
        )}
        <NumberField
          label="参考置信水平"
          value={confidence}
          min={0.5}
          max={0.999}
          step={0.01}
          onChange={onConfidenceChange}
        />
      </div>
      {result ? (
        <Plot
          data={data}
          height={255}
          layout={{
            yaxis: {
              title: {
                text:
                  kind === "nis"
                    ? "NIS"
                    : kind === "nees"
                      ? "NEES"
                      : "纯预测 NEES",
              },
              gridcolor: "#e6ecf2",
            },
          }}
          onTimeClick={onTimeChange}
        />
      ) : (
        <EmptyPlot>运行后查看新息与状态协方差的一致性。</EmptyPlot>
      )}
      {result && (
        <details className="consistency-groups">
          <summary>自由度、有效计数与评估状态</summary>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>实例 / 指标</th>
                  <th>自由度</th>
                  <th>有效计数</th>
                  <th>出界比例</th>
                  <th>评估状态</th>
                </tr>
              </thead>
              <tbody>
                {result.report.instances
                  .filter((m) => enabled.includes(m.instance_id))
                  .flatMap((m) =>
                    m.consistency.map((group, index) => (
                      <tr key={`${m.instance_id}-${index}`}>
                        <th>
                          {m.name} /{" "}
                          {String(group.statistic ?? group.kind ?? "")}
                        </th>
                        <td>{group.dof ?? "—"}</td>
                        <td>{group.count}</td>
                        <td>
                          {group.outside_fraction == null
                            ? "—"
                            : `${(group.outside_fraction * 100).toFixed(1)}%`}
                        </td>
                        <td>
                          {Array.isArray(group.state_names)
                            ? group.state_names.join(", ")
                            : "观测空间"}
                        </td>
                      </tr>
                    )),
                  )}
              </tbody>
            </table>
          </div>
        </details>
      )}
      <div className="diagnostic-note">
        <p>
          虚线为实验配置中 {(result?.config.confidence ?? confidence) * 100}%
          的双侧卡方参考界，自由度随有效状态与观测维数确定。
        </p>
        <p>
          EKF / UKF 使用近似诊断；IMM
          为高斯近似参考。连续时刻相关样本的出界比例是描述统计。
        </p>
        {kind === "forecast" && (
          <p>纯预测 NIS：无新观测。没有未来真值的样本不参与 NEES。</p>
        )}
      </div>
    </>
  );
}
