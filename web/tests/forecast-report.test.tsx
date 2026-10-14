import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import {
  ForecastTimeLabel,
  forecastDifference,
} from "../src/forecast/ForecastPlot";
import { resizeLeads } from "../src/forecast/ForecastEditor";
import { resultFixture } from "./fixtures";
import { scoreLabel } from "../src/evaluation/ConsistencyPlot";
describe("post-update forecast alignment", () => {
  it("labels a forecast by future target time rather than integration step", () => {
    render(
      <ForecastTimeLabel record={resultFixture().instances[0].forecasts[0]} />,
    );
    expect(screen.getByText(/目标时刻 5.10/)).toBeVisible();
  });
  it("never fabricates zero error when future truth is unavailable", () => {
    const r = resultFixture().instances[0].forecasts[0];
    r.truth_physical = null;
    expect(forecastDifference(r, "center")).toBeNull();
  });
  it("compares the same plate identity and uses the shortest angular difference", () => {
    const r = resultFixture().instances[0].forecasts[0];
    r.physical = {
      ...r.physical!,
      armor_positions: r.physical!.armor_positions!.map((p) => [...p]),
      reference_yaw: Math.PI - 0.1,
    };
    r.truth_physical = { ...r.truth_physical!, reference_yaw: -Math.PI + 0.1 };
    r.physical.armor_positions![2][0] += 0.5;
    expect(forecastDifference(r, "armor", 2)).toBeCloseTo(0.5);
    expect(forecastDifference(r, "armor", 1)).toBeCloseTo(0);
    expect(forecastDifference(r, "angle")).toBeCloseTo(-0.2);
  });
  it("extends N while preserving explicit nonuniform leads", () => {
    expect(resizeLeads([0.1, 0.3], 4)).toEqual([0.1, 0.3, 0.4, 0.5]);
    expect(resizeLeads([0.1, 0.3, 0.5], 2)).toEqual([0.1, 0.3]);
  });
  it("does not show NIS=0 for pure prediction", () => {
    const r = resultFixture().instances[0].forecasts[0];
    expect(scoreLabel(r.nis)).toBe("no_new_observation");
  });
});
