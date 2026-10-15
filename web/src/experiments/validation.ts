import type { ExperimentConfig } from "../api/types";
import {
  createFormulaPreset,
  getFormulaIssues,
  readFormulaSpec,
} from "../filters/formulaModel";
export function validateDraft(draft: ExperimentConfig): string[] {
  const errors: string[] = [];
  if (draft.duration_s <= 0 || draft.duration_s > 120)
    errors.push("仿真时长需在 0–120 秒之间");
  if (!(draft.simulation_dt > 0)) errors.push("仿真步长需要大于 0");
  if (!(draft.geometry.rA > 0 && draft.geometry.rB > 0))
    errors.push("两组装甲板半径需要大于 0");
  if (
    draft.translation.speed_range.some((v) => !Number.isFinite(v)) ||
    draft.translation.speed_range[1] < draft.translation.speed_range[0]
  )
    errors.push("速度范围需为有限数值，速度上限须不小于下限");
  if (!draft.filters.some((f) => f.enabled !== false))
    errors.push("至少启用一个滤波器实例");
  if (
    draft.forecast.enabled &&
    (draft.forecast.leads_s.length === 0 ||
      draft.forecast.leads_s.some((s) => !Number.isFinite(s) || s <= 0))
  )
    errors.push("预测提前量需要大于 0");
  for (const f of draft.filters) {
    const formula = readFormulaSpec(f);
    if (formula) {
      errors.push(
        ...getFormulaIssues(formula).map((issue) => `${f.name}：${issue}`),
      );
      if (formula.states.length !== f.x0.length)
        errors.push(`${f.name}：状态表与初值维数不一致`);
    }
    if (f.kind === "imm")
      for (const [index, mode] of f.imm.modes.entries()) {
        if (mode.use_parent_model !== false || !mode.model) continue;
        const modeSpec = readFormulaSpec({ ...f, model: mode.model });
        if (
          mode.model.kind === "builtin" &&
          (f.x0.length !== 11 ||
            (formula &&
              JSON.stringify(
                formula.states.map((s) => [s.name, s.unit, s.angular]),
              ) !==
                JSON.stringify(
                  createFormulaPreset("armor", draft.geometry).states.map(
                    (s) => [s.name, s.unit, s.angular],
                  ),
                )))
        )
          errors.push(
            `${f.name} 模式 ${index + 1}：内置四板模型的 11 维状态须与父模型一致`,
          );
        if (modeSpec) {
          errors.push(
            ...getFormulaIssues(modeSpec).map(
              (issue) => `${f.name} 模式 ${index + 1}：${issue}`,
            ),
          );
          if (modeSpec.states.length !== f.x0.length)
            errors.push(
              `${f.name} 模式 ${index + 1}：状态表与共享初值维数不一致`,
            );
          if (
            formula &&
            JSON.stringify(
              formula.states.map((s) => [s.name, s.unit, s.angular]),
            ) !==
              JSON.stringify(
                modeSpec.states.map((s) => [s.name, s.unit, s.angular]),
              )
          )
            errors.push(
              `${f.name} 模式 ${index + 1}：状态名称、顺序、单位和角度标记须与父模型一致`,
            );
        }
      }
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
