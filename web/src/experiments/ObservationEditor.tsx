import type { ExperimentConfig } from "../api/types";
import { Field, NumberField, Section } from "../app/components";
import { MatrixEditor } from "../filters/MatrixEditor";
export default function ObservationEditor({
  config,
  onChange,
}: {
  config: ExperimentConfig;
  onChange: (config: ExperimentConfig) => void;
}) {
  const o = config.observation;
  const patch = (value: Partial<typeof o>) =>
    onChange({ ...config, observation: { ...o, ...value } });
  return (
    <Section title="观测与真实噪声" subtitle={`${o.frequency_hz} Hz`}>
      <Field label="观测装甲板">
        <select
          value={o.mode}
          onChange={(e) => patch({ mode: e.target.value as typeof o.mode })}
        >
          <option value="facing">朝向视点的单板</option>
          <option value="fixed">指定单板</option>
          <option value="all">全部四板</option>
        </select>
      </Field>
      {o.mode === "fixed" && (
        <Field label="指定板编号">
          <select
            value={o.plate_id}
            onChange={(e) => patch({ plate_id: Number(e.target.value) })}
          >
            {[0, 1, 2, 3].map((i) => (
              <option key={i} value={i}>
                A{i}
              </option>
            ))}
          </select>
        </Field>
      )}
      <NumberField
        label="观测频率（Hz）"
        value={o.frequency_hz}
        min={0.1}
        onChange={(frequency_hz) => patch({ frequency_hz })}
      />
      {o.mode === "facing" && (
        <div className="field-grid three">
          {["X", "Y", "Z"].map((axis, i) => (
            <NumberField
              key={axis}
              label={`视点 ${axis}（m）`}
              value={o.viewpoint[i]}
              onChange={(n) =>
                patch({
                  viewpoint: o.viewpoint.map((v, j) => (i === j ? n : v)),
                })
              }
            />
          ))}
        </div>
      )}
      <MatrixEditor
        label="真实观测协方差"
        value={o.noise_covariance}
        size={o.noise_covariance.length}
        onChange={(noise_covariance) => patch({ noise_covariance })}
        hint="每板 [x,y,z,yaw] 的方差；位置 m²，角度 rad²"
      />
      <div className="field-grid">
        <NumberField
          label="缺测概率"
          value={o.missing_probability}
          min={0}
          max={1}
          step={0.01}
          onChange={(missing_probability) => patch({ missing_probability })}
        />
        <NumberField
          label="异常观测概率"
          value={o.outlier_probability}
          min={0}
          max={1}
          step={0.01}
          onChange={(outlier_probability) => patch({ outlier_probability })}
        />
      </div>
      <p className="help">
        这里设置生成观测的真实噪声。滤波器假设的 R 在右侧独立设置。
      </p>
    </Section>
  );
}
