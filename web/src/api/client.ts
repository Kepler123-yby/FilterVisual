import { fromWireConfig, fromWirePayload, toWireConfig } from "./adapter";
import type { WireConfig, WirePayload } from "./adapter";
import type { ExperimentConfig, ModelValidation, RunStatus } from "./types";
export class ApiError extends Error {
  constructor(
    message: string,
    public status: number,
  ) {
    super(message);
  }
}
async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options,
    headers: { "Content-Type": "application/json", ...options?.headers },
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApiError(
      typeof body.detail === "string"
        ? body.detail
        : body.detail
          ? JSON.stringify(body.detail)
          : `请求失败（${response.status}）`,
      response.status,
    );
  }
  return response.json() as Promise<T>;
}
const post = <T>(path: string, body: unknown) =>
  request<T>(path, { method: "POST", body: JSON.stringify(body) });
export const api = {
  defaultConfig: async () =>
    fromWireConfig(await request<WireConfig>("/default-config")),
  history: () => request<RunStatus[]>("/runs"),
  createRun: (config: ExperimentConfig) =>
    post<RunStatus>("/runs", toWireConfig(config)),
  getStatus: (id: string) => request<RunStatus>(`/runs/${id}`),
  getResult: async (id: string) =>
    fromWirePayload(await request<WirePayload>(`/runs/${id}/result`)),
  getAnalysis: (id: string) => request<unknown>(`/runs/${id}/result`),
  cancel: (id: string) => post<RunStatus>(`/runs/${id}/cancel`, {}),
  template: () => request<{ source: string }>("/models/template"),
  validateModel: (body: unknown) =>
    post<ModelValidation>("/models/validate", body),
  scan: (id: string, body: unknown) =>
    post<RunStatus>(`/runs/${id}/scan`, body),
  monteCarlo: (id: string, body: unknown) =>
    post<RunStatus>(`/runs/${id}/monte-carlo`, body),
  exportUrl: (id: string, format: string) =>
    `/api/runs/${id}/export?format=${format}`,
};
