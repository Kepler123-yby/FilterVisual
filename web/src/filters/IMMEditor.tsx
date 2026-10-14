import { lazy, Suspense } from "react";
import type { FilterConfig, Geometry } from "../api/types";
import { Field, NumberField, Toggle } from "../app/components";
import { MatrixEditor } from "./MatrixEditor";
import { JsonField, TransitionPreview } from "./ParameterEditor";
const ModelEditor = lazy(() => import("./ModelEditor"));
export default function IMMEditor({
  filter,
  geometry,
  onChange,
}: {
  filter: FilterConfig;
  geometry: Geometry;
  onChange: (f: FilterConfig) => void;
}) {
  const imm = filter.imm;
  function modePatch(
    index: number,
    patch: Partial<(typeof imm.modes)[number]>,
  ) {
    onChange({
      ...filter,
      imm: {
        ...imm,
        modes: imm.modes.map((m, i) => (i === index ? { ...m, ...patch } : m)),
      },
    });
  }
  function resize(count: number) {
    const modes = Array.from(
      { length: count },
      (_, i) =>
        imm.modes[i] ?? {
          kind: "ekf" as const,
          name: `模式 ${i + 1}`,
          q_translation: filter.q_translation,
          q_rotation: filter.q_rotation,
          q_geometry: filter.q_geometry,
          q_scale: 1,
          r_scale: 1,
          use_parent_model: true,
          model: structuredClone(filter.model),
          R: structuredClone(filter.R),
        },
    );
    const generator = Array.from({ length: count }, (_, i) =>
      Array.from({ length: count }, (_, j) =>
        i === j ? 0 : (imm.generator[i]?.[j] ?? 1),
      ),
    );
    generator.forEach((row, i) => {
      row[i] = -row.reduce((a, b) => a + b, 0);
    });
    const probabilities = Array.from(
        { length: count },
        (_, i) => imm.mu0[i] ?? 0.1,
      ),
      sum = probabilities.reduce((a, b) => a + b, 0);
    onChange({
      ...filter,
      imm: { ...imm, modes, generator, mu0: probabilities.map((p) => p / sum) },
    });
  }
  return (
    <details open>
      <summary>IMM 模式与转移率</summary>
      <div className="instance-actions">
        <button
          className="text-button"
          disabled={imm.modes.length >= 8}
          onClick={() => resize(imm.modes.length + 1)}
        >
          ＋ 添加模式
        </button>
        <button
          className="text-button danger"
          disabled={imm.modes.length <= 2}
          onClick={() => resize(imm.modes.length - 1)}
        >
          删除末尾模式
        </button>
      </div>
      {imm.modes.map((m, i) => {
        const own = m.model ?? filter.model;
        return (
          <div className="imm-mode" key={i}>
            <Field label={`模式 ${i + 1} 算法`}>
              <select
                value={m.kind}
                onChange={(e) =>
                  modePatch(i, { kind: e.target.value as "ekf" | "ukf" })
                }
              >
                <option value="ekf">EKF</option>
                <option value="ukf">UKF</option>
              </select>
            </Field>
            <div className="field-grid">
              <NumberField
                label={`模式 ${i + 1} Q 倍率`}
                value={m.q_scale ?? 1}
                min={0}
                onChange={(q_scale) => modePatch(i, { q_scale })}
              />
              <NumberField
                label={`模式 ${i + 1} R 倍率`}
                value={m.r_scale ?? 1}
                min={0.001}
                onChange={(r_scale) => modePatch(i, { r_scale })}
              />
            </div>
            <Toggle
              label={`模式 ${i + 1} 使用父模型方程`}
              checked={m.use_parent_model !== false}
              onChange={(use_parent_model) =>
                modePatch(i, {
                  use_parent_model,
                  model: m.model ?? structuredClone(filter.model),
                  R: m.R ?? structuredClone(filter.R),
                })
              }
            />
            {m.use_parent_model === false && (
              <>
                <Field label={`模式 ${i + 1} 模型来源`}>
                  <select
                    value={own.kind}
                    onChange={(e) =>
                      modePatch(i, {
                        model: {
                          ...own,
                          kind: e.target.value as typeof own.kind,
                        },
                      })
                    }
                  >
                    <option value="builtin">独立四板 CV</option>
                    <option value="custom">独立 Python 方程</option>
                  </select>
                </Field>
                {own.kind === "builtin" ? (
                  <>
                    <div className="field-grid">
                      <NumberField
                        label={`模式 ${i + 1} 基础平移 Q`}
                        value={m.q_translation}
                        min={0}
                        onChange={(q_translation) =>
                          modePatch(i, { q_translation })
                        }
                      />
                      <NumberField
                        label={`模式 ${i + 1} 基础自旋 Q`}
                        value={m.q_rotation}
                        min={0}
                        onChange={(q_rotation) => modePatch(i, { q_rotation })}
                      />
                      <NumberField
                        label={`模式 ${i + 1} 几何 Q`}
                        value={m.q_geometry}
                        min={0}
                        onChange={(q_geometry) => modePatch(i, { q_geometry })}
                      />
                    </div>
                    <MatrixEditor
                      label={`模式 ${i + 1} 独立 R`}
                      value={m.R ?? filter.R}
                      size={(m.R ?? filter.R).length}
                      onChange={(R) => modePatch(i, { R })}
                    />
                  </>
                ) : (
                  <Suspense fallback={<p>正在加载模式模型编辑器…</p>}>
                    <ModelEditor
                      filter={{ ...filter, model: own }}
                      geometry={geometry}
                      onChange={(next) => modePatch(i, { model: next.model })}
                    />
                  </Suspense>
                )}
              </>
            )}
          </div>
        );
      })}
      <JsonField
        label="初始模式概率 μ₀"
        value={imm.mu0}
        validate={(v) =>
          !Array.isArray(v) ||
          v.length !== imm.modes.length ||
          v.some((p) => typeof p !== "number" || p < 0) ||
          Math.abs(v.reduce((a, b) => a + b, 0) - 1) > 1e-8
            ? "概率长度须匹配模式，且非负、和为 1"
            : null
        }
        onChange={(v) =>
          onChange({ ...filter, imm: { ...imm, mu0: v as number[] } })
        }
      />
      <MatrixEditor
        label="转移生成矩阵 Λ（1/s）"
        positive={false}
        value={imm.generator}
        size={imm.modes.length}
        onChange={(generator) =>
          onChange({ ...filter, imm: { ...imm, generator } })
        }
      />
      <p className="help">
        非对角 ≥ 0、每行和为
        0。所有子模型须具有一致的状态维数、单位和角度语义；后端逐个检查。
      </p>
      {imm.modes.length === 2 && (
        <div className="transition-preview">
          <NumberField
            label="转移参考间隔（s）"
            value={imm.reference_dt}
            min={0.001}
            onChange={(reference_dt) =>
              onChange({ ...filter, imm: { ...imm, reference_dt } })
            }
          />
          <TransitionPreview rates={imm.generator} dt={imm.reference_dt} />
        </div>
      )}
    </details>
  );
}
