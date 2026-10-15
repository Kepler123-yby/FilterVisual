import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import TuningPanel from "../src/evaluation/TuningPanel";
import { api } from "../src/api/client";
import { toWireConfig } from "../src/api/adapter";
import { resultFixture, statusFixture } from "./fixtures";

vi.mock("../src/plots/Plot", () => ({ Plot: () => <div /> }));
vi.mock("../src/api/client", () => ({
  api: { scan: vi.fn(), getAnalysis: vi.fn() },
}));
afterEach(cleanup);

function scanFixture(commonCount = 3) {
  const candidate = (multiplier: number, ownRmse: number) => ({
    multiplier,
    value: multiplier,
    parameter_diff: {},
    config: toWireConfig(resultFixture().config),
    report: { instances: [{ position_rmse: ownRmse, angle_rmse: 0.1 }] },
  });
  return {
    type: "noise_scan",
    parameter: "q_scale",
    baseline: candidate(1, 999),
    candidates: [candidate(2, 0.0001)],
    summary: [],
    common_comparison: {
      common_count: commonCount,
      scores: [
        {
          role: "baseline",
          candidate_index: null,
          rmse: commonCount ? 0.015 : null,
          reason: null,
        },
        {
          role: "candidate",
          candidate_index: 0,
          rmse: commonCount ? 0.02 : null,
          reason: null,
        },
      ],
    },
  };
}

describe("noise scan comparison evidence", () => {
  it("shows common-window RMSE and copies the scanned parameter even after changing the next scan", async () => {
    vi.mocked(api.scan).mockResolvedValue(statusFixture);
    vi.mocked(api.getAnalysis).mockResolvedValue(scanFixture());
    const user = userEvent.setup(),
      changed = vi.fn();
    render(
      <TuningPanel
        result={resultFixture()}
        runId="fixture-run"
        onConfig={changed}
      />,
    );
    await user.click(screen.getByRole("button", { name: "扫描 Q / R" }));
    const table = await screen.findByRole("table");
    expect(within(table).getByText("共同中心 RMSE（m）")).toBeVisible();
    expect(within(table).getByText("0.0150")).toBeVisible();
    expect(within(table).getByText("0.0200")).toBeVisible();
    expect(within(table).queryByText("999.0000")).not.toBeInTheDocument();
    expect(screen.getByText(/3 个共同有效时刻/)).toBeVisible();
    await user.selectOptions(screen.getByLabelText("扫描参数"), "r_scale");
    await user.click(screen.getByRole("button", { name: "复制候选到草稿" }));
    expect(changed.mock.lastCall![0].filters.at(-1).name).toContain("Q×2");
  });

  it("leaves common-window scores empty when there are no shared valid samples", async () => {
    vi.mocked(api.scan).mockResolvedValue(statusFixture);
    vi.mocked(api.getAnalysis).mockResolvedValue(scanFixture(0));
    const user = userEvent.setup();
    render(
      <TuningPanel
        result={resultFixture()}
        runId="fixture-run"
        onConfig={() => {}}
      />,
    );
    await user.click(screen.getByRole("button", { name: "扫描 Q / R" }));
    const rows = within(await screen.findByRole("table")).getAllByRole("row");
    expect(within(rows[1]).getByText("—")).toBeVisible();
    expect(within(rows[2]).getByText("—")).toBeVisible();
    expect(screen.getByText(/0 个共同有效时刻/)).toBeVisible();
  });
});
