import type { ExperimentConfig, ModelView, RunPayload } from "./types";
import type { components } from "./generated";
type DeepRequired<T> = T extends (infer Item)[]
  ? DeepRequired<Item>[]
  : T extends object
    ? { [K in keyof T]-?: DeepRequired<T[K]> }
    : T;
// Pydantic always returns defaulted fields. These are the generated schemas with
// response fields required, rather than a second independently named API shape.
export type WireModel = DeepRequired<components["schemas"]["ModelDefinition"]>;
export type WireConfig = DeepRequired<
  components["schemas"]["ExperimentConfig"]
>;
export function covariance(position = 0.01, yaw = 0.02) {
  return [position ** 2, position ** 2, position ** 2, yaw ** 2].map((v, i) =>
    [0, 1, 2, 3].map((j) => (i === j ? v : 0)),
  );
}
export function fromWireConfig(wire: WireConfig): ExperimentConfig {
  const g = wire.scene.geometry,
    tr = wire.scene.translation,
    r = wire.scene.rotation,
    o = wire.observation;
  const modelById = (id: string) => {
    const model = wire.models.find((m) => m.id === id);
    if (!model) throw new Error(`模型引用不存在：${id}`);
    return model;
  };
  return {
    name: wire.name,
    seed: wire.seed,
    duration_s: wire.scene.duration_s,
    simulation_dt: wire.scene.simulation_dt,
    evaluation_hz: wire.evaluation.frequency_hz,
    animation_fps: 15,
    confidence: wire.evaluation.confidence,
    geometry: {
      rA: g.radius_a,
      rB: g.radius_b,
      zA: g.height_a,
      dh: g.height_diff,
      reference_id: g.reference_id,
    },
    translation: {
      mode: tr.mode === "waypoints" ? "segments" : tr.mode,
      initial_xy: tr.initial_xy,
      velocity_xy: tr.velocity_xy,
      speed_range: [tr.speed_min, tr.speed_max],
      segments: tr.waypoints.map((p) => ({
        t: p.time_s,
        speed: p.speed,
        heading: p.heading_rad,
      })),
      node_interval_s: tr.node_interval_s,
    },
    spin: {
      mode: r.mode,
      theta0: r.initial_yaw,
      terms: r.terms.map((t) => ({
        A: t.amplitude,
        frequency_rad_s: t.frequency_rad_s,
        phase_rad: t.phase_rad,
        C: t.offset,
      })),
    },
    observation: {
      frequency_hz: o.frequency_hz,
      mode: o.mode === "nearest_visible" ? "facing" : o.mode,
      plate_id: o.plate_id,
      viewpoint: o.viewpoint_xyz,
      noise_covariance: o.covariance ?? covariance(o.std_xyz, o.std_yaw),
      missing_probability: o.dropout_probability,
      outlier_probability: o.outlier_probability,
      outlier_scale: o.outlier_scale,
    },
    forecast: wire.forecast,
    filters: wire.instances.map((f) => {
      const model = modelById(f.model_id),
        p = model.params;
      return {
        id: f.id,
        name: f.name,
        kind: f.kind,
        enabled: f.enabled,
        q_scale: f.q_scale,
        r_scale: f.r_scale,
        frequency_hz: f.frequency_hz,
        x0: f.x0,
        P0: f.p0,
        q_translation:
          Number(p.q_translation ?? 0.5) * (f.kind === "imm" ? 1 : f.q_scale),
        q_rotation:
          Number(p.q_rotation ?? 0.8) * (f.kind === "imm" ? 1 : f.q_scale),
        q_geometry:
          Number(p.q_geometry ?? 1e-6) * (f.kind === "imm" ? 1 : f.q_scale),
        R: (
          (p.observation_covariance as number[][]) ??
          covariance(
            Number(p.measurement_position_std ?? 0.01),
            Number(p.measurement_yaw_std ?? 0.02),
          )
        ).map((row) => row.map((v) => v * (f.kind === "imm" ? 1 : f.r_scale))),
        alpha: f.ukf.alpha,
        beta: f.ukf.beta,
        kappa: f.ukf.kappa,
        model: {
          kind: model.kind === "python" ? "custom" : "builtin",
          source: model.source ?? undefined,
          builtin_name: model.builtin_name ?? undefined,
          params: model.params,
        },
        imm: {
          modes: f.imm.models.map((m, i) => {
            const own = modelById(m.model_id);
            const p = own.params;
            return {
              kind: m.kind,
              name: `模式 ${i + 1}`,
              q_translation: Number(p.q_translation ?? 0.5),
              q_rotation: Number(p.q_rotation ?? 0.8),
              q_geometry: Number(p.q_geometry ?? 1e-6),
              q_scale: m.q_scale,
              r_scale: m.r_scale,
              params: own.params,
              model: {
                kind: own.kind === "python" ? "custom" : "builtin",
                source: own.source ?? undefined,
                builtin_name: own.builtin_name ?? undefined,
                params: own.params,
              },
              use_parent_model: m.model_id === f.model_id,
              R:
                (own.params.observation_covariance as number[][]) ??
                covariance(
                  Number(own.params.measurement_position_std ?? 0.01),
                  Number(own.params.measurement_yaw_std ?? 0.02),
                ),
            };
          }),
          mu0: f.imm.probabilities,
          generator: f.imm.generator,
          reference_dt: 1 / f.frequency_hz,
        },
      };
    }),
  };
}
export function toWireConfig(config: ExperimentConfig): WireConfig {
  const g = config.geometry,
    tr = config.translation,
    r = config.spin,
    o = config.observation,
    models: WireModel[] = [];
  function addModel(
    id: string,
    model: ModelView,
    params: Record<string, unknown>,
  ): string {
    models.push({
      id,
      kind: model.kind === "custom" ? "python" : "builtin",
      builtin_name:
        model.kind === "custom" ? null : (model.builtin_name ?? "rm_cv"),
      source: model.source ?? null,
      params,
    });
    return id;
  }
  const instances = config.filters.map((f) => {
    const params =
      f.model.kind === "custom"
        ? f.model.params
        : {
            ...f.model.params,
            q_translation: f.q_translation,
            q_rotation: f.q_rotation,
            q_geometry: f.q_geometry,
            observation_covariance: f.R,
          };
    const model_id = addModel(`model-${f.id}`, f.model, params);
    const modes = f.imm.modes.map((m, i) => {
      const own = m.model ?? f.model;
      return {
        model_id:
          m.use_parent_model !== false
            ? model_id
            : addModel(
                `model-${f.id}-mode-${i}`,
                own,
                own.kind === "custom"
                  ? own.params
                  : {
                      ...own.params,
                      q_translation: m.q_translation,
                      q_rotation: m.q_rotation,
                      q_geometry: m.q_geometry,
                      observation_covariance: m.R ?? f.R,
                    },
              ),
        kind: m.kind,
        q_scale: m.q_scale ?? 1,
        r_scale: m.r_scale ?? 1,
      };
    });
    return {
      id: f.id,
      name: f.name,
      kind: f.kind,
      enabled: f.enabled ?? true,
      model_id,
      frequency_hz: f.frequency_hz,
      x0: f.x0,
      p0: f.P0,
      q_scale:
        f.kind === "imm" || f.model.kind === "custom" ? (f.q_scale ?? 1) : 1,
      r_scale:
        f.kind === "imm" || f.model.kind === "custom" ? (f.r_scale ?? 1) : 1,
      ukf: { alpha: f.alpha, beta: f.beta, kappa: f.kappa },
      imm: {
        models: modes,
        probabilities: f.imm.mu0,
        generator: f.imm.generator,
      },
    };
  });
  return {
    schema_version: 1,
    name: config.name,
    seed: config.seed,
    scene: {
      duration_s: config.duration_s,
      simulation_dt: config.simulation_dt,
      geometry: {
        radius_a: g.rA,
        radius_b: g.rB,
        height_a: g.zA,
        height_diff: g.dh,
        reference_id: g.reference_id,
      },
      translation: {
        mode: tr.mode === "segments" ? "waypoints" : tr.mode,
        initial_xy: tr.initial_xy,
        velocity_xy: tr.velocity_xy,
        speed_min: tr.speed_range[0],
        speed_max: tr.speed_range[1],
        node_interval_s: tr.node_interval_s ?? 1,
        waypoints: tr.segments.map((n) => ({
          time_s: n.t,
          speed: n.speed,
          heading_rad: n.heading,
        })),
      },
      rotation: {
        mode: r.mode,
        initial_yaw: r.theta0,
        terms: r.terms.map((t) => ({
          amplitude: t.A,
          frequency_rad_s: t.frequency_rad_s,
          phase_rad: t.phase_rad,
          offset: t.C,
        })),
      },
    },
    observation: {
      frequency_hz: o.frequency_hz,
      mode: o.mode === "facing" ? "nearest_visible" : o.mode,
      plate_id: o.plate_id,
      viewpoint_xyz: o.viewpoint,
      std_xyz: 0.01,
      std_yaw: 0.02,
      covariance: o.noise_covariance,
      dropout_probability: o.missing_probability,
      outlier_probability: o.outlier_probability,
      outlier_scale: o.outlier_scale ?? 10,
    },
    models,
    instances,
    forecast: config.forecast,
    evaluation: {
      frequency_hz: config.evaluation_hz,
      confidence: config.confidence,
      monte_carlo_trials: 20,
    },
  };
}
export type WirePayload = Omit<RunPayload, "config"> & { config: WireConfig };
export function fromWirePayload(payload: WirePayload): RunPayload {
  return { ...payload, config: fromWireConfig(payload.config) };
}
