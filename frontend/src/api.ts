export type OpKind = "equal" | "sub" | "del" | "ins";
export interface WordOp { op: OpKind; ref: string | null; hyp: string | null }

export type ItemStatus = "Chờ" | "Không áp dụng" | "Đã sinh audio" | "Đạt" | "Audio không đạt" | "Lỗi";
export const STATUSES: ItemStatus[] = ["Chờ", "Không áp dụng", "Đã sinh audio", "Đạt", "Audio không đạt", "Lỗi"];

/** Block 1 STT check of a row's audio; Block 2 tests every row with audio and shows this beside it. */
export type VerifyStatus = "Đạt" | "Không đạt" | "Chưa";

export interface Item {
  id: number; audio_set_id: number; sheet: string; tc_id: string; turn: string; feature: string;
  priority: string; region: string; speaker: string; expected: string; source_row: number;
  text_raw: string; text_tts: string | null; skip_reason: string | null; enabled: number;
  status: ItemStatus; audio_path: string | null; attempts: number; ref_text: string | null;
  wer: number | null; cer: number | null; ops: WordOp[]; error: string | null; verify: VerifyStatus;
}

export interface AudioSet {
  id: number; name: string; source_file: string; sheets: string[]; voice: string | null;
  voice_trung?: string | null; voice_nam?: string | null; created_at: string; summary: Record<string, number>;
}

export type MappingField = "text_col" | "id_col" | "region_col" | "expected_col" | "turn_col";
export interface InspectResult { file_id: string; sheets: string[] }
export interface SheetPreview {
  columns: string[]; rows: string[][]; row_count: number; suggestions: Partial<Record<MappingField, string>>;
}
export interface ColumnMapping {
  text_col: string; header_row: number; id_col?: string | null; region_col?: string | null;
  region_value?: string | null; expected_col?: string | null; turn_col?: string | null;
}

export interface Settings {
  voice: string | null; voice_trung: string | null; voice_nam: string | null;
  /** 1 = as synthesized; 0.7–1.3, pitch kept (Block 1 time-stretches the audio). */
  voice_speed?: number; max_regen: number; wer_threshold: number; app_wer_threshold?: number; reject_warn_ratio: number;
  wyoming_host: string; wyoming_port: number; stt_timeout_s: number; wyoming_cmd: string[]; port: number;
}
/** `job` is the oldest running job; `jobs` lists them all (Block 1 and Block 2 may run side by side). */
export interface Health { wyoming: boolean; wyoming_error: string | null; gpu: boolean; job: Job | null; jobs?: Job[] }
/** block1 = generate / verify / regenerate, block2 = app test. One job per lane; on one set the lanes
 * only clash when a job is `exclusive` (Sinh lại swaps WAVs an app test plays). */
export type JobLane = "block1" | "block2";
export interface Job { id: string; name: string; done: number; total: number; lane: JobLane; set_id: number | null;
  exclusive?: boolean }
export interface Voice { id: string; label: string }
/** state: device | unauthorized | offline (Android) · no_wda (iPhone seen, WebDriverAgent not answering). */
export interface DeviceInfo { serial: string; state: string; model: string | null; platform?: "android" | "ios" }
export type DeviceKey = "back" | "home" | "recents" | "enter" | "del" | "power" | "volup" | "voldown";
export type DeviceInputBody =
  | { action: "tap"; x: number; y: number }
  | { action: "swipe"; x: number; y: number; x2: number; y2: number; duration_ms?: number }
  | { action: "key"; key: DeviceKey }
  | { action: "text"; text: string };
