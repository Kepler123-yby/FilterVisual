import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, fireEvent } from "@testing-library/react";
import Workbench from "../src/app/Workbench";
import { api } from "../src/api/client";
import { fromWireConfig, toWireConfig } from "../src/api/adapter";
import {
  cloneFilter,
  configFingerprint,
  degreeToRadian,
  radianToDegree,
  validateDraft,
} from "../src/experiments/validation";
import { wireFixture, resultFixture, statusFixture } from "./fixtures";
vi.mock("../src/plots/Plot", () => ({ Plot: () => <div>解析图表样本</div> }));
vi.mock("../src/api/client", () => ({
  api: {
    defaultConfig: vi.fn(),
    history: vi.fn(),
    createRun: vi.fn(),
    getStatus: vi.fn(),
    getResult: vi.fn(),
    exportUrl: () => "/export",
  },
}));
describe("configuration and immutable results", () => {
  it("round-trips noise strengths, full R and continuous-time IMM rates through the API contract", () => {
    const draft = fromWireConfig(wireFixture());
    draft.filters[0].R[0][1] = draft.filters[0].R[1][0] = 0.00001;
    draft.filters[1].q_rotation = 2.4;
    const wire = toWireConfig(draft);
    expect(
      wire.models.find((m) => m.id === "model-ukf-01")?.params.q_rotation,
    ).toBe(2.4);
    expect(wire.instances[2].imm.generator).toEqual([
      [-1, 1],
      [1, -1],
    ]);
    const adapted = fromWireConfig(wire);
    expect(adapted.filters[0].R[0][1]).toBe(0.00001);
    expect(configFingerprint(toWireConfig(adapted))).toBe(
      configFingerprint(wire),
    );
  });
  it("clones an instance with a new ID without mutating the baseline matrix", () => {
    const original = fromWireConfig(wireFixture()).filters[0];
    const copy = cloneFilter(original, "another-id");
    copy.P0[0][0] = 900;
    expect(copy.id).not.toBe(original.id);
    expect(original.P0[0][0]).toBe(0.04);
  });
  it("rejects an invalid covariance shape and forecast horizon", () => {
    const draft = fromWireConfig(wireFixture());
    draft.filters[0].P0 = [];
    draft.forecast.leads_s = [0];
    expect(validateDraft(draft).join(" ")).toMatch(/P₀/);
    expect(validateDraft(draft).join(" ")).toMatch(/提前量/);
  });
  it("converts UI degrees at the boundary only", () => {
    expect(degreeToRadian(180)).toBeCloseTo(Math.PI);
    expect(radianToDegree(Math.PI)).toBeCloseTo(180);
  });
  it("keeps movement, fit and error visible while editing geometry and marks old results stale", async () => {
    localStorage.clear();
    vi.mocked(api.defaultConfig).mockResolvedValue(
      fromWireConfig(wireFixture()),
    );
    vi.mocked(api.history).mockResolvedValue([statusFixture]);
    vi.mocked(api.getStatus).mockResolvedValue(statusFixture);
    vi.mocked(api.getResult).mockResolvedValue(resultFixture());
    render(<Workbench />);
    await screen.findByLabelText("A 组半径（m）");
    fireEvent.click(screen.getByText(/实验记录/));
    fireEvent.click(screen.getByText("实验 fixture-"));
    await waitFor(() =>
      expect(screen.getByText("配置与结果一致")).toBeVisible(),
    );
    fireEvent.change(screen.getByLabelText("A 组半径（m）"), {
      target: { value: "0.30" },
    });
    expect(screen.getByTestId("target-scene")).toBeVisible();
    expect(screen.getByTestId("state-plot")).toBeVisible();
    expect(screen.getByTestId("error-plot")).toBeVisible();
    expect(screen.getByText(/结果待更新/)).toBeVisible();
    expect(resultFixture().config.geometry.rA).toBe(0.25);
  });
});

describe("independent IMM models", () => {
  it("preserves distinct Python equations and mode R matrices on import/edit/submit", () => {
    const wire = wireFixture();
    const f = wire.instances[2];
    f.q_scale = 2;
    f.r_scale = 3;
    const Ra = [
        [0.01, 0, 0, 0],
        [0, 0.01, 0, 0],
        [0, 0, 0.01, 0],
        [0, 0, 0, 0.02],
      ],
      Rb = Ra.map((row) => row.map((v) => v * 4));
    const source =
      "def build_model(params, geometry):\n    return DifferentMotion(geometry, **params)\n";
    wire.models.push(
      {
        id: "mode-python",
        kind: "python",
        builtin_name: null,
        source,
        params: { observation_covariance: Ra, q_translation: 0.7 },
      },
      {
        id: "mode-builtin",
        kind: "builtin",
        builtin_name: "rm_cv",
        source: null,
        params: { observation_covariance: Rb, q_translation: 1.1 },
      },
    );
    f.imm.models = [
      { model_id: "mode-python", kind: "ukf", q_scale: 0.4, r_scale: 2 },
      { model_id: "mode-builtin", kind: "ekf", q_scale: 4, r_scale: 5 },
    ];
    const view = fromWireConfig(wire);
    expect(view.filters[2].imm.modes[0].use_parent_model).toBe(false);
    const out = toWireConfig(view),
      modes = out.instances[2].imm.models,
      first = out.models.find((m) => m.id === modes[0].model_id)!,
      second = out.models.find((m) => m.id === modes[1].model_id)!;
    expect(first.kind).toBe("python");
    expect(first.source).toBe(source);
    expect(first.params.observation_covariance).toEqual(Ra);
    expect(second.params.observation_covariance).toEqual(Rb);
    expect(second.params.q_translation).toBe(1.1);
    expect(out.instances[2].q_scale).toBe(2);
    expect(out.instances[2].r_scale).toBe(3);
    expect(modes.map((m) => [m.q_scale, m.r_scale])).toEqual([
      [0.4, 2],
      [4, 5],
    ]);
  });
  it("submits edited default IMM mode multipliers", () => {
    const draft = fromWireConfig(wireFixture());
    draft.filters[2].imm.modes[0].q_scale = 0.8;
    const out = toWireConfig(draft);
    expect(out.instances[2].imm.models[0].q_scale).toBe(0.8);
    expect(out.instances[2].imm.models[0].model_id).toBe(
      out.instances[2].model_id,
    );
  });
});
