export type OpKind = "equal" | "sub" | "del" | "ins";
export interface WordOp { op: OpKind; ref: string | null; hyp: string | null }

export type ItemStatus = "Chờ" | "Không áp dụng" | "Đã sinh audio" | "Đạt" | "Audio không đạt" | "Lỗi";
export const STATUSES: ItemStatus[] = ["Chờ", "Không áp dụng", "Đã sinh audio", "Đạt", "Audio không đạt", "Lỗi"];

export interface Item {
  id: number; audio_set_id: number; sheet: string; tc_id: string; turn: string; feature: string;
  priority: string; region: string; speaker: string; expected: string; source_row: number;
  text_raw: string; text_tts: string | null; skip_reason: string | null; enabled: number;
  status: ItemStatus; audio_path: string | null; attempts: number; ref_text: string | null;
  wer: number | null; cer: number | null; ops: WordOp[]; error: string | null;
}

export interface AudioSet {
  id: number; name: string; source_file: string; sheets: string[]; voice: string | null;
  created_at: string; summary: Record<string, number>;
}

export interface SheetInfo { name: string; item_count: number; is_testcase: boolean }
export interface InspectResult { file_id: string; is_form: boolean; columns: string[]; sheets: SheetInfo[] }
export interface ColumnMapping { text_col: string; id_col: string | null; header_row?: number }

export interface Settings {
  voice: string | null; max_regen: number; wer_threshold: number; reject_warn_ratio: number;
  wyoming_host: string; wyoming_port: number; stt_timeout_s: number; wyoming_cmd: string[]; port: number;
}
export interface Health { wyoming: boolean; wyoming_error: string | null; gpu: boolean; job: Job | null }
export interface Job { id: string; name: string; done: number; total: number }
export interface Voice { id: string; label: string }
export interface DeviceInfo { serial: string; state: string; model: string | null }
export type DeviceKey = "back" | "home" | "recents" | "enter" | "del" | "power" | "volup" | "voldown";
export type DeviceInputBody =
  | { action: "tap"; x: number; y: number }
  | { action: "swipe"; x: number; y: number; x2: number; y2: number; duration_ms?: number }
  | { action: "key"; key: DeviceKey }
  | { action: "text"; text: string };
export interface DeviceStatus { adb: boolean; error: string | null; devices: DeviceInfo[] }

export interface ProgressEvent {
  job_id: string; kind: "item" | "progress" | "log" | "done" | "error" | "cancelled";
  done: number; total: number; item: Item | AppResult | null; message: string | null;
}

export interface AppProfile {
  name: string; package: string; open_label: string; stop_label: string; idle_label: string;
  close_label: string; sheet_label: string; pre_delay_s: number; post_delay_s: number;
  listen_timeout_s: number; result_timeout_s: number;
}
export type AppStatus = "Chờ" | "Đúng" | "Sai" | "Lỗi thao tác";
export interface AppRun {
  id: number; audio_set_id: number; serial: string; device_model: string | null; profile_name: string;
  app_version: string | null; created_at: string; summary: Record<string, number>;
}
export interface AppResult {
  id: number; app_run_id: number; item_id: number; status: AppStatus; app_text: string | null;
  wer: number | null; cer: number | null; ops: WordOp[]; error: string | null; log: string | null;
}
export interface UiNodeInfo { label: string; cls: string; bounds: number[]; clickable: boolean }

async function req<T>(method: string, url: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method };
  if (body instanceof FormData) init.body = body;
  else if (body !== undefined) {
    init.body = JSON.stringify(body);
    init.headers = { "Content-Type": "application/json" };
  }
  const r = await fetch(url, init);
  if (!r.ok) {
    let msg = `${r.status}`;
    try { msg = (await r.json()).detail ?? msg; } catch { /* not json */ }
    throw new Error(msg);
  }
  return r.json() as Promise<T>;
}

export const api = {
  device: () => req<DeviceStatus>("GET", "/api/device"),
  deviceInput: (serial: string, b: DeviceInputBody) =>
    req<{ ok: boolean }>("POST", `/api/device/${encodeURIComponent(serial)}/input`, b),
  inspect(file: File) {
    const fd = new FormData();
    fd.append("file", file);
    return req<InspectResult>("POST", "/api/files/inspect", fd);
  },
  createSet: (b: { file_id: string; sheets: string[]; name: string; mapping?: ColumnMapping }) =>
    req<{ id: number }>("POST", "/api/audio-sets", b),
  sets: () => req<AudioSet[]>("GET", "/api/audio-sets"),
  items: (setId: number) => req<Item[]>("GET", `/api/audio-sets/${setId}/items`),
  patchItem: (id: number, patch: { text_tts?: string; enabled?: boolean }) =>
    req<Item>("PATCH", `/api/items/${id}`, patch),
  startBlock1: (setId: number) => req<{ job_id: string }>("POST", `/api/audio-sets/${setId}/block1`),
  cancelJob: (jobId: string) => req<{ ok: boolean }>("POST", `/api/jobs/${jobId}/cancel`),
  currentJob: () => req<Job | null>("GET", "/api/jobs/current"),
  settings: () => req<Settings>("GET", "/api/settings"),
  saveSettings: (s: Settings) => req<Settings>("PUT", "/api/settings", s),
  voices: () => req<Voice[]>("GET", "/api/voices"),
  health: () => req<Health>("GET", "/api/health"),
  profiles: () => req<AppProfile[]>("GET", "/api/profiles"),
  saveProfile: (p: AppProfile) => req<AppProfile>("PUT", `/api/profiles/${encodeURIComponent(p.name)}`, p),
  appRuns: (setId: number) => req<AppRun[]>("GET", `/api/audio-sets/${setId}/app-runs`),
  appResults: (runId: number) => req<AppResult[]>("GET", `/api/app-runs/${runId}/results`),
  startAppRun: (setId: number, serial: string, profile: string) =>
    req<{ id: number; job_id: string }>("POST", `/api/audio-sets/${setId}/app-runs`, { serial, profile }),
  resumeAppRun: (runId: number) => req<{ job_id: string }>("POST", `/api/app-runs/${runId}/resume`),
  nodeAt: (serial: string, x: number, y: number) =>
    req<UiNodeInfo>("GET", `/api/device/${encodeURIComponent(serial)}/node-at?x=${x}&y=${y}`),
  audioUrl: (itemId: number, version = "") => `/api/items/${itemId}/audio${version ? `?v=${version}` : ""}`,
  async downloadReport(setId: number, format: "xlsx" | "csv", appRunId?: number | null) {
    const q = appRunId ? `&app_run_id=${appRunId}` : "";
    const r = await fetch(`/api/audio-sets/${setId}/report?format=${format}${q}`, { method: "POST" });
    if (!r.ok) throw new Error(`Xuất báo cáo lỗi (${r.status})`);
    const cd = r.headers.get("content-disposition") ?? "";
    const m = /filename\*=utf-8''([^;]+)|filename="?([^";]+)"?/i.exec(cd);
    const name = m ? decodeURIComponent(m[1] ?? m[2]) : `bao-cao.${format}`;
    const url = URL.createObjectURL(await r.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = name;
    a.click();
    URL.revokeObjectURL(url);
  },
};
