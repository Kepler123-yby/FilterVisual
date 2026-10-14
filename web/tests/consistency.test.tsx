import { expect, it, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import ConsistencyPlot from "../src/evaluation/ConsistencyPlot";
import { resultFixture } from "./fixtures";
vi.mock("../src/plots/Plot", () => ({
  Plot: ({ data }: { data: { y: unknown[] }[] }) => (
    <div data-testid="plot-values">{JSON.stringify(data[0]?.y)}</div>
  ),
}));
it("uses the available forecast lead when the .3s default does not exist", () => {
  const result = resultFixture();
  result.instances.forEach((i) => i.forecasts.forEach((f) => (f.lead_s = 0.2)));
  render(
    <ConsistencyPlot
      result={result}
      enabled={result.instances.map((i) => i.id)}
      onTimeChange={() => {}}
      confidence={0.95}
      onConfidenceChange={() => {}}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "纯预测 NEES" }));
  expect(screen.getByLabelText("提前量")).toHaveValue(
    ".2".replace(/^\./, "0."),
  );
  expect(screen.getByTestId("plot-values")).toHaveTextContent("[2]");
});
