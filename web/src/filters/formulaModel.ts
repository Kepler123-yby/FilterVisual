import type { FilterConfig, Geometry } from "../api/types";

export interface FormulaState {
  name: string;
  unit: string;
  angular: boolean;
  initial: number;
  variance: number;
  transition: string;
  truth: string;
}

export interface FormulaSpec {
  version: 1;
  states: FormulaState[];
  observation: string[];
  q: string[][];
  r: string[][];
}

export const FORMULA_MODEL_SOURCE = `from filtervisual.models.formula import FormulaModel

def build_model(params, geometry):
    return FormulaModel(params, geometry)
`;
export const ADVANCED_FORMULA_PREFIX = "# Advanced Python model\n";

export const truthRoles = [
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
];
const roleUnits: Record<string, string> = {
  cx: "m",
  cy: "m",
  zA: "m",
  vx: "m/s",
  vy: "m/s",
  vz: "m/s",
  theta: "rad",
  omega: "rad/s",
  rA: "m",
  rB: "m",
  dh: "m",
};
const reserved = new Set([
  "dt",
  "t0",
  "pi",
  "sin",
  "cos",
  "tan",
  "exp",
  "sqrt",
  "abs",
  "min",
  "max",
  "radius_a",
  "radius_b",
  "height_a",
  "height_diff",
  "reference_id",
  "plate_id",
  "plate_odd",
  "plate_offset",
  "plate_radius",
  "plate_height",
  "False",
  "None",
  "True",
  "and",
  "as",
  "assert",
  "async",
  "await",
  "break",
  "class",
  "continue",
  "def",
  "del",
  "elif",
  "else",
  "except",
  "finally",
  "for",
  "from",
  "global",
  "if",
  "import",
  "in",
  "is",
  "lambda",
  "nonlocal",
  "not",
  "or",
  "pass",
  "raise",
  "return",
  "try",
  "while",
  "with",
  "yield",
]);

export function readFormulaSpec(filter: FilterConfig): FormulaSpec | null {
  if (filter.model.source !== FORMULA_MODEL_SOURCE) return null;
  return recoverFormulaSpec(filter);
}

export function recoverFormulaSpec(filter: FilterConfig): FormulaSpec | null {
  const candidate = filter.model.params.form_model as FormulaSpec | undefined;
  const valid =
    filter.model.kind === "custom" &&
    (filter.model.source === FORMULA_MODEL_SOURCE ||
      filter.model.source === ADVANCED_FORMULA_PREFIX + FORMULA_MODEL_SOURCE) &&
    candidate?.version === 1 &&
    Array.isArray(candidate.states) &&
    candidate.states.every(
      (state) =>
        state &&
        typeof state.name === "string" &&
        typeof state.unit === "string" &&
        typeof state.transition === "string" &&
        typeof state.truth === "string",
    ) &&
    Array.isArray(candidate.observation) &&
    candidate.observation.every((value) => typeof value === "string") &&
    Array.isArray(candidate.q) &&
    candidate.q.every(
      (row) =>
        Array.isArray(row) && row.every((value) => typeof value === "string"),
    ) &&
    Array.isArray(candidate.r) &&
    candidate.r.every(
      (row) =>
        Array.isArray(row) && row.every((value) => typeof value === "string"),
    );
  if (!valid || !candidate) return null;
  // The engine's instance initial values remain authoritative after imports or full-P edits.
  return {
    ...candidate,
    states: candidate.states.map((state, i) => ({
      ...state,
      initial: filter.x0[i] ?? state.initial,
      variance: filter.P0[i]?.[i] ?? state.variance,
    })),
  };
}

export function getFormulaIssues(spec: FormulaSpec): string[] {
  const issues: string[] = [];
  const n = spec.states.length;
  if (n < 1 || n > 32) issues.push("状态数量需要在 1–32 之间");
  const names = new Set<string>(),
    mapped = new Set<string>();
  spec.states.forEach((state, i) => {
    if (
      !/^[A-Za-z][A-Za-z0-9_]{0,63}$/.test(state.name) ||
      reserved.has(state.name)
    )
      issues.push(
        `状态 ${i + 1}：名称需以英文字母开头，最多 64 字符，且不能与公式变量重名或使用保留名称`,
      );
    if (state.unit.length > 40) issues.push(`状态 ${i + 1}：单位最多 40 字符`);
    if (names.has(state.name)) issues.push(`状态名称 ${state.name} 重复`);
    names.add(state.name);
    if (
      !Number.isFinite(state.initial) ||
      !Number.isFinite(state.variance) ||
      state.variance <= 0
    )
      issues.push(`状态 ${i + 1}：初值需有限，初始方差需大于 0`);
    if (!state.transition.trim())
      issues.push(`状态 ${i + 1}：请填写下一时刻公式`);
    if (
      state.truth &&
      (!truthRoles.includes(state.truth) || mapped.has(state.truth))
    )
      issues.push(`状态 ${i + 1}：物理量映射无效或重复`);
    if (
      state.truth &&
      roleUnits[state.truth] &&
      state.unit !== roleUnits[state.truth]
    )
      issues.push(
        `状态 ${i + 1}：${state.truth} 的单位需要为 ${roleUnits[state.truth]}`,
      );
    if (state.truth && state.angular !== (state.truth === "theta"))
      issues.push(
        `状态 ${i + 1}：只有参考板朝向 theta 是周期角度，角速度不是角度状态`,
      );
    if (state.truth) mapped.add(state.truth);
  });
  if (
    spec.observation.length !== 4 ||
    spec.observation.some((value) => !value.trim())
  )
    issues.push("请填写每板 x、y、z、yaw 的四个预测观测公式");
  for (const [label, matrix, size] of [
    ["Q", spec.q, n],
    ["R", spec.r, 4],
  ] as const) {
    if (
      matrix.length !== size ||
      matrix.some(
        (row) => row.length !== size || row.some((value) => !value.trim()),
      )
    )
      issues.push(`${label} 需要完整的 ${size} × ${size} 公式矩阵`);
  }
  return issues;
}