export interface DeviceStatus { adb: boolean; ios?: boolean; error: string | null; devices: DeviceInfo[]; busy?: string[] }
/** GET/POST /api/ios/connect — the "Kết nối iPhone" button (starts WebDriverAgent + port forward). */
export interface IosConnect {
  state: "idle" | "starting" | "running" | "error"; step: string | null; error: string | null; detail: string | null;
  udid: string | null; bundle: string | null; external: boolean;
}
export type TtsDeviceKind = "cpu" | "cuda";
export interface CudaInstall { state: "idle" | "running" | "done" | "failed"; log_tail: string[]; error: string | null }
/** GET /api/tts/device: chosen and loaded TTS device, NVIDIA / PyTorch CUDA probe, installer state. */
export interface TtsDevice {
  device: TtsDeviceKind; active: TtsDeviceKind | null; load_error: string | null;
  nvidia: boolean; gpu_name: string | null; torch_cuda: boolean; uv: boolean; install: CudaInstall;
}

export interface ProgressEvent {
  job_id: string; kind: "item" | "progress" | "log" | "done" | "error" | "cancelled";
  done: number; total: number; item: Item | AppResult | null; message: string | null; lane?: JobLane | null;
  /** Block 2: the run (phone) this event is about; none = about the whole job. */
  run_id?: number | null;
}

