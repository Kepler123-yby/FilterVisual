import { useMemo, useState } from "react";
import type { Data } from "plotly.js";
import type { ForecastRecord, InstanceResult, RunPayload } from "../api/types";
import { COLORS, EmptyPlot, Field, formatNumber } from "../app/components";
import { Plot } from "../plots/Plot";
export function forecastDifference(
  record: ForecastRecord,
  target: "center" | "armor" | "angle",
  plate = 0,
): number | null {
  if (!record.truth_physical || !record.physical) return null;
  if (target === "angle") {
    if (
      record.physical.reference_yaw == null ||
      record.truth_physical.reference_yaw == null
    )
      return null;
    const e =
      record.physical.reference_yaw - record.truth_physical.reference_yaw;
    return Math.atan2(Math.sin(e), Math.cos(e));
  }
  const a =
      target === "armor"
        ? record.physical.armor_positions?.[plate]
        : record.physical.center_xy,
    b =
      target === "armor"
        ? record.truth_physical.armor_positions?.[plate]
        : record.truth_physical.center_xy;
  return a &&
    b &&
    a.every((n) => n != null && Number.isFinite(n)) &&
    b.every((n) => n != null && Number.isFinite(n))
    ? Math.hypot(...a.map((n, i) => n - b[i]))
    : null;
}
export function ForecastTimeLabel({ record }: { record: ForecastRecord }) {
  return (
    <span>
      起点 {record.origin_time.toFixed(2)} s · 提前 {record.lead_s.toFixed(2)} s
      · 目标时刻 {record.target_time.toFixed(2)} s
    </span>
  );
}
function forecastAtOrigin(instance: InstanceResult, time: number) {
  const latest = instance.forecasts
    .filter((f) => f.origin_time <= time + 1e-8)
    .at(-1)?.origin_time;
  return latest == null
    ? []
    : instance.forecasts.filter((f) => Math.abs(f.origin_time - latest) < 1e-8);
}
export default function ForecastPlot({
  result,
  enabled,
  time,
  plate,
  onTimeChange,
}: {
  result: RunPayload | null;
  enabled: string[];
  time: number;
  plate: number;
  onTimeChange: (t: number) => void;
}) {
  const [view, setView] = useState<"error" | "endpoint">("error"),
    [target, setTarget] = useState<"center" | "armor" | "angle">("armor"),
    [preferredLead, setPreferredLead] = useState(0.3);
  const instances =
      result?.instances.filter((i) => enabled.includes(i.id)) ?? [],
    leads = [
      ...new Set(instances.flatMap((i) => i.forecasts.map((f) => f.lead_s))),
    ].sort((a, b) => a - b),
    lead = leads.includes(preferredLead) ? preferredLead : (leads[0] ?? 0.3);
  const origins = instances.flatMap((i) => forecastAtOrigin(i, time));
  const example =
    origins.find((f) => Math.abs(f.lead_s - lead) < 1e-8) ?? origins[0];
  const data = useMemo(() => {
    if (!result) return [];
    const traces: Data[] = [];
    instances.forEach((i) => {
      const color =
          COLORS[
            result.instances.findIndex((v) => v.id === i.id) % COLORS.length
          ],
        records =
          view === "error"
            ? i.forecasts.filter((f) => Math.abs(f.lead_s - lead) < 1e-8)
            : forecastAtOrigin(i, time);
      if (view === "error")
        traces.push({
          x: records.map((f) => f.origin_time),
          y: records.map((f) => forecastDifference(f, target, plate)),
          type: "scatter",
          mode: "lines",
          name: i.name,
          line: { color, width: 1.7 },
          customdata: records.map((f) => f.target_time),
          hovertemplate:
            "起点 %{x:.3f}s<br>目标 %{customdata:.3f}s<br>差距 %{y:.4f}<extra>%{fullData.name}</extra>",
        });
      else {
        const project = (f: ForecastRecord, truth = false) => {
          const p = truth ? f.truth_physical : f.physical;
          if (!p) return null;
          return target === "angle"
            ? p.reference_yaw
            : target === "armor"
              ? (p.armor_positions?.[plate]?.[0] ?? null)
              : (p.center_xy?.[0] ?? null);
        };
        traces.push(
          {
            x: records.map((f) => f.target_time),
            y: records.map((f) => project(f)),
            name: `${i.name} 预测`,
            mode: "lines+markers",
            type: "scatter",
            line: { color, width: 1.8 },
          },
          {
            x: records.map((f) => f.target_time),
            y: records.map((f) => project(f, true)),
            name: `${i.name} 对应未来真值`,
            mode: "lines+markers",
            type: "scatter",
            line: { color: "#263e57", dash: "dot", width: 1.2 },
          },
        );
      }
    });
    return traces;
  }, [result, enabled, view, target, lead, plate, time]);
  const missing = instances.flatMap((i) =>
    i.forecasts.filter(
      (f) => Math.abs(f.lead_s - lead) < 1e-8 && !f.truth_physical,
    ),
  ).length;
  return (
    <div data-testid="forecast-plot">
      <div className="plot-toolbar">
        <div className="segmented">
          <button
            className={view === "error" ? "active" : ""}
            onClick={() => setView("error")}
          >
            持续差距
          </button>
          <button
            className={view === "endpoint" ? "active" : ""}
            onClick={() => setView("endpoint")}
          >
            当前更新的未来状态
          </button>
        </div>
        <Field label="预测对象">
          <select
            value={target}
            onChange={(e) => setTarget(e.target.value as typeof target)}
          >
            <option value="armor">A{plate} 装甲板</option>
            <option value="center">中心</option>
            <option value="angle">参考角 θ</option>
          </select>
        </Field>
        {view === "error" && (
          <Field label="提前量">
            <select
              value={lead}
              onChange={(e) => setPreferredLead(Number(e.target.value))}
            >
              {leads.map((l) => (
                <option key={l} value={l}>
                  +{l.toFixed(3)} s
                </option>
              ))}
            </select>
          </Field>
        )}
      </div>
      {result && instances.some((i) => i.forecasts.length) ? (
        <>
          <div className="forecast-caption">
            {view === "error" ? (
              `每次更新的 +${formatNumber(lead, 3)} s 预测，与对应未来真值比较。${target === "angle" ? "角度差使用最短角。" : "曲线为位置差距的欧氏距离。"}`
            ) : example ? (
              <ForecastTimeLabel record={example} />
            ) : (
              "将时间游标移至一次观测更新之后。"
            )}
            {missing > 0 && (
              <span className="badge warning">
                {missing} 个端点超出真值范围，未评估
              </span>
            )}
          </div>
          <Plot
            data={data}
            height={260}
            layout={{
              xaxis: {
                title: {
                  text:
                    view === "error" ? "预测起点（s）" : "未来目标时刻（s）",
                },
                gridcolor: "#e6ecf2",
              },
              yaxis: {
                title: {
                  text:
                    target === "angle"
                      ? "角度（rad）"
                      : view === "error"
                        ? "位置差距（m）"
                        : "X 位置（m）",
                },
                gridcolor: "#e6ecf2",
              },
              shapes:
                view === "error"
                  ? [
                      {
                        type: "line",
                        x0: time,
                        x1: time,
                        y0: 0,
                        y1: 1,
                        yref: "paper",
                        line: { color: "#8195ab", width: 1, dash: "dot" },
                      },
                    ]
                  : [],
            }}
            onTimeClick={view === "error" ? onTimeChange : undefined}
          />
          <div className="forecast-notes">
            {target === "armor" &&
              instances.some((i) =>
                i.forecasts.some(
                  (f) => f.physical && !f.physical.armor_positions,
                ),
              ) && <span>部分模型未提供装甲板物理投影，该对象未评估。</span>}
            <span>NIS：无新观测</span>
            <span>NEES：使用纯预测协方差与目标时刻真值</span>
          </div>
        </>
      ) : (
        <EmptyPlot>
          在右侧开启“每次观测更新后附带纯预测”，运行后查看未来状态与差距。
        </EmptyPlot>
      )}
    </div>
  );
}
