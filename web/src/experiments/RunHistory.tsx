import type { RunStatus } from "../api/types";
const labels: Record<string, string> = {
  completed: "已完成",
  running: "运行中",
  queued: "排队中",
  validating: "校验中",
  failed: "失败",
  cancelled: "已取消",
  timed_out: "超时",
};
export default function RunHistory({
  runs,
  selectedId,
  onSelect,
}: {
  runs: RunStatus[];
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <details className="history">
      <summary>
        实验记录 <span>{runs.length}</span>
      </summary>
      {runs.length ? (
        <div className="history-list">
          {runs.map((run) => (
            <button
              key={run.id}
              className={`history-item ${run.id === selectedId ? "selected" : ""}`}
              onClick={() => onSelect(run.id)}
            >
              <span>{run.name || `实验 ${run.id.slice(0, 8)}`}</span>
              <small>
                {new Date(run.created_at).toLocaleString("zh-CN")} ·{" "}
                {labels[run.status] || run.status}
              </small>
            </button>
          ))}
        </div>
      ) : (
        <p className="help">运行后记录配置和结果，旧实验可随时打开。</p>
      )}
    </details>
  );
}
