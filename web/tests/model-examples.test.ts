import { expect, it } from "vitest";
import fourState from "../../examples/custom-xy.json";
import sixState from "../../examples/custom-xy-bias.json";
import { readExperimentJson } from "../src/experiments/ConfigFiles";
import { toWireConfig } from "../src/api/adapter";

it.each([
  { name: "four-state CV", config: fourState, dimension: 4 },
  { name: "six-state measurement bias", config: sixState, dimension: 6 },
])("imports and exports the documented $name example", ({ config, dimension }) => {
  const draft = readExperimentJson(JSON.stringify(config));
  expect(draft.filters).toHaveLength(2);
  for (const filter of draft.filters) {
    expect(filter.model.kind).toBe("custom");
    expect(filter.x0).toHaveLength(dimension);
    expect(filter.P0).toHaveLength(dimension);
    expect(filter.model.source).toBe(config.models[0].source);
    expect(filter.model.params).toEqual(config.models[0].params);
  }
  const exported = toWireConfig(draft);
  const modelIds = new Set(exported.models.map((model) => model.id));
  for (const filter of exported.instances) {
    expect(modelIds.has(filter.model_id)).toBe(true);
    for (const mode of filter.imm.models) {
      expect(modelIds.has(mode.model_id)).toBe(true);
    }
  }
  expect(() => readExperimentJson(JSON.stringify(exported))).not.toThrow();
});
