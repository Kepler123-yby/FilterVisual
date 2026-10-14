import { useEffect, useRef } from "react";
import type { Data, Layout, PlotlyHTMLElement } from "plotly.js";
// Plotly's distribution is loaded only when a completed experiment has curves.
let engine: Promise<typeof import("plotly.js")> | undefined;
export function Plot({
  data,
  layout = {},
  height = 240,
  onTimeClick,
  testId,
}: {
  data: Data[];
  layout?: Partial<Layout>;
  height?: number;
  onTimeClick?: (t: number) => void;
  testId?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const renderQueue = useRef<Promise<void>>(Promise.resolve());
  const callback = useRef(onTimeClick);
  callback.current = onTimeClick;
  useEffect(() => {
    let disposed = false;
    let ready = false;
    const element = ref.current;
    if (!element) return;
    engine ??= import("plotly.js-basic-dist-min").then(
      (m) => m.default as typeof import("plotly.js"),
    );
    renderQueue.current = renderQueue.current
      .then(async () => {
        const Plotly = await engine!;
        if (disposed) return;
        await Plotly.react(
          element,
          data,
          {
            font: {
              family: '"Noto Sans SC", "Microsoft YaHei", sans-serif',
              color: "#45566b",
              size: 11,
            },
            margin: { l: 50, r: 20, t: 14, b: 43 },
            paper_bgcolor: "transparent",
            plot_bgcolor: "#fbfdff",
            xaxis: {
              title: { text: "时间（s）", font: { size: 11 } },
              gridcolor: "#e6ecf2",
              zeroline: false,
            },
            yaxis: { gridcolor: "#e6ecf2", zerolinecolor: "#cfd8e2" },
            showlegend: true,
            legend: { orientation: "h", y: 1.14, x: 0, font: { size: 10 } },
            hovermode: "x unified",
            autosize: true,
            height,
            ...layout,
          },
          {
            responsive: true,
            displaylogo: false,
            modeBarButtonsToRemove: ["lasso2d", "select2d"],
            toImageButtonOptions: { format: "png", scale: 2 },
          },
        );
        if (disposed) {
          return;
        }
        ready = true;
        (element as unknown as PlotlyHTMLElement).removeAllListeners?.(
          "plotly_click",
        );
        (element as unknown as PlotlyHTMLElement).on("plotly_click", (ev) => {
          const x = ev.points[0]?.x;
          if (typeof x === "number") callback.current?.(x);
        });
      })
      .catch(() => {
        if (!disposed) element.innerText = "图表模块加载失败，请刷新页面。";
      });
    const observer = new ResizeObserver(() => {
      void engine?.then((p) => {
        if (!disposed && ready && element.isConnected)
          void Promise.resolve(p.Plots.resize(element)).catch(() => {});
      });
    });
    observer.observe(element);
    return () => {
      disposed = true;
      observer.disconnect();
    };
  }, [data, layout, height]);
  useEffect(() => {
    const element = ref.current;
    return () => {
      if (element)
        void renderQueue.current.finally(() => {
          void engine?.then((p) => p.purge(element));
        });
    };
  }, []);
  return (
    <div
      ref={ref}
      className="plot"
      style={{ minHeight: height }}
      data-testid={testId}
    />
  );
}
