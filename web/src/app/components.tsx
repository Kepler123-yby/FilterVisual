import type { ReactNode } from "react";

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
}: {
  label: string;
  value: number;
  onChange: (value: number) => void;
  min?: number;
  max?: number;
  step?: number | "any";
  hint?: string;
  disabled?: boolean;
}) {
  return (
    <Field label={label} hint={hint}>
      <input
        type="number"
        aria-label={label}
        value={Number.isFinite(value) ? value : ""}
        onChange={(e) =>
          onChange(e.target.value === "" ? 0 : Number(e.target.value))
        }
        min={min}
        max={max}
        step={step}
        disabled={disabled}
      />
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
