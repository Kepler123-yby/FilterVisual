import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { NumberField } from "../src/app/components";
import SceneEditor from "../src/experiments/SceneEditor";
import { fromWireConfig, toWireConfig } from "../src/api/adapter";
import { validateDraft } from "../src/experiments/validation";
import { wireFixture } from "./fixtures";
import type { ExperimentConfig } from "../src/api/types";

afterEach(cleanup);

function NumericHarness({
  onChange = () => {},
}: {
  onChange?: (n: number) => void;
}) {
  const [value, setValue] = useState(2);
  return (
    <NumberField
      signed
      label="有向速度"
      value={value}
      step={0.1}
      onChange={(n) => {
        setValue(n);
        onChange(n);
      }}
    />
  );
}

describe("signed numeric motion input", () => {
  it("preserves a minus prefix without replacing the model value with zero", async () => {
    const changed = vi.fn(),
      user = userEvent.setup();
    render(<NumericHarness onChange={changed} />);
    const input = screen.getByLabelText("有向速度");
    await user.clear(input);
    await user.type(input, "-");
    expect(input).toHaveValue("-");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(changed).not.toHaveBeenCalled();
    await user.type(input, "1.5");
    expect(input).toHaveValue("-1.5");
    expect(input).toHaveAttribute("aria-invalid", "false");
    expect(changed).toHaveBeenLastCalledWith(-1.5);
  });

  it("keeps decimal/scientific prefixes editable and Escape restores the last valid number", async () => {
    const changed = vi.fn(),
      user = userEvent.setup();
    render(<NumericHarness onChange={changed} />);
    const input = screen.getByLabelText("有向速度");
    await user.clear(input);
    await user.type(input, "-.25");
    expect(changed).toHaveBeenLastCalledWith(-0.25);
    await user.clear(input);
    await user.type(input, "-2e-");
    expect(input).toHaveValue("-2e-");
    expect(input).toHaveAttribute("aria-invalid", "true");
    await user.type(input, "3");
    expect(changed).toHaveBeenLastCalledWith(-0.002);
    await user.clear(input);
    await user.type(input, "-");
    await user.keyboard("{Escape}");
    expect(input).toHaveValue("-0.002");
    expect(input).toHaveAttribute("aria-invalid", "false");
    await user.keyboard("{ArrowDown}");
    expect(changed).toHaveBeenLastCalledWith(-0.102);
  });
});

function SceneHarness({
  initial,
  changed,
}: {
  initial: ExperimentConfig;
  changed: (c: ExperimentConfig) => void;
}) {
  const [config, setConfig] = useState(initial);
  return (
    <SceneEditor
      config={config}
      onChange={(next) => {
        setConfig(next);
        changed(next);
      }}
    />
  );
}

