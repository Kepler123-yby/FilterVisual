import { useState } from "react";
import type { Data } from "plotly.js";
import { useExperimentStore } from "../experiments/store";
import SceneEditor from "../experiments/SceneEditor";
import ObservationEditor from "../experiments/ObservationEditor";
import ConfigFiles from "../experiments/ConfigFiles";
import RunHistory from "../experiments/RunHistory";
import InstanceList from "../filters/InstanceList";
import ForecastEditor from "../forecast/ForecastEditor";
import TargetScene from "../plots/TargetScene";
import StatePlot, { STATE_LABELS } from "../plots/StatePlot";
import ErrorPlot from "../plots/ErrorPlot";
import TimeCursor from "../plots/TimeCursor";
import ComparisonLayout from "../plots/ComparisonLayout";
import ForecastPlot from "../forecast/ForecastPlot";
import ConsistencyPlot from "../evaluation/ConsistencyPlot";
import ReportPanel from "../evaluation/ReportPanel";
import TuningPanel, { mergePatch } from "../evaluation/TuningPanel";
import { COLORS, Field, Panel, Section, Toggle } from "./components";
import { Plot } from "../plots/Plot";
import { fromWireConfig, toWireConfig } from "../api/adapter";
import Sidebar from "./Sidebar";
export default function Workbench() {
  const store = useExperimentStore(),
    [wrapped, setWrapped] = useState(false),
    [showDiagnostics, setShowDiagnostics] = useState(true);
  const { draft, result } = store;
  const states = [
    ...new Set([
      "cx",
      "cy",
      "theta",
      "omega",
      "rA",
      "rB",
      "dh",
      ...(result?.instances.flatMap((i) => i.state_names) ?? []),
    ]),
  ];
  const modeData: Data[] =
    result?.instances
      .filter(
        (i) => i.kind === "imm" && store.enabledInstanceIds.includes(i.id),
      )
      .flatMap((i) =>
        Array.from(
          {
            length:
              i.samples.find((s) => s.mode_probabilities?.length)
                ?.mode_probabilities?.length ?? 0,
          },
          (_, index) => ({
            x: i.samples.map((s) => s.t),
            y: i.samples.map((s) => s.mode_probabilities?.[index] ?? null),
            type: "scatter" as const,
            mode: "lines" as const,
            name: `${i.name} 模式 ${index + 1}`,
            line: { color: COLORS[index % COLORS.length] },
          }),
        ),
      ) ?? [];
  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand">
          <svg width="31" height="31" viewBox="0 0 31 31" aria-hidden="true">
            <path d="M15.5 4v23M4 15.5h23" stroke="#89a9c5" />
            <path
              d="M9 4h13M9 27h13M4 9v13M27 9v13"
              stroke="#2866ad"
              strokeWidth="3"
            />
            <circle cx="15.5" cy="15.5" r="3" fill="#008e91" />
          </svg>
          <div>
            <strong>FilterVisual</strong>
            <span>运动与估计实验台</span>
          </div>
        </div>
        <div className="connection">
          <i className={store.connected ? "online" : ""} />
          {store.connected ? "本地数值服务已连接" : "等待数值服务"}
        </div>
        <span className="header-help" title="配置与结果保存于本地实验目录">
          本地实验 / 可复现
        </span>
      </header>
      <main>
        <div className="experiment-bar">
          <div className="experiment-title">
            <span>当前草稿</span>
            {draft ? (
              <input
                aria-label="实验名称"
                value={draft.name}
                onChange={(e) =>
                  store.updateDraft({ ...draft, name: e.target.value })
                }
              />
            ) : (
              <h1>四装甲板运动与滤波比较</h1>
            )}
            <p>共同观测，多实例估计；每次更新后独立预测未来状态。</p>
          </div>
          <div className="run-actions">
            {store.stale && (
              <span className="badge warning">参数已修改 · 结果待更新</span>
            )}
            {result && !store.stale && (
              <span className="badge success">配置与结果一致</span>
            )}
            <button
              className="primary run-button"
              disabled={!draft || store.busy}
              onClick={() => {
                if (document.querySelector('[aria-invalid="true"]'))
                  store.setError("修正参数编辑器中的错误后再运行。");
                else void store.submit();
              }}
            >
              {store.busy ? "计算中…" : "运行实验"}
            </button>
            {store.busy && (
              <button className="danger" onClick={() => void store.cancel()}>
                停止运行
              </button>
            )}
          </div>
        </div>
        {store.error && (
          <div className="error-banner" role="alert">
            <span>{store.error}</span>
            {!store.connected && (
              <button onClick={() => void store.initialize()}>重新连接</button>
            )}
            <button
              aria-label="关闭错误提示"
              onClick={() => store.setError("")}
            >
              ×
            </button>
          </div>
        )}
        {store.status && (
          <div className="run-progress" role="status">
            <span>
              {store.status.status === "completed"
                ? "实验已完成"
                : store.status.status === "failed"
                  ? "实验失败"
                  : store.status.status === "cancelled"
                    ? "实验已停止"
                    : store.status.stage || "准备数值实验"}
            </span>
            <progress value={store.status.progress} max={1} />
            <small>
              {Math.round(store.status.progress * 100)}% ·{" "}
              {store.status.id.slice(0, 8)}
            </small>
          </div>
        )}
        {draft ? (
          <div className="workbench-grid">
            <Sidebar className="scene-sidebar">
              <Panel
                title="运动场景"
                extra={<span className="sidebar-subtitle">真值与观测</span>}
              >
                <ConfigFiles
                  config={draft}
                  onChange={store.replaceDraft}
                  onError={store.setError}
                />
                <SceneEditor
                  key={store.editorRevision}
                  config={draft}
                  onChange={store.updateDraft}
                />
                <ObservationEditor
                  config={draft}
                  onChange={store.updateDraft}
                />
                <RunHistory
                  runs={store.runs}
                  selectedId={store.selectedRunId}
                  onSelect={(id) => void store.selectRun(id)}
                />
              </Panel>
            </Sidebar>
            <div className="center-column">
              <Panel
                title="四装甲板运动"
                extra={<span className="muted">实线真值 / 虚线估计</span>}
              >
                <TargetScene
                  result={result}
                  config={result?.config ?? draft}
                  time={store.cursorTime}
                  enabled={store.enabledInstanceIds}
                  selectedPlate={store.selectedPlate}
                />
                <TimeCursor
                  time={store.cursorTime}
                  duration={result?.config.duration_s ?? draft.duration_s}
                  onChange={store.setCursorTime}
                  ready={!!result}
                />
              </Panel>
              <Panel
                title="状态拟合与误差"
                extra={
                  <div className="segmented">
                    <button
                      className={
                        store.comparisonMode === "overlay" ? "active" : ""
                      }
                      onClick={() => store.setComparisonMode("overlay")}
                    >
                      叠加比较
                    </button>
                    <button
                      className={
                        store.comparisonMode === "parallel" ? "active" : ""
                      }
                      onClick={() => store.setComparisonMode("parallel")}
                    >
                      并排比较
                    </button>
                  </div>
                }
              >
                <div className="plot-toolbar">
                  <Field label="状态量">
                    <select
                      value={store.selectedState}
                      onChange={(e) => store.setSelectedState(e.target.value)}
                    >
                      {states.map((s) => (
                        <option key={s} value={s}>
                          {STATE_LABELS[s] ?? s} · {s}
                        </option>
                      ))}
                    </select>
                  </Field>
                  <Field label="装甲板">
                    <select
                      value={store.selectedPlate}
                      onChange={(e) =>
                        store.setSelectedPlate(Number(e.target.value))
                      }
                    >
                      {[0, 1, 2, 3].map((i) => (
                        <option key={i} value={i}>
                          A{i}
                        </option>
                      ))}
                    </select>
                  </Field>
                  {store.selectedState === "theta" && (
                    <Toggle
                      label="显示包裹角"
                      checked={wrapped}
                      onChange={setWrapped}
                    />
                  )}
                </div>
                {result && (
                  <div className="instance-visibility">
                    {result.instances.map((i, index) => (
                      <label key={i.id}>
                        <input
                          type="checkbox"
                          checked={store.enabledInstanceIds.includes(i.id)}
                          onChange={(e) =>
                            store.setEnabledInstanceIds(
                              e.target.checked
                                ? [...store.enabledInstanceIds, i.id]
                                : store.enabledInstanceIds.filter(
                                    (id) => id !== i.id,
                                  ),
                            )
                          }
                        />
                        <i
                          style={{ background: COLORS[index % COLORS.length] }}
                        />
                        {i.name}
                        {i.status === "failed" && (
                          <span className="badge warning">失败</span>
                        )}
                      </label>
                    ))}
                  </div>
                )}
                <ComparisonLayout
                  result={result}
                  enabled={store.enabledInstanceIds}
                  mode={store.comparisonMode}
                >
                  {(ids) => (
                    <>
                      <StatePlot
                        result={result}
                        state={store.selectedState}
                        enabled={ids}
                        time={store.cursorTime}
                        wrapped={wrapped}
                        onTimeChange={store.setCursorTime}
                      />
                      <div className="plot-divider">
                        <span>估计值 − 同时刻真值</span>
                        <span>角度误差按最短角计算</span>
                      </div>
                      <ErrorPlot
                        result={result}
                        state={store.selectedState}
                        enabled={ids}
                        time={store.cursorTime}
                        onTimeChange={store.setCursorTime}
                      />
                    </>
                  )}
                </ComparisonLayout>
              </Panel>
              <Panel
                title="更新后纯预测与未来差距"
                extra={<span className="muted">与目标时刻的真值对齐</span>}
              >
                <ForecastPlot
                  result={result}
                  enabled={store.enabledInstanceIds}
                  time={store.cursorTime}
                  plate={store.selectedPlate}
                  onTimeChange={store.setCursorTime}
                />
              </Panel>
              <Panel
                title="NIS / NEES 一致性诊断"
                extra={
                  <button
                    className="text-button"
                    onClick={() => setShowDiagnostics(!showDiagnostics)}
                  >
                    {showDiagnostics ? "收起" : "展开"}
                  </button>
                }
              >
                {showDiagnostics && (
                  <>
                    <ConsistencyPlot
                      result={result}
                      enabled={store.enabledInstanceIds}
                      onTimeChange={store.setCursorTime}
                      confidence={draft.confidence}
                      onConfidenceChange={(confidence) =>
                        store.updateDraft({ ...draft, confidence })
                      }
                    />
                    {modeData.length > 0 && (
                      <div className="mode-probabilities">
                        <h3>IMM 模式概率</h3>
                        <Plot
                          data={modeData}
                          height={210}
                          layout={{
                            yaxis: {
                              title: { text: "模式概率" },
                              range: [0, 1],
                              gridcolor: "#e6ecf2",
                            },
                          }}
                          onTimeClick={store.setCursorTime}
                        />
                      </div>
                    )}
                  </>
                )}
              </Panel>
              <Panel title="比较总结与调整建议">
                <ReportPanel
                  result={result}
                  runId={store.selectedRunId}
                  onTimeChange={store.setCursorTime}
                  onCandidate={(patch, id) => {
                    const wire = toWireConfig(result?.config ?? draft),
                      base = wire.instances.find((f) => f.id === id);
                    if (!base) return;
                    const candidate = mergePatch(base, patch);
                    candidate.id = crypto.randomUUID();
                    candidate.name = `${base.name} 候选`;
                    wire.instances.push(candidate);
                    store.updateDraft(fromWireConfig(wire));
                  }}
                />
              </Panel>
              <Panel title="参数候选与多种子试验">
                <TuningPanel
                  key={store.selectedRunId ?? "empty"}
                  result={result}
                  runId={result ? store.selectedRunId : null}
                  onConfig={(config) => store.updateDraft(config)}
                />
              </Panel>
            </div>
            <Sidebar className="filter-sidebar">
              <Panel
                title="滤波器比较"
                extra={
                  <span className="sidebar-subtitle">
                    {draft.filters.length} 个实例
                  </span>
                }
              >
                <p className="sidebar-intro">
                  各实例按独立频率完成预测 → 观测校正。修改参数后运行新实验。
                </p>
                <Section
                  title="更新后附带纯预测"
                  subtitle={`N = ${draft.forecast.leads_s.length}`}
                  initiallyOpen
                >
                  <ForecastEditor
                    value={draft.forecast}
                    onChange={(forecast) =>
                      store.updateDraft({ ...draft, forecast })
                    }
                  />
                </Section>
                <InstanceList config={draft} onChange={store.updateDraft} />
                {result && (
                  <div className="restore-config">
                    <button onClick={store.restoreRunConfig}>
                      恢复此实验的配置到草稿
                    </button>
                    <p className="help">
                      结果保持只读，恢复后可继续修改并重跑。
                    </p>
                  </div>
                )}
              </Panel>
            </Sidebar>
          </div>
        ) : (
          <div className="loading-workbench">
            <div className="loading-geometry">
              <span />
              <span />
              <span />
              <span />
              <i />
            </div>
            <h2>连接运动与滤波数值服务</h2>
            <p>连接成功后加载演示配置；点击“运行实验”生成真实结果。</p>
            <button onClick={() => void store.initialize()}>重试连接</button>
          </div>
        )}
        <footer>
          四板固定编号 · 世界坐标 +Z 向上 · 米 / 秒 / 弧度{" "}
          <span>显示筛选不改变计算结果</span>
        </footer>
      </main>
    </div>
  );
}
