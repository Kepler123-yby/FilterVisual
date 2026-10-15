import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import FormulaModelEditor from "../src/filters/FormulaModelEditor";
import { api } from "../src/api/client";
import { fromWireConfig } from "../src/api/adapter";
import type { FilterConfig, ModelValidation } from "../src/api/types";
import {
  applyFormulaSpec,
  createFormulaPreset,
  readFormulaSpec,
} from "../src/filters/formulaModel";
import { wireFixture } from "./fixtures";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

function setup(kind: "armor" | "xy" | "bias" = "xy") {
  const config = fromWireConfig(wireFixture());
  let current = applyFormulaSpec(
    config.filters[0],
    createFormulaPreset(kind, config.geometry),
  );
  const changed = vi.fn((next: FilterConfig) => {
    current = next;
  });
  function Harness() {
    const [filter, setFilter] = useState(current);
    return (
      <FormulaModelEditor
        filter={filter}
        geometry={config.geometry}
        onChange={(next) => {
          changed(next);
          setFilter(next);
        }}
      />
    );
  }
  render(<Harness />);
  return { config, changed, current: () => current };
}

describe("formula model form", () => {
  it("persists state, observation and covariance edits without code or JSON", () => {
    const { current } = setup();
    fireEvent.change(screen.getByLabelText("状态 1 初值"), {
      target: { value: "1.25" },
    });
    fireEvent.change(screen.getByLabelText("状态 1 初始方差"), {
      target: { value: "0.09" },
    });
    fireEvent.change(screen.getByLabelText("状态 1 下一时刻公式"), {
      target: { value: "cx + 2*vx*dt" },
    });
    fireEvent.change(screen.getByLabelText("预测观测 x 公式"), {
      target: { value: "cx + plate_radius*cos(plate_offset) + 0.1" },
    });
    fireEvent.change(screen.getByLabelText("Q cx,cx"), {
      target: { value: "0.4*dt**3/3" },
    });
    fireEvent.change(screen.getByLabelText("R x,x"), {
      target: { value: "0.03**2" },
    });
    const result = readFormulaSpec(current())!;
    expect(current().x0[0]).toBe(1.25);
    expect(current().P0[0][0]).toBe(0.09);
    expect(result.states[0].transition).toBe("cx + 2*vx*dt");
    expect(result.observation[0]).toContain("+ 0.1");
    expect(result.q[0][0]).toBe("0.4*dt**3/3");
    expect(result.r[0][0]).toBe("0.03**2");
    expect(screen.queryByText(/build_model/)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("textbox", { name: /JSON/ }),
    ).not.toBeInTheDocument();
  });

  it("keeps Q rows and columns aligned when moving, deleting and adding states", () => {
    const { current } = setup();
    const originalQ = readFormulaSpec(current())!.q;
    fireEvent.click(screen.getByRole("button", { name: "下移状态 cx" }));
    let spec = readFormulaSpec(current())!;
    expect(spec.states.map((state) => state.name)).toEqual([
      "cy",
      "cx",
      "vx",
      "vy",
    ]);
    expect(spec.q[0][0]).toBe(originalQ[1][1]);
    expect(spec.q[0][3]).toBe(originalQ[1][3]);
    expect(spec.q[3][0]).toBe(originalQ[3][1]);
    fireEvent.click(screen.getByRole("button", { name: "删除状态 cy" }));
    spec = readFormulaSpec(current())!;
    expect(spec.states.map((state) => state.name)).toEqual(["cx", "vx", "vy"]);
    expect(spec.q).toHaveLength(3);
    expect(spec.q.every((row) => row.length === 3)).toBe(true);
    expect(current().x0).toHaveLength(3);
    expect(current().P0).toHaveLength(3);
    fireEvent.click(screen.getByRole("button", { name: "添加状态" }));
    spec = readFormulaSpec(current())!;
    expect(spec.states[3]).toMatchObject({
      name: "state_1",
      initial: 0,
      variance: 1,
      truth: "",
      transition: "state_1",
    });
    expect(spec.q[3]).toEqual(["0", "0", "0", "0.000001*dt"]);
    expect(spec.q.slice(0, 3).every((row) => row[3] === "0")).toBe(true);
    expect(current().P0[3]).toEqual([0, 0, 0, 1]);
  });

  it("loads a selected template only on request and exposes its scene assumptions", () => {
    const { current, changed } = setup("armor");
    fireEvent.change(screen.getByLabelText("模型模板"), {
      target: { value: "bias" },
    });
    expect(changed).not.toHaveBeenCalled();
    expect(screen.getByText(/假定朝向固定为 0/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "使用此模板" }));
    const spec = readFormulaSpec(current())!;
    expect(spec.states).toHaveLength(6);
    expect(spec.states.slice(-2).map((state) => state.truth)).toEqual(["", ""]);
    expect(spec.observation[0]).toContain("+ bx");
    expect(spec.r[0][1]).toBe("0.00006");
  });

  it("shows incomplete edits and blocks validation instead of retaining old valid values", () => {
    const { current } = setup();
    fireEvent.change(screen.getByLabelText("状态 1 名称"), {
      target: { value: "dt" },
    });
    fireEvent.change(screen.getByLabelText("状态 1 下一时刻公式"), {
      target: { value: "" },
    });
    expect(readFormulaSpec(current())!.states[0].transition).toBe("");
    expect(screen.getByRole("alert")).toHaveTextContent("不能与公式变量重名");
    expect(screen.getByRole("alert")).toHaveTextContent("请填写下一时刻公式");
    expect(screen.getByRole("button", { name: "验证模型" })).toBeDisabled();
  });

  it("validates generated formulas and clears success after another edit", async () => {
    const validate = vi.spyOn(api, "validateModel").mockResolvedValue({
      valid: true,
      issues: [],
      metadata: { state_names: ["cx", "cy", "vx", "vy"] },
    });
    const { current, config } = setup();
    fireEvent.click(screen.getByRole("button", { name: "验证模型" }));
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(
        "验证通过 · 4 维状态",
      ),
    );
    expect(validate).toHaveBeenCalledWith(
      expect.objectContaining({
        definition: expect.objectContaining({
          source: current().model.source,
          params: current().model.params,
        }),
        geometry: expect.objectContaining({ radius_a: config.geometry.rA }),
        x0: current().x0,
        p0: current().P0,
      }),
    );
    fireEvent.change(screen.getByLabelText("预测观测 yaw 公式"), {
      target: { value: "plate_offset + 0.1" },
    });
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("does not display a stale validation result after a user edits while checking", async () => {
    let resolve!: (value: ModelValidation) => void;
    vi.spyOn(api, "validateModel").mockImplementation(
      () =>
        new Promise((done) => {
          resolve = done;
        }),
    );
    setup();
    fireEvent.click(screen.getByRole("button", { name: "验证模型" }));
    fireEvent.change(screen.getByLabelText("状态 1 下一时刻公式"), {
      target: { value: "cx + unknown*dt" },
    });
    resolve({ valid: true, issues: [] });
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "验证模型" })).toBeEnabled(),
    );
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });

  it("reports equation errors returned by validation in the form", async () => {
    vi.spyOn(api, "validateModel").mockResolvedValue({
      valid: false,
      issues: [{ field: "h", message: "未知变量 unknown" }],
    });
    setup();
    fireEvent.change(screen.getByLabelText("预测观测 x 公式"), {
      target: { value: "cx + unknown" },
    });
    fireEvent.click(screen.getByRole("button", { name: "验证模型" }));
    await waitFor(() =>
      expect(screen.getByRole("status")).toHaveTextContent(
        "h：未知变量 unknown",
      ),
    );
  });
});
