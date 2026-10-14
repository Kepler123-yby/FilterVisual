import type { ReactNode } from "react";
import type { RunPayload } from "../api/types";
export default function ComparisonLayout({
  result,
  enabled,
  mode,
  children,
}: {
  result: RunPayload | null;
  enabled: string[];
  mode: "overlay" | "parallel";
  children: (ids: string[]) => ReactNode;
}) {
  return (
    <div className={mode === "parallel" ? "parallel-plots" : ""}>
      {mode === "parallel" && result
        ? result.instances
            .filter((i) => enabled.includes(i.id))
            .map((i) => (
              <div key={i.id}>
                <h3 className="plot-instance-name">{i.name}</h3>
                {children([i.id])}
              </div>
            ))
        : children(enabled)}
    </div>
  );
}
