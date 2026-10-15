import type { Report } from "../api/types";
import { formatNumber } from "../app/components";
export default function MetricsTable({ report }: { report: Report }) {
  return (
    <div className="table-scroll">
      <p className="metrics-explanation">
        主状态在评估网格统计，各指标仅使用有真值的有效样本；纯预测表格包含各实例全部有效端点，总结使用共同有效预测起点。
      </p>
      <table>
        <thead>
          <tr>
            <th>实例</th>
            <th>中心 RMSE（m）</th>
            <th>角度 RMSE（rad）</th>
            <th>实际更新（Hz）</th>
            <th>耗时（s）</th>
            <th>评估样本</th>
          </tr>
        </thead>
        <tbody>
          {report.instances.map((m) => (
            <tr key={m.instance_id}>
              <th>
                {m.name}
                <small>
                  {m.kind.toUpperCase()} ·{" "}
                  {m.status === "completed"
                    ? "完成"
                    : m.status === "failed"
                      ? "失败"
                      : m.status}
                </small>
              </th>
              <td>{formatNumber(m.position_rmse, 4)}</td>
              <td>{formatNumber(m.angle_rmse, 4)}</td>
              <td>{formatNumber(m.actual_update_hz, 2)}</td>
              <td>{formatNumber(m.elapsed_s, 3)}</td>
              <td>{m.sample_count}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {report.instances.some((i) => i.forecast.length > 0) && (
        <table className="forecast-metrics">
          <thead>
            <tr>
              <th>纯预测</th>
              <th>提前量（s）</th>
              <th>中心 RMSE（m）</th>
              <th>A0 / A1 / A2 / A3 RMSE（m）</th>
              <th>有效端点</th>
            </tr>
          </thead>
          <tbody>
            {report.instances.flatMap((i) =>
              i.forecast.map((f) => (
                <tr key={`${i.instance_id}-${f.lead_s}`}>
                  <th>{i.name}</th>
                  <td>{f.lead_s}</td>
                  <td>{formatNumber(f.position_rmse, 4)}</td>
                  <td>
                    {f.armor_rmse.map((v) => formatNumber(v, 4)).join(" / ")}
                  </td>
                  <td>{f.count}</td>
                </tr>
              )),
            )}
          </tbody>
        </table>
      )}
    </div>
  );
}
