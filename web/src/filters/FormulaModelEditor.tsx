import { useEffect, useRef, useState } from "react";
import { api } from "../api/client";
import type { FilterConfig, Geometry, ModelValidation } from "../api/types";
import {
  applyFormulaSpec,
  createFormulaPreset,
  getFormulaIssues,
  readFormulaSpec,
  truthRoles,
} from "./formulaModel";
import type { FormulaSpec, FormulaState } from "./formulaModel";
import "./formula-model.css";

const measurements = ["x", "y", "z", "yaw"];
const roleNames: Record<string, string> = {
  cx: "中心 x",
  cy: "中心 y",
  zA: "A 板高度",
  vx: "x 速度",
  vy: "y 速度",
  vz: "高度速度",
  theta: "参考板朝向",
  omega: "角速度",
  rA: "A 板半径",
  rB: "B 板半径",
  dh: "两组板高差",
};

function FormulaMatrix({
  label,
  names,
  value,
  onChange,
}: {
  label: string;
  names: string[];
  value: string[][];
  onChange: (next: string[][]) => void;
}) {
  return (
    <div
      className="formula-matrix-scroll"
      tabIndex={0}
      aria-label={`${label} 矩阵，可横向滚动`}
    >
      <table className="formula-matrix">
        <caption>
          {label} · {names.length} × {names.length}
        </caption>
        <thead>
          <tr>
            <th scope="col">行 / 列</th>
            {names.map((name, i) => (
              <th scope="col" key={i}>
                {name || `状态 ${i + 1}`}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {names.map((name, i) => (
            <tr key={i}>
              <th scope="row">{name || `状态 ${i + 1}`}</th>
              {names.map((other, j) => (
                <td key={j}>
                  <input
                    aria-label={`${label} ${name || i + 1},${other || j + 1}`}
                    value={value[i]?.[j] ?? ""}
                    spellCheck={false}
                    onChange={(event) =>
                      onChange(
                        value.map((row, r) =>
                          row.map((cell, c) =>
                            r === i && c === j ? event.target.value : cell,
                          ),
                        ),
                      )
                    }
                  />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function FormulaModelEditor({
  filter,
  geometry,
  onChange,
}: {
  filter: FilterConfig;
  geometry: Geometry;
  onChange: (next: FilterConfig) => void;
}) {
  const [preset, setPreset] = useState<"armor" | "xy" | "bias">("armor");
  const [validation, setValidation] = useState<ModelValidation | null>(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const validationSequence = useRef(0);
  const persisted = readFormulaSpec(filter);
  const spec = persisted ?? createFormulaPreset("armor", geometry);
  const issues = getFormulaIssues(spec);
  const signature = JSON.stringify([
    filter.model,
    filter.x0,
    filter.P0,
    geometry,
  ]);

  useEffect(() => {
    validationSequence.current += 1;
    setValidation(null);
    setError("");
    setBusy(false);
  }, [signature]);

  function update(next: FormulaSpec, renamedStateIndex?: number) {
    validationSequence.current += 1;
    setValidation(null);
    setError("");
    setBusy(false);
    onChange(applyFormulaSpec(filter, next, renamedStateIndex));
  }

  function patchState(index: number, patch: Partial<FormulaState>) {
    update(
      {
        ...spec,
        states: spec.states.map((state, i) =>
          i === index ? { ...state, ...patch } : state,
        ),
      },
      patch.name !== undefined ? index : undefined,
    );
  }

  function reorder(index: number, nextIndex: number) {
    const order = spec.states.map((_, i) => i);
    [order[index], order[nextIndex]] = [order[nextIndex], order[index]];
    update({
      ...spec,
      states: order.map((i) => spec.states[i]),
      q: order.map((i) => order.map((j) => spec.q[i][j])),
    });
  }

  function addState() {
    let suffix = 1;
    while (spec.states.some((state) => state.name === `state_${suffix}`))
      suffix += 1;
    const name = `state_${suffix}`;
    update({
      ...spec,
      states: [
        ...spec.states,
        {
          name,
          unit: "",
          angular: false,
          initial: 0,
          variance: 1,
          transition: name,
          truth: "",
        },
      ],
      q: [
        ...spec.q.map((row) => [...row, "0"]),
        [...spec.states.map(() => "0"), "0.000001*dt"],
      ],
    });
  }

  function removeState(index: number) {
    update({
      ...spec,
      states: spec.states.filter((_, i) => i !== index),
      q: spec.q
        .filter((_, i) => i !== index)
        .map((row) => row.filter((_, j) => j !== index)),
    });
  }

  async function validate() {
    const sequence = ++validationSequence.current;
    const candidate = applyFormulaSpec(filter, spec);
    setBusy(true);
    setValidation(null);
    setError("");
    try {
      const result = await api.validateModel({
        definition: {
          id: `model-${filter.id}`,
          kind: "python",
          builtin_name: null,
          source: candidate.model.source,
          params: candidate.model.params,
        },
        geometry: {
          radius_a: geometry.rA,
          radius_b: geometry.rB,
          height_a: geometry.zA,
          height_diff: geometry.dh,
          reference_id: geometry.reference_id,
        },
        x0: candidate.x0,
        p0: candidate.P0,
      });
      if (sequence === validationSequence.current) setValidation(result);
    } catch (cause) {
      if (sequence === validationSequence.current)
        setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      if (sequence === validationSequence.current) setBusy(false);
    }
  }

  return (
    <div className="formula-model-editor">
      <p className="help">
        按表格填写状态和数学公式，修改会自动保存到当前配置。无需编写代码；F、H
        自动对公式求数值导数。
      </p>
      <label className="field">
        <span>模型模板</span>
        <select
          value={preset}
          onChange={(event) => setPreset(event.target.value as typeof preset)}
        >
          <option value="armor">11 维：平移、自旋与板几何</option>
          <option value="xy">4 维：平面匀速，已知姿态与几何</option>
          <option value="bias">6 维：平面匀速与测量偏置</option>
        </select>
      </label>
      <button
        type="button"
        onClick={() => update(createFormulaPreset(preset, geometry))}
      >
        使用此模板
      </button>
      <p className="help">
        载入模板会替换本模型的状态、初值、方差、方程与
        Q/R。场景和真实观测保持当前设置。
      </p>
      <p className="formula-note">
        4 / 6 维模板假定朝向固定为
        0、高度与板几何已知且不变。请让实验场景符合这些假设，否则会出现模型偏差。偏置状态没有真值映射。
      </p>
      {!persisted && (
        <p className="formula-note">
          当前显示模板预览。点击“使用此模板”或修改任一字段，即启用表单模型。
        </p>
      )}

      <details className="formula-help">
        <summary>公式变量与填写示例</summary>
        <p>
          使用状态名称和数学运算 +、-、*、/、**（乘方）；支持
          sin、cos、tan、exp、sqrt、abs、min、max 和 pi。例如位置下一时刻填写 cx
          + vx*dt，方差填写 0.01**2。
        </p>
        <p>
          dt 是本次预测间隔（秒），t0
          是当前预测起点（秒）。状态更新公式可使用状态、dt、t0 和几何量；Q
          可使用 dt 和几何量；观测公式可使用状态、板信息和几何量；R
          可使用几何量。
        </p>
        <p>
          几何量：radius_a、radius_b、height_a、height_diff、reference_id。板信息：plate_id（0–3）、plate_odd（奇数板为
          1）、plate_offset（相对参考板的角度）、plate_radius、plate_height。
        </p>
        <p>
          角度使用弧度。修改名称或删除状态后，请同步修改引用它的公式，再点击验证。状态顺序、x₀、P₀
          与 Q 会同步调整。
        </p>
      </details>

      <details open className="formula-section">
        <summary>状态向量 x · {spec.states.length} 维</summary>
        <p className="help">
          每行一个状态，按显示顺序排列。初始方差填方差，不是标准差。真值对应只用于评估与物理显示，不会读取真值作为估计初值。
        </p>
        <p className="help">
          设置真值对应时，单位须使用该物理量的原单位（m、m/s、rad、rad/s）；对状态做缩放时，请选择“无对应”。
        </p>
        <div className="formula-states">
          {spec.states.map((state, index) => (
            <div className="formula-state" key={index}>
              <div className="formula-state-toolbar">
                <span>#{index + 1}</span>
                <div>
                  <button
                    type="button"
                    aria-label={`上移状态 ${state.name || index + 1}`}
                    disabled={index === 0}
                    onClick={() => reorder(index, index - 1)}
                  >
                    ↑
                  </button>
                  <button
                    type="button"
                    aria-label={`下移状态 ${state.name || index + 1}`}
                    disabled={index === spec.states.length - 1}
                    onClick={() => reorder(index, index + 1)}
                  >
                    ↓
                  </button>
                  <button
                    type="button"
                    aria-label={`删除状态 ${state.name || index + 1}`}
                    disabled={spec.states.length <= 1}
                    onClick={() => removeState(index)}
                  >
                    删除
                  </button>
                </div>
              </div>
              <details open={index === 0}>
                <summary>
                  <strong>{state.name || "未命名状态"}</strong>
                  <span>{state.unit || "无单位"}</span>
                </summary>
                <div className="formula-state-fields">
                  <label className="field">
                    <span>名称</span>
                    <input
                      aria-label={`状态 ${index + 1} 名称`}
                      spellCheck={false}
                      value={state.name}
                      onChange={(event) =>
                        patchState(index, { name: event.target.value })
                      }
                    />
                  </label>
                  <label className="field">
                    <span>单位</span>
                    <input
                      aria-label={`状态 ${index + 1} 单位`}
                      value={state.unit}
                      onChange={(event) =>
                        patchState(index, { unit: event.target.value })
                      }
                    />
                  </label>
                  <label className="field">
                    <span>初值 x₀</span>
                    <input
                      type="number"
                      step="any"
                      aria-label={`状态 ${index + 1} 初值`}
                      value={
                        Number.isFinite(state.initial) ? state.initial : ""
                      }
                      onChange={(event) =>
                        patchState(index, {
                          initial: event.target.valueAsNumber,
                        })
                      }
                    />
                  </label>
                  <label className="field">
                    <span>初始方差 P₀</span>
                    <input
                      type="number"
                      step="any"
                      min="0"
                      aria-label={`状态 ${index + 1} 初始方差`}
                      value={
                        Number.isFinite(state.variance) ? state.variance : ""
                      }
                      onChange={(event) =>
                        patchState(index, {
                          variance: event.target.valueAsNumber,
                        })
                      }
                    />
                  </label>
                  <label className="formula-checkbox">
                    <input
                      type="checkbox"
                      aria-label={`状态 ${index + 1} 是角度`}
                      checked={state.angular}
                      onChange={(event) =>
                        patchState(index, { angular: event.target.checked })
                      }
                    />
                    角度状态（弧度）
                  </label>
                  <label className="field formula-wide">
                    <span>真值对应</span>
                    <select
                      aria-label={`状态 ${index + 1} 真值对应`}
                      value={state.truth}
                      onChange={(event) =>
                        patchState(index, { truth: event.target.value })
                      }
                    >
                      <option value="">无对应（只估计）</option>
                      {truthRoles.map((role) => (
                        <option value={role} key={role}>
                          {roleNames[role]} · {role}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label className="field formula-wide">
                    <span>下一时刻 {state.name || "此状态"} =</span>
                    <textarea
                      rows={2}
                      spellCheck={false}
                      aria-label={`状态 ${index + 1} 下一时刻公式`}
                      value={state.transition}
                      onChange={(event) =>
                        patchState(index, { transition: event.target.value })
                      }
                    />
                  </label>
                </div>
              </details>
            </div>
          ))}
        </div>
        <button
          type="button"
          disabled={spec.states.length >= 32}
          onClick={addState}
        >
          添加状态
        </button>
      </details>

      <details open className="formula-section">
        <summary>预测观测 h · 每板 4 维</summary>
        <p className="help">
          实际观测 z 仍来自场景，每板依次为 [x, y, z,
          yaw]。这里填写模型预测的观测值；多板时系统按板顺序拼接，H 自动生成。
        </p>
        {measurements.map((measurement, index) => (
          <label className="field" key={measurement}>
            <span>
              预测 {measurement} {index === 3 ? "（rad）" : "（m）"} =
            </span>
            <textarea
              rows={2}
              spellCheck={false}
              aria-label={`预测观测 ${measurement} 公式`}
              value={spec.observation[index] ?? ""}
              onChange={(event) =>
                update({
                  ...spec,
                  observation: spec.observation.map((value, i) =>
                    i === index ? event.target.value : value,
                  ),
                })
              }
            />
          </label>
        ))}
      </details>

      <details className="formula-section">
        <summary>
          过程噪声 Q(dt) · {spec.states.length} × {spec.states.length}
        </summary>
        <p className="help">
          这是一个预测间隔内的离散协方差。行列与状态顺序一致，可填写 dt
          公式。对角线为方差，非对角线为协方差；矩阵须对称且半正定。例如速度随机游走可填
          0.2*dt。
        </p>
        <FormulaMatrix
          label="Q"
          names={spec.states.map((state) => state.name)}
          value={spec.q}
          onChange={(q) => update({ ...spec, q })}
        />
      </details>
      <details className="formula-section">
        <summary>观测噪声 R · 每板 4 × 4</summary>
        <p className="help">
          行列顺序为 x、y、z、yaw。标准差 0.01 m 应填
          0.01**2。非对角项表示相关误差，矩阵须对称且正定；多板观测使用相同块且板间独立。这里修改滤波器的噪声假设，真实观测噪声在观测设置中调整。
        </p>
        <FormulaMatrix
          label="R"
          names={measurements}
          value={spec.r}
          onChange={(r) => update({ ...spec, r })}
        />
      </details>
      {issues.length > 0 && (
        <div className="field-error" role="alert">
          <p>请先修正以下配置：</p>
          <ul>
            {issues.map((issue, i) => (
              <li key={i}>{issue}</li>
            ))}
          </ul>
        </div>
      )}
      <button
        type="button"
        disabled={busy || issues.length > 0}
        onClick={() => void validate()}
      >
        {busy ? "正在验证模型…" : "验证模型"}
      </button>
      <p className="help">
        验证会检查公式、维度与协方差；F/H
        在滤波中自动计算。配置变化后请重新验证。
      </p>
      {validation && (
        <div
          role="status"
          className={validation.valid ? "validation-good" : "field-error"}
        >
          {validation.valid
            ? `验证通过 · ${validation.metadata?.state_names?.length ?? spec.states.length} 维状态`
            : validation.issues.map((issue, i) => (
                <p key={i}>
                  {issue.field ? `${issue.field}：` : ""}
                  {issue.message}
                </p>
              ))}
        </div>
      )}
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
