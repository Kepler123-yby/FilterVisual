import type { ExperimentConfig } from "../api/types";
export function validateDraft(draft: ExperimentConfig): string[] {
  const errors: string[] = [];
  if (draft.duration_s <= 0 || draft.duration_s > 120)
    errors.push("仿真时长需在 0–120 秒之间");
  if (!(draft.simulation_dt > 0)) errors.push("仿真步长需要大于 0");
  if (!(draft.geometry.rA > 0 && draft.geometry.rB > 0))
    errors.push("两组装甲板半径需要大于 0");
  if (!draft.filters.some((f) => f.enabled !== false))
    errors.push("至少启用一个滤波器实例");
  if (
    draft.forecast.enabled &&
    (draft.forecast.leads_s.length === 0 ||
      draft.forecast.leads_s.some((s) => !Number.isFinite(s) || s <= 0))
  )
    errors.push("预测提前量需要大于 0");
  for (const f of draft.filters) {
    if (!(f.frequency_hz > 0)) errors.push(`${f.name}：更新频率需要大于 0`);
    if (f.P0.length !== f.x0.length)
      errors.push(`${f.name}：P₀ 与 x₀ 维数不一致`);
    if (
      f.P0.some(
        (row, i) =>
          row.length !== f.x0.length ||
          row[i] <= 0 ||
          row.some((n) => !Number.isFinite(n)),
      )
    )
      errors.push(`${f.name}：P₀ 需要正对角且维数匹配`);
    if (f.kind === "ukf" && !(f.alpha > 0))
      errors.push(`${f.name}：UKF α 需要大于 0`);
  }
  return errors;
}
export function degreeToRadian(value: number) {
  return (value * Math.PI) / 180;
}
export function radianToDegree(value: number) {
  return (value * 180) / Math.PI;
}
export function configFingerprint(value: unknown): string {
  return JSON.stringify(value);
}
export function cloneFilter<T extends { id: string; name: string }>(
  filter: T,
  id: string = crypto.randomUUID(),
): T {
  return { ...structuredClone(filter), id, name: `${filter.name} 副本` };
}
