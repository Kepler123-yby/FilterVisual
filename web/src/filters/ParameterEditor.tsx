import { lazy, Suspense, useState } from "react";
import type { FilterConfig, Geometry } from "../api/types";
import { Field, NumberField } from "../app/components";
import { MatrixEditor } from "./MatrixEditor";
import IMMEditor from "./IMMEditor";
import {
  applyFormulaSpec,
  ADVANCED_FORMULA_PREFIX,
  createFormulaPreset,
  readFormulaSpec,
  recoverFormulaSpec,
} from "./formulaModel";
const ModelEditor = lazy(() => import("./ModelEditor"));
const FormulaModelEditor = lazy(() => import("./FormulaModelEditor"));
export function containsNonFinite(value: unknown): boolean {
  return typeof value === "number"
    ? !Number.isFinite(value)
    : Array.isArray(value)
      ? value.some(containsNonFinite)
      : value && typeof value === "object"
        ? Object.values(value).some(containsNonFinite)
        : false;
}
export function JsonField({
  label,
  value,
  onChange,
  rows = 3,
  validate,
}: {
  label: string;
  value: unknown;
  onChange: (value: unknown) => void;
  rows?: number;
  validate?: (value: unknown) => string | null;
}) {
  const [raw, setRaw] = useState<string | null>(null);
  const [error, setError] = useState("");
  return (
    <>
      <Field label={label}>
        <textarea
          rows={rows}
          spellCheck={false}
          value={raw ?? JSON.stringify(value)}
          aria-invalid={!!error}
          onChange={(e) => {
            setRaw(e.target.value);
            try {
              const parsed: unknown = JSON.parse(e.target.value);
              if (containsNonFinite(parsed)) {
                setError("所有数值必须有限，指数过大请减小数值");
                return;
              }
              const issue =
                validate?.(parsed) ??
                (Array.isArray(value)
                  ? !Array.isArray(parsed) ||
                    parsed.some(
                      (n) => typeof n !== "number" || !Number.isFinite(n),
                    )
                    ? "需要有限数字数组"
                    : null
                  : value && typeof value === "object"
                    ? !parsed ||
                      typeof parsed !== "object" ||
                      Array.isArray(parsed)
                      ? "需要 JSON 对象"
                      : null
                    : null);
              if (issue) {
                setError(issue);
                return;
              }
              setError("");
              onChange(parsed);
            } catch {
              setError("JSON 尚未完整，修正后自动保存");
            }
          }}
          onBlur={() => {
            if (!error) setRaw(null);
          }}
        />
      </Field>
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
    </>
  );
}
export default function ParameterEditor({
  filter,
  onChange,
  geometry,
}: {
  filter: FilterConfig;
  geometry: Geometry;
  onChange: (next: FilterConfig) => void;
}) {
  const patch = (value: Partial<FilterConfig>) =>
    onChange({ ...filter, ...value });
  const n = filter.x0.length;
  const formula = readFormulaSpec(filter);
  return (
    <div className="parameters">
      <details>
        <summary>噪声假设 Q / R</summary>
        {(filter.model.kind === "custom" || filter.kind === "imm") && (
          <div className="field-grid">
            <NumberField
              label="自定义模型 Q 倍率"
              value={filter.q_scale ?? 1}
              min={0}
              onChange={(q_scale) => patch({ q_scale })}
            />
            <NumberField
              label="自定义模型 R 倍率"
              value={filter.r_scale ?? 1}
              min={0.001}
              onChange={(r_scale) => patch({ r_scale })}
            />
          </div>
        )}
        <p className="help">
          {filter.model.kind === "builtin"
            ? "内置 Q 使用连续白加速度强度，按实际 Δt 构造离散协方差。"
            : "Q 是实际预测间隔内的过程协方差；倍率作用于模型返回的矩阵。"}
        </p>
        {filter.model.kind === "builtin" && filter.kind !== "imm" && (
          <div className="field-grid">
            <NumberField
              label="平移 Q 强度"
              value={filter.q_translation}
              min={0}
              onChange={(q_translation) => patch({ q_translation })}
            />
            <NumberField
              label="自旋 Q 强度"
              value={filter.q_rotation}
              min={0}
              onChange={(q_rotation) => patch({ q_rotation })}
            />
            <NumberField
              label="几何 Q 强度"
              value={filter.q_geometry}
              min={0}
              onChange={(q_geometry) => patch({ q_geometry })}
            />
          </div>
        )}
        {filter.model.kind === "builtin" && (
          <MatrixEditor
            label="滤波器 R"
            value={filter.R}
            size={filter.R.length}
            onChange={(R) => patch({ R })}
            hint="每板 [x,y,z,yaw]；各轴方差，不是真实观测噪声"
          />
        )}
        {filter.kind === "imm" && (
          <p className="help">IMM 各模式的 Q 在下方分别设置。</p>
        )}
        {filter.model.kind === "custom" && (
          <p className="help">
            {formula
              ? "完整 Q / R 在下方模型表单的矩阵中修改，无需编辑代码。"
              : "Q(dt) / R(frame) 和完整矩阵在 Python 源码中定义，倍率作用于各自返回的协方差。"}
          </p>
        )}
      </details>
      <details>
        <summary>
          初始状态 x₀ / P₀ <small>{n} 维</small>
        </summary>
        <p className="help">
          {formula
            ? "表单模型的初值和初始方差在下方状态表中修改；这里可检查或调整完整 P₀。"
            : "内置顺序：[cx,cy,zA,vx,vy,vz,θ,ω,rA,rB,dh]。x₀ 不读取隐藏真值。"}
        </p>
        <JsonField
          label="初始状态 x₀（JSON）"
          value={filter.x0}
          onChange={(value) => {
            if (
              Array.isArray(value) &&
              value.every((n) => typeof n === "number" && Number.isFinite(n))
            )
              patch({ x0: value });
          }}
        />
        <MatrixEditor
          label="P₀"
          value={filter.P0}
          size={n}
          onChange={(P0) => patch({ P0 })}
          hint="填写方差，而非标准差；后端检查完整矩阵正定性"
        />
      </details>
      {(filter.kind === "ukf" || filter.kind === "imm") && (
        <details>
          <summary>UKF 无迹变换参数</summary>
          <div className="field-grid three">
            <NumberField
              label="α"
              value={filter.alpha}
              min={0.001}
              onChange={(alpha) => patch({ alpha })}
            />
            <NumberField
              label="β"
              value={filter.beta}
              onChange={(beta) => patch({ beta })}
            />
            <NumberField
              label="κ"
              value={filter.kappa}
              onChange={(kappa) => patch({ kappa })}
            />
          </div>
        </details>
      )}
      {filter.kind === "imm" && (
        <IMMEditor filter={filter} geometry={geometry} onChange={onChange} />
      )}
      <details>
        <summary>预测模型与方程</summary>
        <Field label="模型来源">
          <select
            value={formula ? "formula" : filter.model.kind}
            onChange={(e) => {
              if (e.target.value === "formula") {
                onChange(
                  applyFormulaSpec(
                    filter,
                    recoverFormulaSpec(filter) ??
                      createFormulaPreset("armor", geometry),
                  ),
                );
              } else if (e.target.value === "builtin" && formula) {
                const next = applyFormulaSpec(
                  filter,
                  createFormulaPreset("armor", geometry),
                );
                onChange({
                  ...next,
                  model: { kind: "builtin", builtin_name: "rm_cv", params: {} },
                });
              } else {
                patch({
                  model: {
                    ...filter.model,
                    kind: e.target.value as "builtin" | "custom",
                    source: formula
                      ? `${ADVANCED_FORMULA_PREFIX}${filter.model.source}`
                      : filter.model.source,
                  },
                });
              }
            }}
          >
            <option value="builtin">内置四板 CV 模型</option>
            <option value="formula">表单配置模型（无需 Python）</option>
            <option value="custom">自定义 Python 模型（高级）</option>
          </select>
        </Field>
        {formula ? (
          <Suspense fallback={<p>正在加载模型表单…</p>}>
            <FormulaModelEditor
              filter={filter}
              geometry={geometry}
              onChange={onChange}
            />
          </Suspense>
        ) : filter.model.kind === "custom" ? (
          <Suspense fallback={<p>正在加载模型编辑器…</p>}>
            <ModelEditor
              filter={filter}
              geometry={geometry}
              onChange={onChange}
            />
          </Suspense>
        ) : (
          <p className="help">
            中心匀速、恒定角速度、几何随机游走。自定义模型可编写 f、h、Q 与
            Jacobian，以及物理投影 / 真值映射。
          </p>
        )}
      </details>
    </div>
  );
}
export function TransitionPreview({
  rates,
  dt,
}: {
  rates: number[][];
  dt: number;
}) {
  const a = rates[0]?.[1] ?? 0,
    b = rates[1]?.[0] ?? 0,
    s = a + b,
    e = Math.exp(-s * dt);
  const p01 = s === 0 ? 0 : (a / s) * (1 - e),
    p10 = s === 0 ? 0 : (b / s) * (1 - e);
  return (
    <div className="transition-matrix" aria-label="参考转移概率矩阵">
      Π({dt.toFixed(3)} s)
      <br />[{(1 - p01).toFixed(3)}, {p01.toFixed(3)}]<br />[{p10.toFixed(3)},{" "}
      {(1 - p10).toFixed(3)}]
    </div>
  );
}
