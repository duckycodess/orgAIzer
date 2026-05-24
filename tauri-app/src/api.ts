const BASE = "http://localhost:8000/api";

async function req<T>(method: string, path: string, body?: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method,
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`${method} ${path} → ${res.status}`);
  return res.json();
}

export const api = {
  getHistory: (limit = 200) => req<Event[]>("GET", `/history?limit=${limit}`),
  getPending: () => req<Event[]>("GET", "/pending"),
  decide: (id: number, action: string, subject: string) =>
    req("POST", `/pending/${id}/decide`, { action, subject }),
  undo: (id: number) => req("POST", `/history/${id}/undo`),
  markAsSchool: (id: number, subject: string) =>
    req("POST", `/history/${id}/mark-as-school`, { subject }),

  getSettings: () => req<AppSettings>("GET", "/settings"),
  updateSettings: (patch: Partial<AppSettings>) => req("PUT", "/settings", patch),
  getSubjects: () => req<string[]>("GET", "/subjects"),
  scanSubjects: (path: string) => req("POST", "/scan-subjects", { path }),
  seed: (folder: string) => req("POST", "/seed", { folder }),
  retrain: () => req("POST", "/retrain"),
  clearTraining: () => req("POST", "/clear-training"),
  getWarmupStatus: () => req<{ labeled: number; required: number }>("GET", "/warmup-status"),

  watcherStatus: () => req<{ running: boolean }>("GET", "/watcher/status"),
  watcherStart: () => req("POST", "/watcher/start"),
  watcherStop: () => req("POST", "/watcher/stop"),
};

export interface AppEvent {
  type: string;
  event_id?: number;
  filename?: string;
  stage?: string;
  subject?: string;
  overall_confidence?: number;
  school_confidence?: number;
  reason?: string;
  destination_path?: string;
}

export interface AppSettings {
  downloads_path: string;
  school_root: string;
  watch_folder_override: string;
  threshold_high: number;
  threshold_medium: number;
  warmup_active: boolean;
  warmup_labeled_count: number;
  effective_watch_folder: string;
}

export type Event = Record<string, unknown>;
