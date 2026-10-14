import { useMemo } from "react";
import type { Data } from "plotly.js";
import type { RunPayload, InstanceResult } from "../api/types";
import { COLORS, EmptyPlot } from "../app/components";
import { Plot } from "./Plot";
export const STATE_LABELS: Record<string, string> = {
  cx: "中心 X",
  cy: "中心 Y",
  zA: "A 组高度",
  vx: "速度 X",
  vy: "速度 Y",
  vz: "速度 Z",
  theta: "参考角 θ",
  omega: "角速度 ω",
  rA: "A 组半径",
  rB: "B 组半径",
  dh: "板高差",
};
export function unwrap(values: (number | null)[], wrapped: boolean) {
  if (wrapped)
    return values.map((v) =>
      v == null ? null : Math.atan2(Math.sin(v), Math.cos(v)),
    );
  let last: number | undefined;
  return values.map((v) => {
    if (v == null) return null;
    const n =
      last == null
        ? v
        : last + Math.atan2(Math.sin(v - last), Math.cos(v - last));
    last = n;
    return n;
  });
}
export function stateIndex(i: InstanceResult, state: string) {
  const aliases: Record<string, string[]> = {
    theta: ["theta", "θ", "yaw"],
    omega: ["omega", "ω", "v_yaw"],
  };
  return i.state_names.findIndex(
    (s) => s === state || aliases[state]?.includes(s),
  );
}
export default function StatePlot({
  result,
  state,
  enabled,
  time,
  onTimeChange,
  error = false,
  wrapped = false,
}: {
  result: RunPayload | null;
  state: string;
  enabled: string[];
  time: number;
  onTimeChange: (t: number) => void;
  error?: boolean;
  wrapped?: boolean;
}) {
  const selected =
    result?.instances.filter(
      (i) => enabled.includes(i.id) && stateIndex(i, state) >= 0,
    ) ?? [];
  const unit = selected[0]?.units[stateIndex(selected[0], state)];
  const units = [
    ...new Set(selected.map((i) => i.units[stateIndex(i, state)])),
  ];
  const instances = selected.filter(
    (i) => i.units[stateIndex(i, state)] === unit,
  );
  const data = useMemo(
    () =>
      result ? makeStateTraces(result, instances, state, error, wrapped) : [],
    [result, state, enabled, error, wrapped],
  );
  const layout = useMemo(
    () => ({
      yaxis: {
        title: {
          text: `${error ? "误差" : (STATE_LABELS[state] ?? state)}${unit ? `（${unit}）` : ""}`,
          font: { size: 11 },
        },
        gridcolor: "#e6ecf2",
        zerolinecolor: "#aab8c6",
      },
      shapes: [
        {
          type: "line" as const,
          x0: time,
          x1: time,
          y0: 0,
          y1: 1,
          yref: "paper" as const,
          line: { color: "#8195ab", width: 1, dash: "dot" as const },
        },
      ],
    }),
    [state, unit, time, error],
  );
  return (
    <div data-testid={error ? "error-plot" : "state-plot"}>
      {units.length > 1 && (
        <p className="plot-unit-note">
          状态单位不同，当前叠加图只显示 {unit} 组；切换并排比较查看其余实例。
        </p>
      )}
      {result ? (
        data.length && instances.length ? (
          <Plot
            data={data}
            layout={layout}
            height={225}
            onTimeClick={onTimeChange}
          />
        ) : (
          <EmptyPlot>选择一个包含此状态的实例。</EmptyPlot>
        )
      ) : (
        <EmptyPlot>
          {error
            ? "运行后查看估计值与同一时刻真值的差距。"
            : "配置场景后运行，显示真值、估计和 ±2σ 区间。"}
        </EmptyPlot>
      )}
    </div>
  );
}

export function makeStateTraces(
  result: RunPayload,
  instances: InstanceResult[],
  state: string,
  error = false,
  wrapped = false,
): Data[] {
  const traces: Data[] = [];
  const truthKeys = new Set<string>();
  for (const instance of instances) {
    const idx = stateIndex(instance, state);
    if (idx < 0) continue;
    const x = instance.samples.map((s) => s.t),
      angular = instance.angular_indices.includes(idx),
      color =
        COLORS[
          result.instances.findIndex((i) => i.id === instance.id) %
            COLORS.length
        ];
    if (!error) {
      const truth = instance.samples.map((s) => s.truth[idx] ?? null),
        key = JSON.stringify({ x, truth });
      if (truth.some((v) => v != null) && !truthKeys.has(key)) {
        truthKeys.add(key);
        traces.push({
          x,
          y: angular ? unwrap(truth, wrapped) : truth,
          name: truthKeys.size === 1 ? "真值" : `${instance.name} 映射真值`,
          type: "scatter",
          mode: "lines",
          line: { color: "#263e57", width: 2.3 },
        });
      }
    }
    const raw = instance.samples.map((s) => (error ? s.error[idx] : s.x[idx])),
      y = angular && !error ? unwrap(raw, wrapped) : raw;
    if (!error) {
      const low = y.map((v, j) =>
          v == null
            ? null
            : v - 2 * Math.sqrt(Math.max(0, instance.samples[j].P_diag[idx])),
        ),
        high = y.map((v, j) =>
          v == null
            ? null
            : v + 2 * Math.sqrt(Math.max(0, instance.samples[j].P_diag[idx])),
        );
      traces.push(
        {
          x,
          y: low,
          type: "scatter",
          mode: "lines",
          line: { width: 0 },
          showlegend: false,
          hoverinfo: "skip",
        },
        {
          x,
          y: high,
          type: "scatter",
          mode: "lines",
          fill: "tonexty",
          fillcolor: `${color}16`,
          line: { width: 0 },
          showlegend: false,
          hoverinfo: "skip",
        },
      );
    }
    traces.push({
      x,
      y,
      name: instance.name,
      type: "scatter",
      mode: "lines",
      line: { color, width: 1.7 },
    });
  }
  return traces;
}
