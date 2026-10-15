import { useEffect, useRef, useState, type ReactNode } from "react";

const numericLiteral = /^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$/;
function parseSignedNumber(raw: string): number | null {
  const text = raw.trim();
  if (!numericLiteral.test(text)) return null;
  const value = Number(text);
  return Number.isFinite(value) ? value : null;
}

export function Field({
  label,
  children,
  hint,
  className = "",
}: {
  label: string;
  children: ReactNode;
  hint?: string;
  className?: string;
}) {
  return (
    <label className={`field ${className}`}>
      <span>{label}</span>
      {children}
      {hint && <small>{hint}</small>}
    </label>
  );
}
export function NumberField({
  label,
  value,
  onChange,
  min,
  max,
  step = "any",
  hint,
  disabled,
  signed = false,
  compact = false,
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number | "any";
  hint?: string;
  disabled?: boolean;
  signed?: boolean;
  compact?: boolean;
}) {
  const [raw, setRaw] = useState(String(value));
  const committed = useRef(value);
  const identity = useRef(label);
  useEffect(() => {
    // A degree → radian → degree conversion can differ by a few ULPs.
    // Preserve the typed literal when the parent echoes our own numeric edit.
    const sameNumber =
      Math.abs(committed.current - value) <=
      8 *
        Number.EPSILON *
        Math.max(1, Math.abs(committed.current), Math.abs(value));
    if (!sameNumber || identity.current !== label) {
      committed.current = value;
      identity.current = label;
      setRaw(String(value));
    }
  }, [value, label]);
  const parsed = parseSignedNumber(raw);
  const error =
    parsed === null
      ? "请输入完整的有限数值，支持负数、小数和科学计数法"
      : min !== undefined && parsed < min
        ? `数值须不小于 ${min}`
        : max !== undefined && parsed > max
          ? `数值须不大于 ${max}`
          : undefined;
  const input = (
    <input
      type={signed ? "text" : "number"}
      inputMode={signed ? "text" : undefined}
      role={signed ? "spinbutton" : undefined}
      aria-label={label}
      aria-valuenow={signed && parsed !== null ? parsed : undefined}
      aria-valuemin={signed ? min : undefined}
      aria-valuemax={signed ? max : undefined}
      aria-invalid={signed ? !!error : undefined}
      title={signed ? error : undefined}
      value={signed ? raw : Number.isFinite(value) ? value : ""}
      onChange={(e) => {
        if (!signed) {
          onChange(e.target.value === "" ? 0 : Number(e.target.value));
          return;
        }
        setRaw(e.target.value);
        const next = parseSignedNumber(e.target.value);
        if (next !== null) {
          committed.current = next;
          onChange(next);
        }
      }}
      onBlur={() => {
        if (signed && parsed !== null && !error) setRaw(String(parsed));
      }}
      onKeyDown={(event) => {
        if (!signed) return;
        if (event.key === "Escape") {
          setRaw(String(value));
        } else if (event.key === "ArrowUp" || event.key === "ArrowDown") {
          event.preventDefault();
          const delta =
            (typeof step === "number" ? step : 1) *
            (event.key === "ArrowUp" ? 1 : -1);
          const next = Math.min(
            max ?? Infinity,
            Math.max(
              min ?? -Infinity,
              Number(((parsed ?? value) + delta).toPrecision(15)),
            ),
          );
          if (Number.isFinite(next)) {
            committed.current = next;
            setRaw(String(next));
            onChange(next);
          }
        }
      }}
      min={min}
      max={max}
      step={step}
      disabled={disabled}
    />
  );
  return compact ? (
    input
  ) : (
    <Field label={label} hint={signed && error ? error : hint}>
      {input}
    </Field>
  );
}
export function Section({
  title,
  subtitle,
  children,
  initiallyOpen = false,
  action,
}: {
  title: string;
  subtitle?: string;
  children: ReactNode;
  initiallyOpen?: boolean;
  action?: ReactNode;
}) {
  return (
    <details className="editor-section" open={initiallyOpen}>
      <summary>
        <span>{title}</span>
        {subtitle && <small>{subtitle}</small>}
      </summary>
      {action}
      <div className="section-body">{children}</div>
    </details>
  );
}
export function Panel({
  title,
  extra,
  children,
  className = "",
  testId,
}: {
  title: string;
  extra?: ReactNode;
  children: ReactNode;
  className?: string;
  testId?: string;
}) {
  return (
    <section className={`panel ${className}`} data-testid={testId}>
      <header className="panel-heading">
        <h2>{title}</h2>
        {extra}
      </header>
      {children}
    </section>
  );
}
export function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="toggle">
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span>{label}</span>
    </label>
  );
}
export function EmptyPlot({ children }: { children: ReactNode }) {
  return (
    <div className="empty-plot">
      <svg width="50" height="40" viewBox="0 0 50 40" aria-hidden="true">
        <path
          d="M4 3v30h42M8 27l10-7 8 3 12-16 7 3"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.5"
        />
      </svg>
      <p>{children}</p>
    </div>
  );
}
export function formatNumber(value: number | null | undefined, digits = 3) {
  return value == null || !Number.isFinite(value) ? "—" : value.toFixed(digits);
}
export const COLORS = [
  "#2866ad",
  "#008e91",
  "#cc7626",
  "#a753a2",
  "#bc485c",
  "#6873c6",
];
