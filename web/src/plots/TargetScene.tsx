import { useMemo } from "react";
import type {
  ExperimentConfig,
  InstanceResult,
  Physical,
  CompletePhysical,
  RunPayload,
} from "../api/types";
import { COLORS, formatNumber } from "../app/components";
export function atOrBefore<T extends { t: number }>(
  points: T[],
  time: number,
): T | undefined {
  let lo = 0,
    hi = points.length - 1,
    result = -1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    if (points[mid].t <= time + 1e-9) {
      result = mid;
      lo = mid + 1;
    } else hi = mid - 1;
  }
  return result < 0 ? undefined : points[result];
}
const plateColors = ["#2866ad", "#008e91", "#2866ad", "#008e91"];
export function projectGeometry(config: ExperimentConfig): CompletePhysical {
  const g = config.geometry,
    theta =
      config.spin.theta0 +
      (config.spin.mode === "angle"
        ? config.spin.terms.reduce(
            (sum, t) => sum + t.A * Math.sin(t.phase_rad) + t.C,
            0,
          )
        : 0);
  return {
    center_xy: config.translation.initial_xy,
    reference_yaw: theta,
    armor_positions: [0, 1, 2, 3].map((i) => {
      const a = theta + ((i - g.reference_id) * Math.PI) / 2,
        r = i % 2 ? g.rB : g.rA;
      return [
        config.translation.initial_xy[0] + r * Math.cos(a),
        config.translation.initial_xy[1] + r * Math.sin(a),
        g.zA + (i % 2) * g.dh,
      ];
    }),
  };
}
function Structure({
  physical,
  reference,
}: {
  physical: CompletePhysical;
  reference: number;
}) {
  const maxR = Math.max(
    ...physical.armor_positions.map((p) =>
      Math.hypot(p[0] - physical.center_xy[0], p[1] - physical.center_xy[1]),
    ),
    0.1,
  );
  const scale = 63 / maxR;
  const cx = 115,
    cy = 82;
  const z0 = physical.armor_positions[0]?.[2] ?? 0,
    z1 = physical.armor_positions[1]?.[2] ?? 0,
    dz = z1 - z0;
  const zmin = Math.min(z0, z1) - 0.12,
    zmax = Math.max(z0, z1) + 0.12,
    zy = (z: number) => 130 - ((z - zmin) / (zmax - zmin)) * 90;
  return (
    <div className="structure-pair">
      <svg viewBox="0 0 230 170" role="img" aria-label="四板俯视结构">
        <path
          d="M22 82h186M115 13v136"
          stroke="#d7e0e9"
          strokeDasharray="3 3"
        />
        <text x="17" y="15" className="svg-title">
          俯视结构
        </text>
        {physical.armor_positions.map((p, i) => {
          const x = cx + (p[0] - physical.center_xy[0]) * scale,
            y = cy - (p[1] - physical.center_xy[1]) * scale,
            a = Math.atan2(
              p[1] - physical.center_xy[1],
              p[0] - physical.center_xy[0],
            );
          return (
            <g key={i}>
              <line
                x1={cx}
                y1={cy}
                x2={x}
                y2={y}
                stroke={plateColors[i]}
                strokeWidth={i === reference ? 1.8 : 0.8}
              />
              <line
                x1={x - 10 * Math.sin(a)}
                y1={y - 10 * Math.cos(a)}
                x2={x + 10 * Math.sin(a)}
                y2={y + 10 * Math.cos(a)}
                stroke={i === reference ? "#cc7626" : plateColors[i]}
                strokeWidth="5"
              />
              <text x={x + 9} y={y - 9} fill={plateColors[i]}>
                A{i}
                {i === reference ? " *" : ""}
              </text>
            </g>
          );
        })}
        <circle cx={cx} cy={cy} r="3" fill="#263e57" />
        <text x="52" y="159">
          θ = {formatNumber((physical.reference_yaw * 180) / Math.PI, 1)}°
        </text>
      </svg>
      <svg viewBox="0 0 230 170" role="img" aria-label="两组装甲板高度">
        <text x="17" y="15" className="svg-title">
          装甲板高度
        </text>
        <path d="M32 30v107h166" stroke="#d7e0e9" fill="none" />
        {[z0, z1].map((z, i) => (
          <g key={i}>
            <line
              x1="35"
              x2="188"
              y1={zy(z)}
              y2={zy(z)}
              stroke="#dce4ec"
              strokeDasharray="3 3"
            />
            <rect
              x={i ? 120 : 50}
              y={zy(z) - 3}
              width="43"
              height="6"
              rx="1"
              fill={i ? "#008e91" : "#2866ad"}
            />
            <text x={i ? 120 : 50} y={zy(z) + 18} fill="#566b80">
              {i ? "A1 / A3" : "A0 / A2"}
            </text>
          </g>
        ))}
        <path
          d={`M185 ${zy(z0)}h10M190 ${zy(z0)}v${zy(z1) - zy(z0)}M185 ${zy(z1)}h10`}
          stroke="#cc7626"
          fill="none"
        />
        <text x="193" y={(zy(z0) + zy(z1)) / 2}>
          Δh
        </text>
        <text x="34" y="159">
          zA {z0.toFixed(2)} m · Δh {dz.toFixed(2)} m
        </text>
      </svg>
    </div>
  );
}
export default function TargetScene({
  result,
  config,
  time,
  enabled,
  selectedPlate,
}: {
  result: RunPayload | null;
  config: ExperimentConfig;
  time: number;
  enabled: string[];
  selectedPlate: number;
}) {
  const bounds = useMemo(() => {
    const points =
      result?.truth.flatMap((t) => [t.center_xy, ...t.armor_positions]) ??
      projectGeometry(config).armor_positions;
    const xs = points.map((p) => p[0]),
      ys = points.map((p) => p[1]);
    const minX = Math.min(...xs),
      maxX = Math.max(...xs),
      minY = Math.min(...ys),
      maxY = Math.max(...ys);
    const span = Math.max(maxX - minX, (maxY - minY) * 2.3, 1.3),
      cx = (minX + maxX) / 2,
      cy = (minY + maxY) / 2;
    return {
      minX: cx - span * 0.6,
      maxX: cx + span * 0.6,
      minY: cy - (span * 0.6) / 2.1,
      maxY: cy + (span * 0.6) / 2.1,
    };
  }, [result, config]);
  const width = 660,
    height = 292,
    mapX = (x: number) =>
      44 + ((x - bounds.minX) / (bounds.maxX - bounds.minX)) * 572,
    mapY = (y: number) =>
      262 - ((y - bounds.minY) / (bounds.maxY - bounds.minY)) * 225;
  const truth = result ? atOrBefore(result.truth, time) : undefined;
  const p = truth ?? projectGeometry(config);
  const instances =
    result?.instances.filter((i) => enabled.includes(i.id)) ?? [];
  const pointPath = (points: (number[] | null)[]) => {
    const commands: string[] = [];
    let move = true;
    for (const point of points) {
      if (!point || !point.every(Number.isFinite)) {
        move = true;
        continue;
      }
      commands.push(
        `${move ? "M" : "L"}${mapX(point[0]).toFixed(1)},${mapY(point[1]).toFixed(1)}`,
      );
      move = false;
    }
    return commands.join(" ");
  };
  const history =
    result?.truth.filter((t) => t.t <= time).map((t) => t.center_xy) ?? [];
  const renderPhysical = (
    physical: Physical,
    stroke: string,
    label: string,
    dashed = false,
  ) => {
    if (physical.valid === false || !physical.center_xy?.every(Number.isFinite))
      return null;
    const center = physical.center_xy;
    return (
      <g>
        <circle
          cx={mapX(center[0])}
          cy={mapY(center[1])}
          r={dashed ? 3 : 4}
          fill={stroke}
        />
        {(physical.armor_positions ?? [])
          .filter((p) => p.every((n) => n != null && Number.isFinite(n)))
          .map((pos, i) => {
            const x = mapX(pos[0]),
              y = mapY(pos[1]),
              a =
                (physical.reference_yaw ?? 0) +
                ((i - config.geometry.reference_id) * Math.PI) / 2;
            return (
              <g key={i}>
                <line
                  x1={mapX(center[0])}
                  y1={mapY(center[1])}
                  x2={x}
                  y2={y}
                  stroke={stroke}
                  strokeOpacity=".45"
                  strokeDasharray={dashed ? "3 2" : undefined}
                />
                <line
                  x1={x - 6 * Math.sin(a)}
                  y1={y - 6 * Math.cos(a)}
                  x2={x + 6 * Math.sin(a)}
                  y2={y + 6 * Math.cos(a)}
                  stroke={stroke}
                  strokeWidth={i === selectedPlate ? 5 : 3}
                />
                {!dashed && (
                  <text x={x + 7} y={y - 6} fill={stroke}>
                    A{i}
                  </text>
                )}
              </g>
            );
          })}
        <title>{label}</title>
      </g>
    );
  };
  return (
    <div className="target-scene" data-testid="target-scene">
      <svg
        className="motion-svg"
        viewBox={`0 0 ${width} ${height}`}
        role="img"
        aria-label={result ? "目标与估计 XY 运动" : "四板几何预览"}
      >
        {[0, 1, 2, 3, 4].map((i) => (
          <g key={i}>
            <line
              x1={44 + i * 143}
              x2={44 + i * 143}
              y1="37"
              y2="262"
              stroke="#e3eaf1"
            />
            <line
              x1="44"
              x2="616"
              y1={37 + i * 56.25}
              y2={37 + i * 56.25}
              stroke="#e3eaf1"
            />
            <text x={44 + i * 143} y="280" textAnchor="middle">
              {(bounds.minX + ((bounds.maxX - bounds.minX) * i) / 4).toFixed(1)}
            </text>
            <text x="36" y={265 - i * 56.25} textAnchor="end">
              {(bounds.minY + ((bounds.maxY - bounds.minY) * i) / 4).toFixed(1)}
            </text>
          </g>
        ))}
        <text x="601" y="22">
          x / y（m）
        </text>
        <text x="44" y="21" className="svg-title">
          {result
            ? `真实目标 · t = ${formatNumber(truth?.t, 2)} s`
            : "几何预览 · 运行后显示真实轨迹"}
        </text>
        {result && (
          <path
            d={pointPath(result.truth.map((t) => t.center_xy))}
            stroke="#263e57"
            strokeWidth="1"
            strokeOpacity=".16"
            fill="none"
          />
        )}
        <path
          d={pointPath(history)}
          stroke="#263e57"
          strokeWidth="2.2"
          fill="none"
        />
        {instances.map((instance) => {
          const color =
              COLORS[
                (result?.instances.findIndex((i) => i.id === instance.id) ??
                  0) % COLORS.length
              ],
            sample = atOrBefore(instance.samples, time);
          return (
            <g key={instance.id}>
              <path
                d={pointPath(
                  instance.samples
                    .filter((t) => t.t <= time)
                    .map((t) =>
                      t.physical?.valid === false
                        ? null
                        : (t.physical?.center_xy ?? null),
                    ),
                )}
                stroke={color}
                strokeWidth="1.2"
                strokeDasharray="4 3"
                fill="none"
              />
              {sample?.physical &&
                renderPhysical(sample.physical, color, instance.name, true)}
              {nearestForecasts(instance, time).map(
                (record, i) =>
                  record.physical?.valid !== false &&
                  record.physical?.center_xy?.every(Number.isFinite) && (
                    <g key={i} opacity=".7">
                      <circle
                        cx={mapX(record.physical.center_xy[0])}
                        cy={mapY(record.physical.center_xy[1])}
                        r="5"
                        fill="none"
                        stroke={color}
                      />
                      <title>
                        {instance.name} 提前 {record.lead_s}s →{" "}
                        {record.target_time.toFixed(3)}s
                      </title>
                    </g>
                  ),
              )}
            </g>
          );
        })}
        {renderPhysical(p, "#263e57", "真实目标")}
      </svg>
      <div className="scene-legend">
        <span>
          <i style={{ background: "#263e57" }} />
          真值
        </span>
        {instances.map((i) => (
          <span key={i.id}>
            <i
              style={{
                background:
                  COLORS[
                    (result?.instances.findIndex((v) => v.id === i.id) ?? 0) %
                      COLORS.length
                  ],
              }}
            />
            {i.name}
          </span>
        ))}
        {instances.some((i) => i.forecasts.length) && <span>○ 附带预测</span>}
      </div>
      <Structure physical={p} reference={config.geometry.reference_id} />
    </div>
  );
}
export function nearestForecasts(instance: InstanceResult, time: number) {
  const origins = instance.forecasts.filter(
    (f) => f.origin_time <= time + 1e-9,
  );
  const last = origins.at(-1)?.origin_time;
  return last == null
    ? []
    : origins.filter((f) => Math.abs(f.origin_time - last) < 1e-8);
}
