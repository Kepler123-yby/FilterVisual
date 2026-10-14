import StatePlot from "./StatePlot";
export default function ErrorPlot(
  props: React.ComponentProps<typeof StatePlot>,
) {
  return <StatePlot {...props} error />;
}
