import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import ForecastPlot, { forecastDifference } from "../src/forecast/ForecastPlot";
import TargetScene from "../src/plots/TargetScene";
import { COLORS } from "../src/app/components";
import { resultFixture } from "./fixtures";

vi.mock("../src/plots/Plot", () => ({
  Plot: ({ data }: { data: unknown }) => (
    <div data-testid="plot-data">{JSON.stringify(data)}</div>
  ),
}));
afterEach(cleanup);

describe("physical projection validity", () => {
  it("does not score finite placeholders in an invalid estimate or truth projection", () => {
    for (const invalidSide of ["physical", "truth_physical"] as const) {
      const record = resultFixture().instances[0].forecasts[0];
      record[invalidSide] = { ...record[invalidSide]!, valid: false };
      for (const target of ["center", "armor", "angle"] as const)
        expect(forecastDifference(record, target)).toBeNull();
    }
  });

  it("keeps forecast errors from historical payloads without a validity flag", () => {
    const record = resultFixture().instances[0].forecasts[0];
    expect(forecastDifference(record, "center")).toBe(0);
    expect(forecastDifference(record, "armor")).toBe(0);
    expect(forecastDifference(record, "angle")).toBe(0);
  });

  it("hides invalid forecast endpoints while retaining their available future truth", async () => {
    const result = resultFixture(),
      instance = result.instances[0];
    instance.forecasts[0].physical = {
      ...instance.forecasts[0].physical!,
      valid: false,
    };
    render(
      <ForecastPlot
        result={result}
        enabled={[instance.id]}
        time={5}
        plate={0}
        onTimeChange={() => {}}
      />,
    );
    await userEvent.click(
      screen.getByRole("button", { name: "当前更新的未来状态" }),
    );
    const traces = JSON.parse(screen.getByTestId("plot-data").textContent!);
    expect(traces[0].y).toEqual([null]);
    expect(traces[1].y).toEqual([0.25]);
  });

  it("does not draw invalid estimate structures or prediction markers", () => {
    const result = resultFixture(),
      instance = result.instances[0];
    instance.samples[0].physical = {
      ...instance.samples[0].physical!,
      valid: false,
    };
    instance.forecasts[0].physical = {
      ...instance.forecasts[0].physical!,
      valid: false,
    };
    const { container } = render(
      <TargetScene
        result={result}
        config={result.config}
        time={5}
        enabled={[instance.id]}
        selectedPlate={0}
      />,
    );
    const motion = container.querySelector(".motion-svg")!;
    expect(motion.querySelector(`circle[fill="${COLORS[0]}"]`)).toBeNull();
    expect(motion.querySelector(`circle[stroke="${COLORS[0]}"]`)).toBeNull();
    expect(
      motion.querySelector(`path[stroke="${COLORS[0]}"]`)?.getAttribute("d"),
    ).toBe("");
    expect(motion.querySelector('circle[fill="#263e57"]')).not.toBeNull();
  });

  it("breaks the estimated trail across invalid projection intervals", () => {
    const result = resultFixture(),
      instance = result.instances[0],
      sample = instance.samples[0];
    instance.samples = [0, 0.1, 0.5, 1].map((t) => ({
      ...sample,
      t,
      physical: { ...sample.physical!, center_xy: [t, 0], valid: t !== 0.5 },
    }));
    const { container } = render(
      <TargetScene
        result={result}
        config={result.config}
        time={1}
        enabled={[instance.id]}
        selectedPlate={0}
      />,
    );
    const path = container.querySelector(
      `.motion-svg path[stroke="${COLORS[0]}"]`,
    )!;
    expect(path.getAttribute("d")?.match(/[ML]/g)).toEqual(["M", "L", "M"]);
  });
});
