import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fromWireConfig } from "../src/api/adapter";
import { api } from "../src/api/client";
import type { RunStatus } from "../src/api/types";
import { useExperimentStore } from "../src/experiments/store";
import { resultFixture, statusFixture, wireFixture } from "./fixtures";

vi.mock("../src/api/client", () => ({
  api: {
    defaultConfig: vi.fn(),
    history: vi.fn(),
    getStatus: vi.fn(),
    getResult: vi.fn(),
    createRun: vi.fn(),
    cancel: vi.fn(),
  },
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

const oldStatus: RunStatus = {
  ...statusFixture,
  id: "old-run",
  status: "running",
  progress: 0.5,
};
const newStatus: RunStatus = { ...statusFixture, id: "new-run" };

beforeEach(() => {
  vi.resetAllMocks();
  localStorage.clear();
  vi.mocked(api.defaultConfig).mockResolvedValue(fromWireConfig(wireFixture()));
  vi.mocked(api.history).mockResolvedValue([]);
  vi.mocked(api.getStatus).mockImplementation(async (id) =>
    id === oldStatus.id ? oldStatus : newStatus,
  );
  vi.mocked(api.getResult).mockResolvedValue(resultFixture());
});

afterEach(cleanup);

async function initializedStore() {
  const hook = renderHook(() => useExperimentStore());
  await waitFor(() => expect(hook.result.current.connected).toBe(true));
  return hook;
}

describe("history selection request isolation", () => {
  it("ignores an old cancellation response after another run is selected", async () => {
    const cancellation = deferred<RunStatus>();
    vi.mocked(api.cancel).mockReturnValue(cancellation.promise);
    const { result } = await initializedStore();
    await act(() => result.current.selectRun(oldStatus.id));

    let pending!: Promise<void>;
    act(() => {
      pending = result.current.cancel();
    });
    await act(() => result.current.selectRun(newStatus.id));
    await act(async () => {
      cancellation.resolve({ ...oldStatus, status: "cancelled" });
      await pending;
    });

    expect(api.cancel).toHaveBeenCalledWith(oldStatus.id);
    expect(result.current.selectedRunId).toBe(newStatus.id);
    expect(result.current.status).toEqual(newStatus);
    expect(result.current.result).not.toBeNull();
    expect(result.current.error).toBe("");
  });

  it("ignores an old cancellation error after another run is selected", async () => {
    const cancellation = deferred<RunStatus>();
    vi.mocked(api.cancel).mockReturnValue(cancellation.promise);
    const { result } = await initializedStore();
    await act(() => result.current.selectRun(oldStatus.id));

    let pending!: Promise<void>;
    act(() => {
      pending = result.current.cancel();
    });
    await act(() => result.current.selectRun(newStatus.id));
    await act(async () => {
      cancellation.reject(new Error("old cancellation failed"));
      await pending;
    });

    expect(result.current.status).toEqual(newStatus);
    expect(result.current.error).toBe("");
  });

  it("ignores an old status rejection after another run is selected", async () => {
    const lookup = deferred<RunStatus>();
    vi.mocked(api.getStatus).mockImplementation((id) =>
      id === oldStatus.id ? lookup.promise : Promise.resolve(newStatus),
    );
    const { result } = await initializedStore();

    let pending!: Promise<void>;
    act(() => {
      pending = result.current.selectRun(oldStatus.id);
    });
    await act(() => result.current.selectRun(newStatus.id));
    await act(async () => {
      lookup.reject(new Error("old status lookup failed"));
      await pending;
    });

    expect(result.current.selectedRunId).toBe(newStatus.id);
    expect(result.current.status).toEqual(newStatus);
    expect(result.current.error).toBe("");
  });

  it("ignores an old submission error after a history run is selected", async () => {
    const submission = deferred<RunStatus>();
    vi.mocked(api.createRun).mockReturnValue(submission.promise);
    const { result } = await initializedStore();

    let pending!: Promise<void>;
    act(() => {
      pending = result.current.submit();
    });
    await act(() => result.current.selectRun(newStatus.id));
    await act(async () => {
      submission.reject(new Error("old submission failed"));
      await pending;
    });

    expect(api.createRun).toHaveBeenCalledOnce();
    expect(result.current.selectedRunId).toBe(newStatus.id);
    expect(result.current.status).toEqual(newStatus);
    expect(result.current.error).toBe("");
  });
});