export interface AppProfile {
  name: string; package: string; open_label: string; stop_label: string; idle_label: string;
  close_label: string; sheet_label: string; discard_label?: string;
  /** Start of the task-form line holding what the app heard, e.g. "Bạn nói: ". */
  heard_prefix?: string;
  /** Notice shown when the app caught nothing ("Chưa nghe rõ"); the sentence is spoken once more. */
  not_heard_label?: string; pre_delay_s: number; post_delay_s: number;
  listen_timeout_s: number; result_timeout_s: number;
  /** Pause between two sentences of a Block 2 run (seconds). */
  between_delay_s?: number;
}
export type AppStatus = "Chờ" | "Đúng" | "Sai" | "Lỗi thao tác";
export interface AppRun {
  id: number; audio_set_id: number; serial: string; device_model: string | null; profile_name: string;
  app_version: string | null; created_at: string; summary: Record<string, number>;
  /** A result is "Đúng" when its MER (0..1) is at most this. */
  wer_threshold: number;
  /** The other phone's run when both ran in one job. */
  pair_run_id?: number | null;
}
export interface AppResult {
  id: number; app_run_id: number; item_id: number; status: AppStatus; app_text: string | null;
  wer: number | null; cer: number | null; ops: WordOp[]; error: string | null; log: string | null;
  verify?: VerifyStatus;
  /** Earlier attempts of this case in the same run (it was run again), newest first. */
  history?: AppAttempt[];
}
export interface AppAttempt {
  status: AppStatus; app_text: string | null; wer: number | null; cer: number | null; error: string | null;
  updated_at: string | null;
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
  iosConnectStatus: () => req<IosConnect>("GET", "/api/ios/connect"),
  iosConnect: () => req<IosConnect>("POST", "/api/ios/connect"),
  iosDisconnect: () => req<IosConnect>("POST", "/api/ios/disconnect"),
  deviceInput: (serial: string, b: DeviceInputBody) =>
    req<{ ok: boolean }>("POST", `/api/device/${encodeURIComponent(serial)}/input`, b),
  inspect(file: File) {
    const fd = new FormData();
    fd.append("file", file);
    return req<InspectResult>("POST", "/api/files/inspect", fd);
  },
  preview: (b: { file_id: string; sheet: string | null; header_row: number }) =>
    req<SheetPreview>("POST", "/api/files/preview", b),
  createSet: (b: { file_id: string; sheets: string[]; name: string; mapping: ColumnMapping }) =>
    req<{ id: number }>("POST", "/api/audio-sets", b),
  sets: () => req<AudioSet[]>("GET", "/api/audio-sets"),
  /** Also removes its app runs, screenshots and WAVs no other set uses; 409 while a job runs. */
  deleteSet: (setId: number) => req<{ ok: boolean }>("DELETE", `/api/audio-sets/${setId}`),
  /** Zip with the set's rows, verify state and WAVs; the server builds it, the browser follows a one-time link. 409 while a job runs. */
  async exportSet(setId: number) {
    const r = await req<{ download_url: string }>("POST", `/api/audio-sets/${setId}/export`);
    const a = document.createElement("a");
    a.href = r.download_url;
    a.click();
  },
  /** Loads a zip from `exportSet` as a NEW set; `missing_audio` rows had no WAV and went back to "Chờ". 422 = not a valid zip. */
  importSet(file: File) {
    const fd = new FormData();
    fd.append("file", file);
    return req<{ id: number; missing_audio: number }>("POST", "/api/audio-sets/import", fd);
  },
  /** Every set + its WAVs, app runs, screenshots, reports and uploads; keeps settings and profiles. 409 while a job runs. */
  /** Back to "Chờ" for every row of every set: drops WAVs, STT/MER results and app runs, keeps imported rows. 409 while a job runs. */
  resetProgress: () => req<{ ok: boolean; items: number }>("DELETE", "/api/progress"),
  clearAllData: () => req<{ ok: boolean; sets: number }>("DELETE", "/api/data"),
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
  jobs: () => req<Job[]>("GET", "/api/jobs"),
  settings: () => req<Settings>("GET", "/api/settings"),
  saveSettings: (s: Settings) => req<Settings>("PUT", "/api/settings", s),
  voices: () => req<Voice[]>("GET", "/api/voices"),
  voicePreviewUrl: (id: string, speed = 1) =>
    `/api/voices/preview?voice_id=${encodeURIComponent(id)}${speed === 1 ? "" : `&speed=${speed}`}`,
  health: () => req<Health>("GET", "/api/health"),
  ttsDevice: () => req<TtsDevice>("GET", "/api/tts/device"),
  setTtsDevice: (device: TtsDeviceKind) => req<TtsDevice>("PUT", "/api/tts/device", { device }),
  installCuda: () => req<TtsDevice>("POST", "/api/tts/install-cuda"),
  profiles: () => req<AppProfile[]>("GET", "/api/profiles"),
  saveProfile: (p: AppProfile) => req<AppProfile>("PUT", `/api/profiles/${encodeURIComponent(p.name)}`, p),
  appRuns: (setId: number) => req<AppRun[]>("GET", `/api/audio-sets/${setId}/app-runs`),
  appResults: (runId: number) => req<AppResult[]>("GET", `/api/app-runs/${runId}/results`),
  startAppRun: (setId: number, serial: string, profile: string, itemIds: number[] | null, serial2?: string | null) =>
    req<{ id: number; pair_id?: number | null; job_id: string }>("POST", `/api/audio-sets/${setId}/app-runs`,
      { serial, profile, item_ids: itemIds, ...(serial2 ? { serial2 } : {}) }),
  downloadFormReport: (runId: number) =>
    downloadFile(`/api/app-runs/${runId}/form-report`, undefined, `KetQua_Phien${runId}.xlsx`),
  /** The server builds the zip, then the browser follows a one-time link: it streams the file
   *  (up to ~1 GB) to disk with its own progress, instead of holding it in a page blob. */
  async downloadSessionZip(runId: number, audio: "failed" | "all" | "selected", itemIds: number[] | null) {
    const r = await req<{ download_url: string }>("POST", `/api/app-runs/${runId}/export-zip`,
      { audio, item_ids: itemIds });
    const a = document.createElement("a");
    a.href = r.download_url;
    a.click();
  },
  /** Grade the run again with another MER threshold (0..1); new runs start with it too. */
  setRunThreshold: (runId: number, werThreshold: number) =>
    req<AppRun>("PUT", `/api/app-runs/${runId}/threshold`, { wer_threshold: werThreshold }),
  resumeAppRun: (runId: number) => req<{ job_id: string }>("POST", `/api/app-runs/${runId}/resume`),
  /** Run the picked cases again inside this run: its other results stay. */
  rerunAppRun: (runId: number, serial: string, itemIds: number[]) =>
    req<{ job_id: string }>("POST", `/api/app-runs/${runId}/rerun`, { serial, item_ids: itemIds }),
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
