import { useCallback, useEffect, useRef, useState } from "react";
import type { ExperimentConfig, RunPayload, RunStatus } from "../api/types";
import { api } from "../api/client";
import { toWireConfig } from "../api/adapter";
import { configFingerprint, validateDraft } from "./validation";
const STORAGE_KEY = "filtervisual.draft.v1";
export function useExperimentStore() {
  const [draft, setDraft] = useState<ExperimentConfig | null>(null);
  const [result, setResult] = useState<RunPayload | null>(null);
  const [runs, setRuns] = useState<RunStatus[]>([]);
  const [status, setStatus] = useState<RunStatus | null>(null);
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [cursorTime, setCursorTime] = useState(0);
  const [selectedState, setSelectedState] = useState("cx");
  const [selectedPlate, setSelectedPlate] = useState(0);
  const [enabledInstanceIds, setEnabledInstanceIds] = useState<string[]>([]);
  const [comparisonMode, setComparisonMode] = useState<"overlay" | "parallel">(
    "overlay",
  );
  const [error, setError] = useState("");
  const [connected, setConnected] = useState(false);
  const generation = useRef(0);
  const draftRef = useRef(draft);
  draftRef.current = draft;
  const refreshHistory = useCallback(async () => {
    try {
      setRuns(
        (await api.history()).filter(
          (run) => !run.kind || run.kind === "simulation",
        ),
      );
    } catch {
      /* history does not discard a valid result */
    }
  }, []);
  const initialize = useCallback(async () => {
    try {
      const defaults = await api.defaultConfig();
      let saved: ExperimentConfig | undefined;
      try {
        const raw = localStorage.getItem(STORAGE_KEY);
        if (raw) saved = JSON.parse(raw);
      } catch {
        /* a corrupted draft can be replaced */
      }
      setDraft(
        saved && saved.geometry && saved.filters && saved.forecast
          ? saved
          : defaults,
      );
      setConnected(true);
      setError("");
      void refreshHistory();
    } catch (err) {
      setError(
        `数值服务未连接：${(err as Error).message}。启动后端后点击重试。`,
      );
      setConnected(false);
    }
  }, [refreshHistory]);
  useEffect(() => {
    void initialize();
  }, [initialize]);
  useEffect(() => {
    if (draft) localStorage.setItem(STORAGE_KEY, JSON.stringify(draft));
  }, [draft]);
  const updateDraft = useCallback(
    (next: ExperimentConfig | ((old: ExperimentConfig) => ExperimentConfig)) =>
      setDraft((old) =>
        old ? (typeof next === "function" ? next(old) : next) : old,
      ),
    [],
  );
  const loadResult = useCallback(async (id: string, token: number) => {
    const payload = await api.getResult(id);
    if (generation.current !== token) return;
    setResult(payload);
    setCursorTime(0);
    setEnabledInstanceIds(payload.instances.map((i) => i.id));
  }, []);
  const selectRun = useCallback(
    async (id: string) => {
      const token = ++generation.current;
      setSelectedRunId(id);
      setResult(null);
      setStatus(null);
      setCursorTime(0);
      setError("");
      try {
        const s = await api.getStatus(id);
        if (generation.current !== token) return;
        setStatus(s);
        if (s.status === "completed") await loadResult(id, token);
        else setResult(null);
      } catch (err) {
        setError((err as Error).message);
      }
    },
    [loadResult],
  );
  useEffect(() => {
    if (!status || !["running", "queued", "validating"].includes(status.status))
      return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;
    const id = status.id,
      token = generation.current;
    async function poll() {
      try {
        const s = await api.getStatus(id);
        if (cancelled || token !== generation.current) return;
        setStatus(s);
        if (s.status === "completed") {
          await loadResult(id, token);
          void refreshHistory();
        } else if (["failed", "cancelled", "timed_out"].includes(s.status)) {
          if (s.error) setError(s.error);
          void refreshHistory();
        } else timer = setTimeout(() => void poll(), 700);
      } catch (err) {
        if (!cancelled) {
          setError((err as Error).message);
          timer = setTimeout(() => void poll(), 2500);
        }
      }
    }
    timer = setTimeout(() => void poll(), 500);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [status?.id, status?.status, loadResult, refreshHistory]);
  const submit = useCallback(async () => {
    const config = draftRef.current;
    if (!config) return;
    const issues = validateDraft(config);
    if (issues.length) {
      setError(issues.join("；"));
      return;
    }
    const token = ++generation.current;
    setError("");
    try {
      const s = await api.createRun(structuredClone(config));
      if (token !== generation.current) return;
      setSelectedRunId(s.id);
      setStatus(s);
      setResult(null);
      setCursorTime(0);
      void refreshHistory();
      if (s.status === "completed") await loadResult(s.id, token);
    } catch (err) {
      setError((err as Error).message);
    }
  }, [loadResult, refreshHistory]);
  const cancel = useCallback(async () => {
    if (!status) return;
    try {
      setStatus(await api.cancel(status.id));
      void refreshHistory();
    } catch (err) {
      setError((err as Error).message);
    }
  }, [status, refreshHistory]);
  const restoreRunConfig = useCallback(() => {
    if (result) setDraft(structuredClone(result.config));
  }, [result]);
  return {
    draft,
    result,
    runs,
    status,
    selectedRunId,
    cursorTime,
    selectedState,
    selectedPlate,
    enabledInstanceIds,
    comparisonMode,
    error,
    connected,
    initialize,
    updateDraft,
    submit,
    selectRun,
    cancel,
    setCursorTime,
    setSelectedState,
    setSelectedPlate,
    setEnabledInstanceIds,
    setComparisonMode,
    setError,
    restoreRunConfig,
    stale: !!(
      draft &&
      result &&
      configFingerprint(toWireConfig(draft)) !==
        configFingerprint(toWireConfig(result.config))
    ),
    busy:
      !!status && ["running", "queued", "validating"].includes(status.status),
  };
}
export type ExperimentStore = ReturnType<typeof useExperimentStore>;
