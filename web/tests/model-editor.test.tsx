import { describe, expect, it } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MatrixEditor, parseMatrix } from "../src/filters/MatrixEditor";
import { TransitionPreview } from "../src/filters/ParameterEditor";
describe("parameter editing", () => {
  it("reports malformed and non-square covariance before saving", () => {
    expect(() => parseMatrix("[[1,0],[0]]")).toThrow(/方阵/);
    const updates: number[][][] = [];
    render(
      <MatrixEditor
        label="P₀"
        size={2}
        value={[
          [1, 0],
          [0, 1],
        ]}
        onChange={(v) => updates.push(v)}
      />,
    );
    fireEvent.change(screen.getByLabelText("P₀对角方差"), {
      target: { value: "1,-1" },
    });
    expect(screen.getByRole("alert")).toHaveTextContent("对角元素需要为正");
    expect(updates).toHaveLength(0);
    expect(screen.getByLabelText("P₀对角方差")).toHaveAttribute(
      "aria-invalid",
      "true",
    );
  });
  it("previews rates at a physical interval instead of a fixed per-cycle probability", () => {
    render(
      <TransitionPreview
        rates={[
          [-1, 1],
          [1, -1],
        ]}
        dt={0.1}
      />,
    );
    expect(screen.getByLabelText("参考转移概率矩阵")).toHaveTextContent(
      "[0.909, 0.091]",
    );
  });
});

import { JsonField } from "../src/filters/ParameterEditor";
it("blocks incomplete and wrong-shape JSON instead of running the last valid x0", () => {
  const updates: unknown[] = [];
  render(
    <JsonField
      label="试验 x0"
      value={[0, 0]}
      onChange={(v) => updates.push(v)}
    />,
  );
  const input = screen.getByLabelText("试验 x0");
  fireEvent.change(input, { target: { value: "[" } });
  expect(input).toHaveAttribute("aria-invalid", "true");
  fireEvent.change(input, { target: { value: "{}" } });
  expect(input).toHaveAttribute("aria-invalid", "true");
  expect(updates).toEqual([]);
  fireEvent.change(input, { target: { value: "[1,2]" } });
  expect(input).toHaveAttribute("aria-invalid", "false");
  expect(updates).toEqual([[1, 2]]);
});
it("rejects numeric overflow in nested custom parameters", () => {
  const values: unknown[] = [];
  render(
    <JsonField
      label="模型参数验收"
      value={{}}
      onChange={(v) => values.push(v)}
    />,
  );
  const input = screen.getByLabelText("模型参数验收");
  fireEvent.change(input, { target: { value: '{"nested":{"q":1e999}}' } });
  expect(input).toHaveAttribute("aria-invalid", "true");
  expect(values).toEqual([]);
});