describe("signed scene configuration", () => {
  it("discards a partial input when switching to a different motion field with the same value", async () => {
    const config = fromWireConfig(wireFixture());
    config.translation.mode = "constant";
    config.translation.velocity_xy[0] = config.translation.speed_range[0];
    const user = userEvent.setup();
    render(<SceneHarness initial={config} changed={() => {}} />);
    const vx = screen.getByLabelText("速度 vx（m/s）");
    await user.clear(vx);
    await user.type(vx, "-");
    await user.selectOptions(
      screen.getByLabelText("平移方式"),
      "random_smooth",
    );
    expect(screen.getByLabelText("速度下限（m/s）")).toHaveValue("0.5");
    expect(screen.getByLabelText("速度下限（m/s）")).toHaveAttribute(
      "aria-invalid",
      "false",
    );
  });
  it("lets typed negative XY velocities and every spin coefficient reach the API unchanged", async () => {
    const config = fromWireConfig(wireFixture());
    config.translation.mode = "constant";
    const changed = vi.fn(),
      user = userEvent.setup();
    render(<SceneHarness initial={config} changed={changed} />);
    for (const [label, value] of [
      ["速度 vx（m/s）", "-1.5"],
      ["速度 vy（m/s）", "-0.25"],
      ["正弦项 1 A", "-0.8"],
      ["正弦项 1 Ω", "-2"],
      ["正弦项 1 a", "-0.3"],
      ["正弦项 1 C", "-1"],
    ]) {
      const field = screen.getByLabelText(label);
      await user.clear(field);
      await user.type(field, value);
    }
    const draft = changed.mock.lastCall![0] as ExperimentConfig;
    const wire = toWireConfig(draft);
    expect(wire.scene.translation.velocity_xy).toEqual([-1.5, -0.25]);
    expect(wire.scene.rotation.terms[0]).toEqual({
      amplitude: -0.8,
      frequency_rad_s: -2,
      phase_rad: -0.3,
      offset: -1,
    });
    expect(validateDraft(draft)).toEqual([]);
    expect(screen.getByLabelText("A 组半径（m）")).toHaveAttribute(
      "min",
      "0.001",
    );
  });

  it("preserves typed negative heading and initial angle through degree/radian feedback", async () => {
    const config = fromWireConfig(wireFixture());
    config.translation.mode = "segments";
    config.translation.segments = [{ t: 0, speed: 2, heading: 0 }];
    config.spin.mode = "angular_velocity";
    const changed = vi.fn(),
      user = userEvent.setup();
    render(<SceneHarness initial={config} changed={changed} />);
    for (const label of ["方向（°）", "初始参考角（°）"]) {
      const field = screen.getByLabelText(label);
      await user.clear(field);
      await user.type(field, "-115");
      expect(field).toHaveValue("-115");
      expect(field).toHaveAttribute("aria-invalid", "false");
    }
    expect(screen.getByLabelText("方向（°）")).toHaveValue("-115");
    const wire = toWireConfig(changed.mock.lastCall![0] as ExperimentConfig);
    expect(wire.scene.translation.waypoints[0].heading_rad).toBeCloseTo(
      (-115 * Math.PI) / 180,
      12,
    );
    expect(wire.scene.rotation.initial_yaw).toBeCloseTo(
      (-115 * Math.PI) / 180,
      12,
    );
  });

  it("discards a deleted sine row's partial input when the following row has the same value", async () => {
    const config = fromWireConfig(wireFixture());
    config.spin.terms = [
      { A: 2, frequency_rad_s: 1, phase_rad: 0, C: 0 },
      { A: 2, frequency_rad_s: 1, phase_rad: 0, C: 0 },
    ];
    const changed = vi.fn(),
      user = userEvent.setup();
    render(<SceneHarness initial={config} changed={changed} />);
    const first = screen.getByLabelText("正弦项 1 A");
    await user.clear(first);
    await user.type(first, "-");
    expect(first).toHaveAttribute("aria-invalid", "true");
    await user.click(screen.getByLabelText("删除正弦项 1"));
    const remaining = screen.getByLabelText("正弦项 1 A");
    expect(remaining).toHaveValue("2");
    expect(remaining).toHaveAttribute("aria-invalid", "false");
    const wire = toWireConfig(changed.mock.lastCall![0] as ExperimentConfig);
    expect(wire.scene.rotation.terms).toEqual([
      { amplitude: 2, frequency_rad_s: 1, phase_rad: 0, offset: 0 },
    ]);
  });

  it("discards a deleted waypoint's partial input when the following speed has the same value", async () => {
    const config = fromWireConfig(wireFixture());
    config.translation.mode = "segments";
    config.translation.segments = [
      { t: 0, speed: 2, heading: 0 },
      { t: 1, speed: 2, heading: 0 },
    ];
    const changed = vi.fn(),
      user = userEvent.setup();
    render(<SceneHarness initial={config} changed={changed} />);
    const first = screen.getAllByLabelText("速度（m/s）")[0];
    await user.clear(first);
    await user.type(first, "-");
    expect(first).toHaveAttribute("aria-invalid", "true");
    await user.click(screen.getByLabelText("删除节点 1"));
    const remaining = screen.getByLabelText("速度（m/s）");
    expect(remaining).toHaveValue("2");
    expect(remaining).toHaveAttribute("aria-invalid", "false");
    const wire = toWireConfig(changed.mock.lastCall![0] as ExperimentConfig);
    expect(wire.scene.translation.waypoints).toEqual([
      { time_s: 1, speed: 2, heading_rad: 0 },
    ]);
  });

  it("accepts signed ranges and reverse waypoint speeds but rejects a reversed range", async () => {
    const config = fromWireConfig(wireFixture());
    const changed = vi.fn(),
      user = userEvent.setup();
    render(<SceneHarness initial={config} changed={changed} />);
    for (const [label, value] of [
      ["速度下限（m/s）", "-2"],
      ["速度上限（m/s）", "-0.5"],
    ]) {
      const field = screen.getByLabelText(label);
      await user.clear(field);
      await user.type(field, value);
    }
    const draft = changed.mock.lastCall![0] as ExperimentConfig;
    expect(toWireConfig(draft).scene.translation.speed_min).toBe(-2);
    expect(toWireConfig(draft).scene.translation.speed_max).toBe(-0.5);
    expect(validateDraft(draft)).toEqual([]);
    const invalid = structuredClone(draft);
    invalid.translation.speed_range = [1, -1];
    expect(validateDraft(invalid).join(" ")).toMatch(/速度.*上限/);
    fireEvent.change(screen.getByLabelText("平移方式"), {
      target: { value: "segments" },
    });
    await user.click(screen.getByRole("button", { name: "＋ 添加节点" }));
    const speed = screen.getByLabelText("速度（m/s）");
    await user.clear(speed);
    await user.type(speed, "-1");
    const waypointDraft = changed.mock.lastCall![0] as ExperimentConfig;
    expect(
      toWireConfig(waypointDraft).scene.translation.waypoints[0].speed,
    ).toBe(-1);
  });
});
