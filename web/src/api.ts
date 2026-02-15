import type { ApiError, PublicScreen, RunsListResponse } from "./types";

export class ApiRequestError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(path, {
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(init.headers || {})
    },
    ...init
  });

  if (!res.ok) {
    let detail = `请求失败（${res.status}）`;
    try {
      const body = (await res.json()) as ApiError;
      if (body.detail) detail = body.detail;
    } catch {
      // ignore decode error
    }
    throw new ApiRequestError(res.status, detail);
  }

  return (await res.json()) as T;
}

export const api = {
  guestInit: () => request<{ ok: boolean; message: string }>("/api/guest/init", { method: "POST" }),
  register: (username: string, password: string) =>
    request<{ ok: boolean; message: string }>("/api/auth/register", {
      method: "POST",
      body: JSON.stringify({ username, password })
    }),
  login: (username: string, password: string) =>
    request<{ ok: boolean; message: string }>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ username, password })
    }),
  logout: () => request<{ ok: boolean; message: string }>("/api/auth/logout", { method: "POST" }),
  createRun: () => request<{ run_id: string }>("/api/runs", { method: "POST" }),
  listRuns: () => request<RunsListResponse>("/api/runs"),
  getActiveRun: () => request<PublicScreen | { run: null }>("/api/runs/active"),
  getRun: (runId: string) => request<PublicScreen>(`/api/runs/${runId}`),
  allocate: (runId: string, attributes: Record<string, number>) =>
    request<PublicScreen>(`/api/runs/${runId}/allocate`, {
      method: "POST",
      body: JSON.stringify({ attributes })
    }),
  choose: (runId: string, optionId: string) =>
    request<PublicScreen>(`/api/runs/${runId}/choose`, {
      method: "POST",
      body: JSON.stringify({ option_id: optionId })
    }),
  chooseFinal: (runId: string, tacticId: string) =>
    request<PublicScreen>(`/api/runs/${runId}/final`, {
      method: "POST",
      body: JSON.stringify({ tactic_id: tacticId })
    }),
  finish: (runId: string) => request<PublicScreen>(`/api/runs/${runId}/finish`, { method: "POST" })
};
