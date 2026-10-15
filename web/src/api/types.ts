import type { components } from "./generated";
export interface SinTerm {
  A: number;
  frequency_rad_s: number;
  phase_rad: number;
  C: number;
}
export interface Geometry {
  rA: number;
  rB: number;
  zA: number;
  dh: number;
  reference_id: number;
}
export interface ForecastConfig {
  enabled: boolean;
  leads_s: number[];
  max_step_s: number;
}
export interface ModelView {
  kind: "builtin" | "custom";
  source?: string;
  builtin_name?: string;
  params: Record<string, unknown>;
}
export interface FilterConfig {
  id: string;
  name: string;
  kind: "ekf" | "ukf" | "imm";
  enabled?: boolean;
  frequency_hz: number;
  model: ModelView;
  x0: number[];
  P0: number[][];
  R: number[][];
  q_translation: number;
  q_rotation: number;
  q_geometry: number;
  q_scale?: number;
  r_scale?: number;
  alpha: number;
  beta: number;
  kappa: number;
  imm: {
    modes: {
      kind: "ekf" | "ukf";
      name: string;
      q_translation: number;
      q_rotation: number;
      q_geometry: number;
      q_scale?: number;
      r_scale?: number;
      params?: Record<string, unknown>;
      model?: ModelView;
      R?: number[][];
      use_parent_model?: boolean;
    }[];
    mu0: number[];
    generator: number[][];
    reference_dt: number;
  };
}
export interface ExperimentConfig {
  name: string;
  seed: number;
  duration_s: number;
  simulation_dt: number;
  evaluation_hz: number;
  animation_fps: number;
  geometry: Geometry;
  translation: {
    mode: "constant" | "random_smooth" | "segments";
    initial_xy: number[];
    velocity_xy: number[];
    speed_range: number[];
    node_interval_s?: number;
    segments: { t: number; speed: number; heading: number }[];
  };
  spin: {
    mode: "angle" | "angular_velocity";
    theta0: number;
    terms: SinTerm[];
  };
  observation: {
    frequency_hz: number;
    mode: "facing" | "fixed" | "all";
    plate_id: number;
    viewpoint: number[];
    noise_covariance: number[][];
    missing_probability: number;
    outlier_probability: number;
    outlier_scale?: number;
  };
  filters: FilterConfig[];
  forecast: ForecastConfig;
  confidence: number;
}
export interface Score {
  value: number | null;
  dof: number | null;
  bounds: [number, number] | null;
  reason: string | null;
  label: string;
  assumption?: string;
  state_names?: string[];
}
export interface Physical {
  valid?: boolean;
  center_xy: number[] | null;
  armor_positions: number[][] | null;
  reference_yaw: number | null;
  [key: string]: unknown;
}
export interface CompletePhysical extends Physical {
  center_xy: number[];
  armor_positions: number[][];
  reference_yaw: number;
}
export interface TruthPoint extends CompletePhysical {
  t: number;
  state: number[];
}
export interface Observation {
  id: string;
  t: number;
  plate_ids: number[];
  values: number[];
}
export interface Sample {
  t: number;
  x: number[];
  truth: (number | null)[];
  error: (number | null)[];
  P_diag: number[];
  physical: Physical | null;
  nees: Score;
  mode_probabilities?: number[];
}
export interface Update {
  t: number;
  innovation: number[];
  S: number[][];
  nis: Score;
}
export interface ForecastRecord {
  origin_time: number;
  lead_s: number;
  target_time: number;
  x: number[];
  physical: Physical | null;
  truth_physical: Physical | null;
  error: (number | null)[];
  physical_error: Physical | null;
  nees: Score;
  nis: Score;
  mode_probabilities?: number[];
}
export interface InstanceResult {
  id: string;
  name: string;
  kind: string;
  status: string;
  error?: string;
  state_names: string[];
  units: string[];
  angular_indices: number[];
  samples: Sample[];
  updates: Update[];
  forecasts: ForecastRecord[];
}
export interface ConsistencyGroup {
  kind?: string;
  label?: string;
  name?: string;
  count: number;
  dof?: number;
  mean?: number;
  outside_fraction?: number;
  lower_fraction?: number;
  upper_fraction?: number;
  assumption?: string;
  [key: string]: unknown;
}
export interface InstanceMetrics {
  instance_id: string;
  name: string;
  kind: string;
  status: string;
  sample_count: number;
  rmse: (number | null)[];
  position_rmse: number | null;
  angle_rmse: number | null;
  position_count?: number;
  angle_count?: number;
  forecast: {
    lead_s: number;
    position_rmse: number | null;
    armor_rmse: (number | null)[];
    count: number;
    max_error: number | null;
  }[];
  consistency: ConsistencyGroup[];
  elapsed_s: number;
  actual_update_hz: number;
  skipped_observations: number;
}
export interface Recommendation {
  instance_id: string;
  title: string;
  evidence: { interval: number[]; metric: string; value: number };
  causes: string[];
  parameter_paths: string[];
  trial_patch: Record<string, unknown>;
  hypothesis: boolean;
}
export interface Report {
  instances: InstanceMetrics[];
  recommendations: Recommendation[];
  summary: string[];
}
export interface RunPayload {
  config: ExperimentConfig;
  truth: TruthPoint[];
  observations: Observation[];
  instances: InstanceResult[];
  report: Report;
}
export type RunStatus = components["schemas"]["RunStatus"];
export type RunState = RunStatus["status"];
export interface ModelValidation {
  valid: boolean;
  issues: { message: string; line?: number; field?: string }[];
  metadata?: {
    state_names?: string[];
    units?: string[];
    angular_indices?: number[];
  };
}
export interface ScanResult {
  baseline_run_id?: string;
  candidates: {
    id?: string;
    run_id?: string;
    config?: ExperimentConfig;
    patch?: Record<string, unknown>;
    multiplier?: number;
    metric?: string;
    value?: number;
    report?: Report;
    status?: string;
  }[];
  summary?: string[];
}
export interface MonteCarloResult {
  runs?: number;
  count?: number;
  seeds?: number[];
  results?: unknown[];
  summary?: string[];
  [key: string]: unknown;
}
