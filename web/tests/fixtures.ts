import type { WireConfig } from "../src/api/adapter";
import type { RunPayload, RunStatus, Score } from "../src/api/types";
import { fromWireConfig } from "../src/api/adapter";
import { diagonalMatrix } from "../src/filters/MatrixEditor";
export function wireFixture(): WireConfig {
  const p0 = diagonalMatrix([
    0.04, 0.04, 0.01, 1, 1, 0.04, 0.25, 4, 0.01, 0.01, 0.0025,
  ]);
  return {
    schema_version: 1,
    name: "四装甲板平移与自旋",
    seed: 42,
    scene: {
      duration_s: 12,
      simulation_dt: 0.002,
      geometry: {
        radius_a: 0.25,
        radius_b: 0.35,
        height_a: 0.2,
        height_diff: 0.08,
        reference_id: 0,
      },
      translation: {
        mode: "random_smooth",
        initial_xy: [0, 0],
        velocity_xy: [0.5, 0],
        speed_min: 0.5,
        speed_max: 2,
        node_interval_s: 1,
        waypoints: [],
      },
      rotation: {
        mode: "angular_velocity",
        initial_yaw: 0,
        terms: [
          { amplitude: 1, frequency_rad_s: 1.2, phase_rad: 0, offset: 2 },
        ],
      },
    },
    observation: {
      frequency_hz: 100,
      mode: "nearest_visible",
      plate_id: 0,
      viewpoint_xyz: [-3, 0, 0.2],
      std_xyz: 0.01,
      std_yaw: 0.02,
      covariance: null,
      dropout_probability: 0,
      outlier_probability: 0,
      outlier_scale: 10,
    },
    models: [
      {
        id: "rm-cv",
        kind: "builtin",
        builtin_name: "rm_cv",
        source: null,
        params: {},
      },
    ],
    instances: ["ekf", "ukf", "imm"].map((kind, index) => ({
      id: `${kind}-01`,
      name: `${kind.toUpperCase()} 01`,
      kind: kind as "ekf" | "ukf" | "imm",
      enabled: true,
      model_id: "rm-cv",
      frequency_hz: 50,
      x0: [0, 0, 0.2, 0, 0, 0, 0, 0, 0.2, 0.2, 0],
      p0,
      q_scale: 1,
      r_scale: 1,
      ukf: { alpha: 0.5, beta: 2, kappa: 0 },
      imm: {
        models: [
          { model_id: "rm-cv", kind: "ekf", q_scale: 0.2, r_scale: 1 },
          { model_id: "rm-cv", kind: "ukf", q_scale: 4, r_scale: 1 },
        ],
        probabilities: [0.5, 0.5],
        generator: [
          [-1, 1],
          [1, -1],
        ],
      },
    })),
    forecast: { enabled: true, leads_s: [0.1, 0.3, 0.5], max_step_s: 0.005 },
    evaluation: { frequency_hz: 50, confidence: 0.95, monte_carlo_trials: 20 },
  };
}
export const statusFixture: RunStatus = {
  id: "fixture-run",
  status: "completed",
  kind: "simulation",
  name: "",
  timeout_s: 120,
  progress: 1,
  stage: "完成",
  created_at: "2026-10-15T00:00:00Z",
};
const score: Score = {
  value: 2,
  dof: 11,
  bounds: [3, 23],
  reason: null,
  label: "卡方参考区间",
};
export function resultFixture(): RunPayload {
  const config = fromWireConfig(wireFixture());
  const physical = {
    center_xy: [0, 0],
    reference_yaw: 0,
    armor_positions: [
      [0.25, 0, 0.2],
      [0, 0.35, 0.28],
      [-0.25, 0, 0.2],
      [0, -0.35, 0.28],
    ],
  };
  return {
    config,
    truth: [
      {
        t: 0,
        ...physical,
        state: [0, 0, 0.2, 0, 0, 0, 0, 0, 0.25, 0.35, 0.08],
      },
    ],
    observations: [],
    instances: config.filters.map((f) => ({
      id: f.id,
      name: f.name,
      kind: f.kind,
      status: "completed",
      state_names: [
        "cx",
        "cy",
        "zA",
        "vx",
        "vy",
        "vz",
        "theta",
        "omega",
        "rA",
        "rB",
        "dh",
      ],
      units: [
        "m",
        "m",
        "m",
        "m/s",
        "m/s",
        "m/s",
        "rad",
        "rad/s",
        "m",
        "m",
        "m",
      ],
      angular_indices: [6],
      samples: [
        {
          t: 0,
          x: f.x0,
          truth: f.x0,
          error: Array(11).fill(0),
          P_diag: Array(11).fill(0.01),
          physical,
          nees: score,
        },
      ],
      updates: [],
      forecasts: [
        {
          origin_time: 4.8,
          lead_s: 0.3,
          target_time: 5.1,
          x: f.x0,
          physical,
          truth_physical: physical,
          error: Array(11).fill(0),
          physical_error: physical,
          nees: score,
          nis: {
            ...score,
            value: null,
            dof: null,
            bounds: null,
            reason: "no_new_observation",
          },
        },
      ],
    })),
    report: {
      instances: [],
      recommendations: [],
      summary: ["来自真实接口格式的解析测试样本"],
    },
  };
}
