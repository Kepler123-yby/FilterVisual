import { expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import StatePlot, { makeStateTraces } from "../src/plots/StatePlot";
import { resultFixture, wireFixture } from "./fixtures";
import { fromWireConfig } from "../src/api/adapter";
vi.mock("../src/plots/Plot", () => ({ Plot: () => <div>plot</div> }));
it("uses explicit mapped truth even when custom cx is measured in cm", () => {
  const r = resultFixture(),
    i = r.instances[0];
  i.units[0] = "cm";
  i.samples[0].truth[0] = 123;
  const data = makeStateTraces(r, [i], "cx");
  expect((data[0] as { y: number[] }).y).toEqual([123]);
});
it("does not invent a canonical truth curve for an unmapped cx state", () => {
  const r = resultFixture(),
    i = r.instances[0];
  i.samples[0].truth[0] = null;
  const data = makeStateTraces(r, [i], "cx");
  expect(data.some((d) => d.name === "真值")).toBe(false);
});
it("filters different units in an overlay and points to parallel comparison", () => {
  const r = resultFixture();
  r.instances[1].units[0] = "cm";
  render(
    <StatePlot
      result={r}
      state="cx"
      enabled={r.instances.map((i) => i.id)}
      time={0}
      onTimeChange={() => {}}
    />,
  );
  expect(screen.getByText(/状态单位不同/)).toBeVisible();
});
it("refuses unknown model references on import", () => {
  const w = wireFixture();
  w.instances[0].model_id = "missing";
  expect(() => fromWireConfig(w)).toThrow(/模型引用不存在/);
});
