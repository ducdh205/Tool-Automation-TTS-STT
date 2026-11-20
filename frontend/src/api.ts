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
export interface DeviceStatus { adb: boolean; error: string | null; devices: DeviceInfo[]; busy?: string | null }

export interface ProgressEvent {
  job_id: string; kind: "item" | "progress" | "log" | "done" | "error" | "cancelled";
  done: number; total: number; item: Item | AppResult | null; message: string | null;
}

export interface AppProfile {
  name: string; package: string; open_label: string; stop_label: string; idle_label: string;
  close_label: string; sheet_label: string; discard_label?: string; pre_delay_s: number; post_delay_s: number;
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

/** A non-2xx answer; `status` 422 means "nothing to do / invalid choice", not a failure. */
export class ApiError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

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
    throw new ApiError(msg, r.status);
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
  generate: (setId: number, itemIds: number[] | null) =>
    req<{ job_id: string }>("POST", `/api/audio-sets/${setId}/generate`, { item_ids: itemIds }),
  verify: (setId: number, itemIds: number[] | null) =>
    req<{ job_id: string }>("POST", `/api/audio-sets/${setId}/verify`, { item_ids: itemIds }),
  regenerate: (setId: number, itemIds: number[] | null) =>
    req<{ job_id: string }>("POST", `/api/audio-sets/${setId}/regenerate`, { item_ids: itemIds }),
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
  startAppRun: (setId: number, serial: string, profile: string, itemIds: number[] | null) =>
    req<{ id: number; job_id: string }>("POST", `/api/audio-sets/${setId}/app-runs`,
      { serial, profile, item_ids: itemIds }),
  downloadFormReport: (runId: number) =>
    downloadFile(`/api/app-runs/${runId}/form-report`, undefined, `KetQua_Phien${runId}.xlsx`),
  downloadSessionZip: (runId: number, audio: "failed" | "all" | "selected", itemIds: number[] | null) =>
    downloadFile(`/api/app-runs/${runId}/export-zip`, { audio, item_ids: itemIds }, `Phien${runId}.zip`),
  resumeAppRun: (runId: number) => req<{ job_id: string }>("POST", `/api/app-runs/${runId}/resume`),
  nodeAt: (serial: string, x: number, y: number) =>
    req<UiNodeInfo>("GET", `/api/device/${encodeURIComponent(serial)}/node-at?x=${x}&y=${y}`),
  audioUrl: (itemId: number, version = "") => `/api/items/${itemId}/audio${version ? `?v=${version}` : ""}`,
  downloadReport(setId: number, format: "xlsx" | "csv", appRunId?: number | null) {
    const q = appRunId ? `&app_run_id=${appRunId}` : "";
    return downloadFile(`/api/audio-sets/${setId}/report?format=${format}${q}`, undefined, `bao-cao.${format}`);
  },
};

/** POST, then save the response as a file named by the server (Content-Disposition). */
export async function downloadFile(url: string, body: unknown, fallbackName: string): Promise<void> {
  const init: RequestInit = { method: "POST" };
  if (body !== undefined) {
    init.body = JSON.stringify(body);
    init.headers = { "Content-Type": "application/json" };
  }
  const r = await fetch(url, init);
  if (!r.ok) {
    let msg = `Xuất file lỗi (${r.status})`;
    try { msg = (await r.json()).detail ?? msg; } catch { /* not json */ }
    throw new ApiError(msg, r.status);
  }
  const cd = r.headers.get("content-disposition") ?? "";
  const m = /filename\*=utf-8''([^;]+)|filename="?([^";]+)"?/i.exec(cd);
  const name = m ? decodeURIComponent(m[1] ?? m[2]) : fallbackName;
  const href = URL.createObjectURL(await r.blob());
  const a = document.createElement("a");
  a.href = href;
  a.download = name;
  a.click();
  URL.revokeObjectURL(href);
}
