import { useState } from "react";
import { expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { fromWireConfig } from "../src/api/adapter";
import { validateDraft } from "../src/experiments/validation";
import IMMEditor from "../src/filters/IMMEditor";
import {
  applyFormulaSpec,
  createFormulaPreset,
  readFormulaSpec,
} from "../src/filters/formulaModel";
import { wireFixture } from "./fixtures";

it("starts an independent IMM mode from the current form parent rather than an old builtin snapshot", async () => {
  const draft = fromWireConfig(wireFixture());
  const parent = applyFormulaSpec(
    { ...draft.filters[0], kind: "imm" },
    createFormulaPreset("xy", draft.geometry),
  );
  let current = parent;
  function Harness() {
    const [filter, setFilter] = useState(parent);
    current = filter;
    return (
      <IMMEditor
        filter={filter}
        geometry={draft.geometry}
        onChange={setFilter}
      />
    );
  }
  render(<Harness />);
  fireEvent.click(screen.getByLabelText("模式 1 使用父模型方程"));
  await screen.findByLabelText("状态 1 名称");
  const own = current.imm.modes[0].model!;
  expect(readFormulaSpec({ ...current, model: own })?.states).toHaveLength(4);
  expect(current.x0).toHaveLength(4);
  expect(validateDraft({ ...draft, filters: [current] })).toEqual([]);
});

it("rejects an imported builtin IMM mode whose states disagree with the form parent", () => {
  const draft = fromWireConfig(wireFixture());
  const parent = applyFormulaSpec(
    { ...draft.filters[0], kind: "imm" },
    createFormulaPreset("xy", draft.geometry),
  );
  parent.imm.modes[0].use_parent_model = false;
  parent.imm.modes[0].model = {
    kind: "builtin",
    builtin_name: "rm_cv",
    params: {},
  };
  expect(validateDraft({ ...draft, filters: [parent] }).join(" ")).toMatch(
    /11 维状态/,
  );
});