const zeros = (n: number) =>
  Array.from({ length: n }, () => Array<string>(n).fill("0"));
function accelerationBlock(
  q: string[][],
  position: number,
  velocity: number,
  strength: number,
) {
  q[position][position] = `${strength}*dt**3/3`;
  q[position][velocity] = q[velocity][position] = `${strength}*dt**2/2`;
  q[velocity][velocity] = `${strength}*dt`;
}

export function createFormulaPreset(
  kind: "armor" | "xy" | "bias",
  geometry: Geometry,
): FormulaSpec {
  function state(
    name: string,
    unit: string,
    initial: number,
    variance: number,
    transition = name,
  ): FormulaState {
    return {
      name,
      unit,
      initial,
      variance,
      transition,
      truth: name,
      angular: name === "theta",
    };
  }
  const states =
    kind === "armor"
      ? [
          state("cx", "m", 0, 0.04, "cx + vx*dt"),
          state("cy", "m", 0, 0.04, "cy + vy*dt"),
          state("zA", "m", geometry.zA, 0.01, "zA + vz*dt"),
          state("vx", "m/s", 0, 1),
          state("vy", "m/s", 0, 1),
          state("vz", "m/s", 0, 0.04),
          state("theta", "rad", 0, 0.25, "theta + omega*dt"),
          state("omega", "rad/s", 0, 4),
          state("rA", "m", geometry.rA, 0.01),
          state("rB", "m", geometry.rB, 0.01),
          state("dh", "m", geometry.dh, 0.0025),
        ]
      : [
          state("cx", "m", 0, 0.04, "cx + vx*dt"),
          state("cy", "m", 0, 0.04, "cy + vy*dt"),
          state("vx", "m/s", 0.5, 1),
          state("vy", "m/s", 0, 1),
          ...(kind === "bias"
            ? [
                { ...state("bx", "m", 0, 0.0001), truth: "" },
                { ...state("by", "m", 0, 0.0001), truth: "" },
              ]
            : []),
        ];
  const q = zeros(states.length);
  if (kind === "armor") {
    for (const [p, v] of [
      [0, 3],
      [1, 4],
      [2, 5],
    ])
      accelerationBlock(q, p, v, 0.5);
    accelerationBlock(q, 6, 7, 0.8);
    q[8][8] = q[9][9] = q[10][10] = "0.000001*dt";
  } else {
    accelerationBlock(q, 0, 2, 0.2);
    accelerationBlock(q, 1, 3, 0.2);
    if (kind === "bias") q[4][4] = q[5][5] = "0.000001*dt";
  }
  const r = zeros(4);
  for (let i = 0; i < 4; i++) r[i][i] = i === 3 ? "0.02**2" : "0.01**2";
  if (kind === "bias") r[0][1] = r[1][0] = "0.00006";
  const radius = "((1-plate_odd)*rA + plate_odd*rB)";
  const observation =
    kind === "armor"
      ? [
          `cx + ${radius}*cos(theta + plate_offset)`,
          `cy + ${radius}*sin(theta + plate_offset)`,
          "zA + plate_odd*dh",
          "theta + plate_offset",
        ]
      : [
          `cx + plate_radius*cos(plate_offset)${kind === "bias" ? " + bx" : ""}`,
          `cy + plate_radius*sin(plate_offset)${kind === "bias" ? " + by" : ""}`,
          "plate_height",
          "plate_offset",
        ];
  return { version: 1, states, observation, q, r };
}

export function applyFormulaSpec(
  filter: FilterConfig,
  spec: FormulaSpec,
  renamedStateIndex?: number,
): FilterConfig {
  const old = recoverFormulaSpec(filter);
  const previousNames = old?.states.map((state) => state.name) ?? [];
  const renaming =
    typeof renamedStateIndex === "number" &&
    Number.isInteger(renamedStateIndex) &&
    renamedStateIndex >= 0 &&
    renamedStateIndex < spec.states.length &&
    old?.states.length === spec.states.length;
  const P0 = spec.states.map((state, i) =>
    spec.states.map((other, j) => {
      if (i === j) return state.variance;
      // A name edit leaves row identities unchanged, including during temporarily
      // duplicate or incomplete names. Structural edits instead follow names.
      const oldI = renaming ? i : previousNames.indexOf(state.name),
        oldJ = renaming ? j : previousNames.indexOf(other.name);
      return oldI < 0 || oldJ < 0 ? 0 : (filter.P0[oldI]?.[oldJ] ?? 0);
    }),
  );
  return {
    ...filter,
    model: {
      kind: "custom",
      source: FORMULA_MODEL_SOURCE,
      params: { form_model: structuredClone(spec) },
    },
    x0: spec.states.map((state) => state.initial),
    P0,
    q_scale: filter.q_scale ?? 1,
    r_scale: filter.r_scale ?? 1,
  };
}
