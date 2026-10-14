import type { ExperimentConfig } from "../api/types";
import { Field, NumberField, Section } from "../app/components";
import { degreeToRadian, radianToDegree } from "./validation";
export default function SceneEditor({
  config,
  onChange,
}: {
  config: ExperimentConfig;
  onChange: (next: ExperimentConfig) => void;
}) {
  const patch = <K extends keyof ExperimentConfig>(
    key: K,
    value: Partial<ExperimentConfig[K]>,
  ) => onChange({ ...config, [key]: { ...(config[key] as object), ...value } });
  const g = config.geometry,
    tr = config.translation,
    spin = config.spin;
  return (
    <>
      <Section title="四装甲板几何" subtitle="两半径 / 两高度" initiallyOpen>
        <div className="field-grid">
          <NumberField
            label="A 组半径（m）"
            value={g.rA}
            min={0.001}
            step={0.01}
            onChange={(rA) => patch("geometry", { rA })}
          />
          <NumberField
            label="B 组半径（m）"
            value={g.rB}
            min={0.001}
            step={0.01}
            onChange={(rB) => patch("geometry", { rB })}
          />
          <NumberField
            label="A 组高度（m）"
            value={g.zA}
            step={0.01}
            onChange={(zA) => patch("geometry", { zA })}
          />
          <NumberField
            label="高度差 Δh（m）"
            value={g.dh}
            step={0.01}
            onChange={(dh) => patch("geometry", { dh })}
          />
        </div>
        <Field label="自旋参考板">
          <select
            value={g.reference_id}
            onChange={(e) =>
              patch("geometry", { reference_id: Number(e.target.value) })
            }
          >
            {[0, 1, 2, 3].map((i) => (
              <option key={i} value={i}>
                A{i} · {i % 2 === 0 ? "A" : "B"} 组
              </option>
            ))}
          </select>
        </Field>
        <p className="help">
          A0/A2 等距等高，A1/A3 等距等高。θ 从世界 +X 指向参考板。
        </p>
      </Section>
      <Section title="XY 平移" subtitle="运动真值" initiallyOpen>
        <Field label="平移方式">
          <select
            value={tr.mode}
            onChange={(e) =>
              patch("translation", { mode: e.target.value as typeof tr.mode })
            }
          >
            <option value="random_smooth">范围内平滑变速</option>
            <option value="constant">匀速</option>
            <option value="segments">速度 / 方向节点</option>
          </select>
        </Field>
        <div className="field-grid">
          {[0, 1].map((i) => (
            <NumberField
              key={i}
              label={`初始 ${i ? "Y" : "X"}（m）`}
              value={tr.initial_xy[i]}
              onChange={(n) =>
                patch("translation", {
                  initial_xy: tr.initial_xy.map((v, j) => (i === j ? n : v)),
                })
              }
            />
          ))}
        </div>
        {tr.mode === "constant" ? (
          <div className="field-grid">
            {[0, 1].map((i) => (
              <NumberField
                key={i}
                label={`速度 v${i ? "y" : "x"}（m/s）`}
                value={tr.velocity_xy[i]}
                onChange={(n) =>
                  patch("translation", {
                    velocity_xy: tr.velocity_xy.map((v, j) =>
                      i === j ? n : v,
                    ),
                  })
                }
              />
            ))}
          </div>
        ) : (
          <div className="field-grid">
            {[0, 1].map((i) => (
              <NumberField
                key={i}
                label={i ? "速度上限（m/s）" : "速度下限（m/s）"}
                value={tr.speed_range[i]}
                min={0}
                onChange={(n) =>
                  patch("translation", {
                    speed_range: tr.speed_range.map((v, j) =>
                      i === j ? n : v,
                    ),
                  })
                }
              />
            ))}
          </div>
        )}
        {tr.mode === "segments" && (
          <>
            <p className="help">
              时间节点之间平滑过渡，方向为世界 +X 逆时针角。
            </p>
            {tr.segments.map((node, i) => (
              <div className="term-row" key={i}>
                <NumberField
                  label="时刻（s）"
                  value={node.t}
                  onChange={(t) =>
                    patch("translation", {
                      segments: tr.segments.map((v, j) =>
                        i === j ? { ...v, t } : v,
                      ),
                    })
                  }
                />
                <NumberField
                  label="速度（m/s）"
                  value={node.speed}
                  onChange={(speed) =>
                    patch("translation", {
                      segments: tr.segments.map((v, j) =>
                        i === j ? { ...v, speed } : v,
                      ),
                    })
                  }
                />
                <NumberField
                  label="方向（°）"
                  value={radianToDegree(node.heading)}
                  onChange={(n) =>
                    patch("translation", {
                      segments: tr.segments.map((v, j) =>
                        i === j ? { ...v, heading: degreeToRadian(n) } : v,
                      ),
                    })
                  }
                />
                <button
                  aria-label={`删除节点 ${i + 1}`}
                  onClick={() =>
                    patch("translation", {
                      segments: tr.segments.filter((_, j) => i !== j),
                    })
                  }
                >
                  ×
                </button>
              </div>
            ))}
            <button
              className="text-button"
              onClick={() =>
                patch("translation", {
                  segments: [
                    ...tr.segments,
                    {
                      t: (tr.segments.at(-1)?.t ?? 0) + 1,
                      speed: 1,
                      heading: 0,
                    },
                  ],
                })
              }
            >
              ＋ 添加节点
            </button>
          </>
        )}
      </Section>
      <Section
        title="自旋组合"
        subtitle="Σ [ A sin(Ωt + a) + C ]"
        initiallyOpen
      >
        <Field label="正弦定义">
          <select
            value={spin.mode}
            onChange={(e) =>
              patch("spin", { mode: e.target.value as typeof spin.mode })
            }
          >
            <option value="angular_velocity">角速度 ω(t)（rad/s）</option>
            <option value="angle">参考角 θ(t)（rad）</option>
          </select>
        </Field>
        <NumberField
          label={spin.mode === "angle" ? "参考角偏置（°）" : "初始参考角（°）"}
          value={radianToDegree(spin.theta0)}
          onChange={(n) => patch("spin", { theta0: degreeToRadian(n) })}
        />
        <div className="sine-head">
          <span>A</span>
          <span>Ω（rad/s）</span>
          <span>a（rad）</span>
          <span>C</span>
          <span />
        </div>
        {spin.terms.map((term, i) => (
          <div className="sine-row" key={i}>
            {(["A", "frequency_rad_s", "phase_rad", "C"] as const).map(
              (key, j) => (
                <input
                  key={key}
                  aria-label={`正弦项 ${i + 1} ${["A", "Ω", "a", "C"][j]}`}
                  type="number"
                  step="any"
                  value={term[key]}
                  onChange={(e) =>
                    patch("spin", {
                      terms: spin.terms.map((v, k) =>
                        k === i ? { ...v, [key]: Number(e.target.value) } : v,
                      ),
                    })
                  }
                />
              ),
            )}
            <button
              aria-label={`删除正弦项 ${i + 1}`}
              onClick={() =>
                patch("spin", { terms: spin.terms.filter((_, j) => i !== j) })
              }
            >
              ×
            </button>
          </div>
        ))}
        <button
          className="text-button"
          onClick={() =>
            patch("spin", {
              terms: [
                ...spin.terms,
                { A: 0.2, frequency_rad_s: 1, phase_rad: 0, C: 0 },
              ],
            })
          }
        >
          ＋ 添加正弦项
        </button>
      </Section>
      <Section title="仿真与复现" subtitle={`seed ${config.seed}`}>
        <div className="field-grid">
          <NumberField
            label="仿真时长（s）"
            value={config.duration_s}
            min={0.1}
            max={120}
            onChange={(duration_s) => onChange({ ...config, duration_s })}
          />
          <NumberField
            label="真值最大步长（s）"
            value={config.simulation_dt}
            min={0.0001}
            onChange={(simulation_dt) => onChange({ ...config, simulation_dt })}
          />
          <NumberField
            label="共同评估频率（Hz）"
            value={config.evaluation_hz}
            min={1}
            onChange={(evaluation_hz) => onChange({ ...config, evaluation_hz })}
          />
          <NumberField
            label="随机种子"
            value={config.seed}
            min={0}
            step={1}
            onChange={(seed) => onChange({ ...config, seed })}
          />
        </div>
        <p className="help">
          各实例共享同一观测流；回放速度和帧率独立于数值计算。
        </p>
      </Section>
    </>
  );
}
