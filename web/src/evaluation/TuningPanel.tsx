import { useEffect, useRef, useState } from "react";
import type { ExperimentConfig, RunPayload, RunStatus } from "../api/types";
import { api } from "../api/client";
import { fromWireConfig } from "../api/adapter";
import type { WireConfig } from "../api/adapter";
import { Field, NumberField, formatNumber } from "../app/components";
import type { Report } from "../api/types";
import { cloneFilter } from "../experiments/validation";
import { Plot } from "../plots/Plot";
import type { Data } from "plotly.js";
export function mergePatch<T>(base: T, patch: Record<string, unknown>): T {
  const next = structuredClone(base) as Record<string, unknown>;
  for (const [key, value] of Object.entries(patch)) {
    next[key] =
      value &&
      typeof value === "object" &&
      !Array.isArray(value) &&
      next[key] &&
      typeof next[key] === "object" &&
      !Array.isArray(next[key])
        ? mergePatch(next[key], value as Record<string, unknown>)
        : structuredClone(value);
  }
  return next as T;
}
interface ScanCandidate {
  multiplier: number;
  value: number;
  parameter_diff: Record<string, unknown>;
  config: WireConfig;
  report: Report;
}
interface ScanPayload {
  type: "noise_scan";
  baseline: ScanCandidate;
  candidates: ScanCandidate[];
  summary: string[];
}
interface MonteCarloPayload {
  type: "monte_carlo";
  trials: number;
  seeds: number[];
  groups: {
    instance_id: string;
    t: number;
    statistic: string;
    dof: number;
    count: number;
    mean: number;
    bounds: number[];
    state_names: string[];
    assumption: string;
  }[];
  summary: string[];
  notes: string[];
}
export default function TuningPanel({
  result,
  runId,
  onConfig,
}: {
  result: RunPayload | null;
  runId: string | null;
  onConfig: (config: ExperimentConfig) => void;
}) {
  const [parameter, setParameter] = useState("q_scale"),
    [instanceId, setInstanceId] = useState(""),
    [count, setCount] = useState(20),
    [multipliers, setMultipliers] = useState("0.1, 0.3, 1, 3, 10"),
    [busy, setBusy] = useState(""),
    [error, setError] = useState(""),
    [scan, setScan] = useState<ScanPayload | null>(null),
    [mc, setMc] = useState<MonteCarloPayload | null>(null),
    [job, setJob] = useState<RunStatus | null>(null),
    [statistic, setStatistic] = useState("anees");
  const mounted = useRef(true);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const selected = instanceId || result?.instances[0]?.id || "";
  async function execute(kind: "scan" | "mc") {
    if (!runId) return;
    setBusy(kind);
    setError("");
    try {
      const nums = multipliers.split(",").map((s) => Number(s.trim()));
      if (
        kind === "scan" &&
        (!nums.length || nums.some((n) => !Number.isFinite(n) || n <= 0))
      )
        throw new Error("倍率列表需要为正的有限数字，用逗号分隔。");
      let status =
        kind === "scan"
          ? await api.scan(runId, {
              instance_id: selected,
              parameter,
              multipliers: nums,
            })
          : await api.monteCarlo(runId, { trials: count });
      while (
        mounted.current &&
        ["queued", "validating", "running"].includes(status.status)
      ) {
        setJob(status);
        await new Promise((resolve) => setTimeout(resolve, 800));
        status = await api.getStatus(status.id);
      }
      if (!mounted.current) return;
      setJob(status);
      if (status.status !== "completed")
        throw new Error(
          status.error ??
            `试验${status.status === "cancelled" ? "已停止" : "失败"}`,
        );
      const payload = (await api.getAnalysis(status.id)) as
        | ScanPayload
        | MonteCarloPayload;
      if (payload.type === "noise_scan") setScan(payload);
      else setMc(payload);
    } catch (e) {
      if (mounted.current) setError((e as Error).message);
    } finally {
      if (mounted.current) setBusy("");
    }
  }
  function apply(c: ScanCandidate) {
    if (!result) return;
    const candidate = cloneFilter(fromWireConfig(c.config).filters[0]);
    candidate.name = `${candidate.name.replace(" 副本", "")} ${parameter === "q_scale" ? "Q" : "R"}×${c.multiplier}`;
    onConfig({
      ...structuredClone(result.config),
      filters: [...structuredClone(result.config.filters), candidate],
    });
  }
  const mcData: Data[] = mc
    ? [
        ...new Set(
          mc.groups
            .filter((g) => g.statistic === statistic)
            .map((g) => `${g.instance_id}/${g.dof}`),
        ),
      ].flatMap((key) => {
        const groups = mc.groups.filter(
          (g) =>
            g.statistic === statistic && `${g.instance_id}/${g.dof}` === key,
        );
        return [
          {
            x: groups.map((g) => g.t),
            y: groups.map((g) => g.mean),
            name: key,
            mode: "lines" as const,
            type: "scatter" as const,
          },
          ...[0, 1].map((b) => ({
            x: groups.map((g) => g.t),
            y: groups.map((g) => g.bounds[b]),
            showlegend: false,
            mode: "lines" as const,
            type: "scatter" as const,
            line: { dash: "dot" as const, width: 1 },
          })),
        ];
      })
    : [];
  return (
    <div className="tuning-panel">
      <p className="help">
        参数扫描复用基线的观测流。候选结果独立保存，复制候选只更新草稿。
      </p>
      <div className="tuning-controls">
        <Field label="基线实例">
          <select
            value={selected}
            onChange={(e) => setInstanceId(e.target.value)}
          >
            {result?.instances.map((i) => (
              <option key={i.id} value={i.id}>
                {i.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="扫描参数">
          <select
            value={parameter}
            onChange={(e) => setParameter(e.target.value)}
          >
            <option value="q_scale">Q 整体倍率</option>
            <option value="r_scale">R 整体倍率</option>
          </select>
        </Field>
        <Field label="倍率列表">
          <input
            value={multipliers}
            onChange={(e) => setMultipliers(e.target.value)}
          />
        </Field>
        <button
          className="primary"
          disabled={!runId || !!busy}
          onClick={() => void execute("scan")}
        >
          {busy === "scan" ? "候选试验中…" : "扫描 Q / R"}
        </button>
      </div>
      {busy && job && (
        <div className="analysis-progress">
          <span>
            {job.stage} · {Math.round(job.progress * 100)}%
          </span>
          <progress value={job.progress} max={1} />
          <button onClick={() => void api.cancel(job.id).then(setJob)}>
            停止试验
          </button>
        </div>
      )}
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
      {scan && (
        <>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>候选倍率</th>
                  <th>中心 RMSE（m）</th>
                  <th>角度 RMSE（rad）</th>
                  <th>参数</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th>原基线</th>
                  <td>
                    {formatNumber(
                      scan.baseline.report.instances[0]?.position_rmse,
                      4,
                    )}
                  </td>
                  <td>
                    {formatNumber(
                      scan.baseline.report.instances[0]?.angle_rmse,
                      4,
                    )}
                  </td>
                  <td>保持不变</td>
                </tr>
                {scan.candidates.map((c, i) => (
                  <tr key={i}>
                    <th>{c.multiplier}×</th>
                    <td>
                      {formatNumber(c.report.instances[0]?.position_rmse, 4)}
                    </td>
                    <td>
                      {formatNumber(c.report.instances[0]?.angle_rmse, 4)}
                    </td>
                    <td>
                      <button onClick={() => apply(c)}>复制候选到草稿</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {scan.summary.map((s, i) => (
            <p className="help" key={i}>
              {s}
            </p>
          ))}
        </>
      )}
      <div className="monte-carlo">
        <div>
          <h3>多种子一致性试验</h3>
          <p className="help">
            同一时刻聚合独立试验的 ANIS /
            ANEES，避免把连续相关样本当作独立试验。
          </p>
        </div>
        <NumberField
          label="独立试验次数"
          value={count}
          min={2}
          max={100}
          step={1}
          onChange={setCount}
        />
        <button disabled={!runId || !!busy} onClick={() => void execute("mc")}>
          {busy === "mc" ? "多种子运行中…" : "运行 Monte Carlo"}
        </button>
      </div>
      {mc && (
        <div className="mc-result">
          <strong>独立试验：{mc.trials} 次</strong>
          {mc.summary?.map((s, i) => (
            <p key={i}>{s}</p>
          ))}
          <Field label="平均统计量">
            <select
              value={statistic}
              onChange={(e) => setStatistic(e.target.value)}
            >
              <option value="anees">ANEES</option>
              <option value="anis">ANIS</option>
            </select>
          </Field>
          <Plot
            data={mcData}
            height={240}
            layout={{
              yaxis: {
                title: { text: statistic.toUpperCase() },
                gridcolor: "#e6ecf2",
              },
            }}
          />
          {mc.notes.map((n, i) => (
            <p key={i} className="help">
              {n}
            </p>
          ))}
          <details>
            <summary>查看聚合数值</summary>
            <pre>{JSON.stringify(mc, null, 2)}</pre>
          </details>
        </div>
      )}
    </div>
  );
}
