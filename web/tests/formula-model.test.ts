import { expect, it } from "vitest";
import { fromWireConfig, toWireConfig } from "../src/api/adapter";
import { validateDraft } from "../src/experiments/validation";
import { wireFixture } from "./fixtures";
import {
  ADVANCED_FORMULA_PREFIX,
  applyFormulaSpec,
  createFormulaPreset,
  FORMULA_MODEL_SOURCE,
  getFormulaIssues,
  readFormulaSpec,
  recoverFormulaSpec,
} from "../src/filters/formulaModel";

it.each(["armor", "xy", "bias"] as const)(
  "round-trips the %s form through export/import",
  (kind) => {
    const draft = fromWireConfig(wireFixture());
    const spec = createFormulaPreset(kind, draft.geometry);
    expect(getFormulaIssues(spec)).toEqual([]);
    draft.filters[0] = applyFormulaSpec(draft.filters[0], spec);
    const imported = fromWireConfig(toWireConfig(draft));
    expect(readFormulaSpec(imported.filters[0])).toEqual(spec);
    expect(imported.filters[0].x0).toEqual(
      spec.states.map((state) => state.initial),
    );
    expect(validateDraft(imported)).toEqual([]);
  },
);

it("keeps named covariance and initial values aligned after reordering states", () => {
  const draft = fromWireConfig(wireFixture());
  const spec = createFormulaPreset("xy", draft.geometry);
  const filter = applyFormulaSpec(draft.filters[0], spec);
  filter.P0[0][2] = filter.P0[2][0] = 0.01;
  filter.x0[0] = 0.3;
  const current = readFormulaSpec(filter)!;
  const order = [2, 0, 1, 3];
  const next = applyFormulaSpec(filter, {
    ...current,
    states: order.map((i) => current.states[i]),
    q: order.map((i) => order.map((j) => current.q[i][j])),
  });
  expect(next.x0).toEqual([0.5, 0.3, 0, 0]);
  expect(next.P0[0][1]).toBe(0.01);
  expect(next.P0[1][0]).toBe(0.01);
  expect(next.P0[0][0]).toBe(1);
});

it("prevents invalid state identifiers, units and initial variance from being run", () => {
  const draft = fromWireConfig(wireFixture());
  const spec = createFormulaPreset("xy", draft.geometry);
  spec.states[0].name = "dt";
  spec.states[0].unit = "cm";
  spec.states[0].variance = -1;
  draft.filters[0] = applyFormulaSpec(draft.filters[0], spec);
  expect(validateDraft(draft).join(" ")).toMatch(/名称/);
  expect(validateDraft(draft).join(" ")).toMatch(/单位/);
  expect(validateDraft(draft).join(" ")).toMatch(/初始方差/);
});

it("preserves all initial covariance entries while a state is renamed", () => {
  const draft = fromWireConfig(wireFixture());
  const filter = applyFormulaSpec(
    draft.filters[0],
    createFormulaPreset("xy", draft.geometry),
  );
  filter.P0[0][1] = filter.P0[1][0] = 0.005;
  filter.P0[0][2] = filter.P0[2][0] = 0.01;
  filter.P0[1][3] = filter.P0[3][1] = 0.02;
  filter.x0[0] = 0.3;
  const spec = readFormulaSpec(filter)!;
  // Typing can briefly duplicate another row's name before producing a new one.
  spec.states[0].name = "cy";
  const duplicate = applyFormulaSpec(filter, spec, 0);
  const renamedSpec = readFormulaSpec(duplicate)!;
  renamedSpec.states[0].name = "position_x";
  const renamed = applyFormulaSpec(duplicate, renamedSpec, 0);
  expect(duplicate.P0).toEqual(filter.P0);
  expect(renamed.P0).toEqual(filter.P0);
  expect(renamed.x0).toEqual(filter.x0);
});

it("recovers unchanged formula code from advanced mode without changing its state or covariance", () => {
  const draft = fromWireConfig(wireFixture());
  const filter = applyFormulaSpec(
    draft.filters[0],
    createFormulaPreset("bias", draft.geometry),
  );
  filter.P0[0][2] = filter.P0[2][0] = 0.01;
  filter.x0[0] = 0.8;
  const advanced = {
    ...filter,
    model: {
      ...filter.model,
      source: ADVANCED_FORMULA_PREFIX + FORMULA_MODEL_SOURCE,
    },
  };
  expect(readFormulaSpec(advanced)).toBeNull();
  expect(recoverFormulaSpec(advanced)).toEqual(readFormulaSpec(filter));
  const restored = applyFormulaSpec(advanced, recoverFormulaSpec(advanced)!);
  expect(restored.x0).toEqual(filter.x0);
  expect(restored.P0).toEqual(filter.P0);
  expect(restored.model.source).toBe(FORMULA_MODEL_SOURCE);
  expect(readFormulaSpec(restored)?.states).toHaveLength(6);
});

it.each([
  FORMULA_MODEL_SOURCE + "\n# a user edit",
  ADVANCED_FORMULA_PREFIX + FORMULA_MODEL_SOURCE + "\n# a user edit",
  FORMULA_MODEL_SOURCE.replace(
    "FormulaModel(params, geometry)",
    "FormulaModel({}, geometry)",
  ),
])("does not recover modified Python source: %s", (source) => {
  const draft = fromWireConfig(wireFixture());
  const filter = applyFormulaSpec(
    draft.filters[0],
    createFormulaPreset("xy", draft.geometry),
  );
  filter.model.source = source;
  expect(readFormulaSpec(filter)).toBeNull();
  expect(recoverFormulaSpec(filter)).toBeNull();
});
