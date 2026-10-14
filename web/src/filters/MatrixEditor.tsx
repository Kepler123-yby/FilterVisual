import { useEffect, useState } from "react";
import { Field } from "../app/components";
export function parseMatrix(text: string, size?: number): number[][] {
  const parsed: unknown = JSON.parse(text);
  if (
    !Array.isArray(parsed) ||
    !parsed.length ||
    !parsed.every(
      (row) =>
        Array.isArray(row) &&
        row.length === parsed.length &&
        row.every((n) => typeof n === "number" && Number.isFinite(n)),
    )
  )
    throw new Error("填写有限数值组成的方阵");
  if (size && parsed.length !== size)
    throw new Error(`需要 ${size} × ${size} 矩阵`);
  return parsed as number[][];
}
export function diagonalMatrix(values: number[]) {
  return values.map((x, i) => values.map((_, j) => (i === j ? x : 0)));
}
export function MatrixEditor({
  label,
  value,
  onChange,
  size,
  positive = true,
  hint,
}: {
  label: string;
  value: number[][];
  onChange: (value: number[][]) => void;
  size?: number;
  positive?: boolean;
  hint?: string;
}) {
  const [mode, setMode] = useState<"diagonal" | "full">(
    positive ? "diagonal" : "full",
  );
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  useEffect(
    () =>
      setText(
        mode === "diagonal"
          ? value.map((row, i) => row[i]).join(", ")
          : JSON.stringify(value, null, 2),
      ),
    [mode, value],
  );
  function apply(nextText: string) {
    setText(nextText);
    try {
      const next =
        mode === "diagonal"
          ? diagonalMatrix(nextText.split(",").map((n) => Number(n.trim())))
          : parseMatrix(nextText, size);
      if (size && next.length !== size)
        throw new Error(`需要 ${size} 个对角元素`);
      if (
        next.some(
          (row, i) =>
            row.some((n) => !Number.isFinite(n)) || (positive && row[i] <= 0),
        )
      )
        throw new Error("对角元素需要为正，且所有元素有限");
      setError("");
      onChange(next);
    } catch (err) {
      setError((err as Error).message);
    }
  }
  return (
    <div className="matrix-editor">
      <div className="matrix-heading">
        <strong>
          {label}{" "}
          <small>
            {value.length} × {value.length}
          </small>
        </strong>
        <select
          aria-label={`${label}编辑方式`}
          value={mode}
          onChange={(e) => setMode(e.target.value as typeof mode)}
        >
          <option value="diagonal">对角快捷</option>
          <option value="full">完整矩阵</option>
        </select>
      </div>
      <Field
        label={`${label}${mode === "diagonal" ? "对角方差" : "矩阵 JSON"}`}
        hint={hint}
      >
        <textarea
          rows={mode === "full" ? 7 : 2}
          value={text}
          aria-invalid={!!error}
          onChange={(e) => apply(e.target.value)}
          spellCheck={false}
        />
      </Field>
      {error && (
        <p className="field-error" role="alert">
          {error}
        </p>
      )}
    </div>
  );
}
