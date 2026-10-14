import type { RunPayload } from "../api/types";
import MetricsTable from "./MetricsTable";
import { api } from "../api/client";
export default function ReportPanel({
  result,
  runId,
  onTimeChange,
  onCandidate,
}: {
  result: RunPayload | null;
  runId: string | null;
  onTimeChange: (t: number) => void;
  onCandidate: (patch: Record<string, unknown>, instanceId: string) => void;
}) {
  if (!result)
    return (
      <p className="empty-text">
        实验完成后，依据实际误差、频率和协方差生成比较总结与调参候选。
      </p>
    );
  const failed = result.instances.filter((i) => i.status === "failed");
  return (
    <div className="report-panel">
      {failed.length > 0 && (
        <p className="warning-message">
          部分比较未完成：
          {failed
            .map((i) => `${i.name}（${i.error ?? "实例失败"}）`)
            .join("；")}
          。以下结论只涵盖成功实例。
        </p>
      )}
      <MetricsTable report={result.report} />
      <div className="summary-copy">
        {result.report.summary.map((s, i) => (
          <p key={i}>{s}</p>
        ))}
      </div>
      <div className="recommendations">
        {result.report.recommendations.map((r, i) => (
          <article key={i}>
            <h3>{r.title}</h3>
            <button
              className="evidence"
              onClick={() => onTimeChange(r.evidence.interval[0])}
            >
              {r.evidence.metric} = {r.evidence.value.toFixed(4)} ·{" "}
              {r.evidence.interval.map((t) => t.toFixed(2)).join("–")} s
            </button>
            <p>{r.causes.join("；")}</p>
            <p className="help">候选原因，需在相同观测上复跑验证。</p>
            <button onClick={() => onCandidate(r.trial_patch, r.instance_id)}>
              复制为参数候选
            </button>
          </article>
        ))}
      </div>
      {runId && (
        <div className="export-actions">
          <span>导出不可变结果</span>
          <a className="button" href={api.exportUrl(runId, "json")} download>
            JSON 配置与结果
          </a>
          <a className="button" href={api.exportUrl(runId, "csv")} download>
            CSV 数值序列
          </a>
          <a className="button" href={api.exportUrl(runId, "npz")} download>
            NPZ 完整矩阵
          </a>
          <a className="button" href={api.exportUrl(runId, "zip")} download>
            ZIP 复现包
          </a>
          <a
            className="button"
            href={api.exportUrl(runId, "markdown")}
            download
          >
            Markdown 报告
          </a>
        </div>
      )}
    </div>
  );
}
