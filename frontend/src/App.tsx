import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api, ApiError, STATUSES, type AppProfile, type AppResult, type AppRun, type AudioSet, type DeviceStatus, type Health,
  type Item, type Job, type ProgressEvent, type Settings,
} from "./api";
import { formatPct } from "./format";
import { APP_STATUSES, passRate } from "./status";
import { classifyEvent } from "./events";
import { AppRunPanel } from "./components/AppRunPanel";
import { connectEvents } from "./ws";
import { jobAfterStart, jobFromServer } from "./jobState";
import { Sidebar, type Section } from "./components/Sidebar";
import { RunBar } from "./components/RunBar";
import { RunSettings } from "./components/RunSettings";
import { ItemTable } from "./components/ItemTable";
import { ImportDialog } from "./components/ImportDialog";
import { DevicePanel } from "./components/DevicePanel";
import { ExportZipDialog, type ZipAudio } from "./components/ExportZipDialog";
import { clickRow, emptySelection, prune, toggleAllVisible, type Selection } from "./selection";

function countBy<T>(rows: Iterable<T>, key: (r: T) => string | undefined): Record<string, number> {
  const out: Record<string, number> = {};
  for (const r of rows) {
    const k = key(r);
    if (k !== undefined) out[k] = (out[k] ?? 0) + 1;
  }
  return out;
}

const step1Selectable = (it: Item) => !!it.enabled && !!it.text_tts;
// Step 2 tests every row with audio, verified or not; the verify result is shown beside it.
const step2Listed = (it: Item) => !!it.audio_path && it.status !== "Không áp dụng";
const step2Selectable = (it: Item) => step2Listed(it) && !!it.enabled;

export default function App() {
  const [section, setSection] = useState<Section>("step1");
  const [sel1, setSel1] = useState<Selection>(emptySelection);
  const [sel2, setSel2] = useState<Selection>(emptySelection);
  const [health, setHealth] = useState<Health | null>(null);
  const [sets, setSets] = useState<AudioSet[]>([]);
  const [setId, setSetId] = useState<number | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [filter, setFilter] = useState<string>("all");
  const [search, setSearch] = useState("");
  const [dialog, setDialog] = useState<"import" | "zip" | null>(null);
  const [toast, setToast] = useState<{ text: string; kind: "info" | "error" } | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [settingsLoadFailed, setSettingsLoadFailed] = useState(false);
  const [settingsSaving, setSettingsSaving] = useState(false);
  const [deviceStatus, setDeviceStatus] = useState<DeviceStatus | null>(null);
  const devices = deviceStatus?.devices ?? [];
  const [profiles, setProfiles] = useState<AppProfile[]>([]);
  const [appRuns, setAppRuns] = useState<AppRun[]>([]);
  const [appRunId, setAppRunId] = useState<number | null>(null);
  const [appResults, setAppResults] = useState<Map<number, AppResult>>(new Map());
  const [jobLogs, setJobLogs] = useState<string[]>([]);
  const appRunRef = useRef<number | null>(null);
  appRunRef.current = appRunId;
  const setIdRef = useRef<number | null>(null);
  const finishedJobs = useRef(new Set<string>());
  setIdRef.current = setId;

  const notify = (text: string, kind: "info" | "error" = "info") => {
    setToast({ text, kind });
    window.setTimeout(() => setToast(null), 6000);
  };
  // 422 = "nothing to do" (e.g. Verify with no generated audio): information, not a failure.
  const notifyError = (e: unknown) =>
    notify((e as Error).message, e instanceof ApiError && e.status === 422 ? "info" : "error");

  const loadSets = useCallback(async () => {
    const s = await api.sets();
    setSets(s);
    return s;
  }, []);

  const loadItems = useCallback(async (id: number) => {
    setItems(await api.items(id));
  }, []);

  const loadAppRuns = useCallback(async (id: number, select?: number) => {
    const runs = await api.appRuns(id);
    setAppRuns(runs);
    setAppRunId((cur) => select ?? (runs.some((r) => r.id === cur) ? cur : runs[0]?.id ?? null));
  }, []);

  const loadAppResults = useCallback(async (runId: number) => {
    const rows = await api.appResults(runId);
    setAppResults(new Map(rows.map((r) => [r.item_id, r])));
  }, []);

  const loadSettings = useCallback(() => {
    setSettingsLoadFailed(false);
    api.settings().then(setSettings).catch(() => setSettingsLoadFailed(true));
  }, []);

  const saveProfile = async (p: AppProfile) => {
    try {
      const saved = await api.saveProfile(p);
      setProfiles((ps) => ps.map((x) => (x.name === saved.name ? saved : x)));
      notify(`Đã lưu: nghỉ ${saved.between_delay_s ?? 0}s giữa các câu (${saved.name}).`);
    } catch (e) {
      notifyError(e);
      throw e;
    }
  };

  const saveSettings = async (changes: Partial<Settings>, resetProgress = false) => {
    if (!settings) return;
    setSettingsSaving(true);
    try {
      setSettings(await api.saveSettings({ ...settings, ...changes }));
      if (!resetProgress) {
        notify("Đã lưu cài đặt.");
        return;
      }
      // Settings are saved either way; a failed reset is reported, not thrown back into the panel.
      try {
        await api.resetProgress();
        notify("Đã lưu cài đặt và xóa toàn bộ tiến trình cũ.");
      } catch (e) {
        notify(`Đã lưu cài đặt, nhưng chưa xóa được tiến trình cũ: ${(e as Error).message}`, "error");
      }
      const open = setIdRef.current;
      await Promise.all([loadSets(), open !== null && loadItems(open), open !== null && loadAppRuns(open)]).catch(() => {});
    } finally {
      setSettingsSaving(false);
    }
  };

  useEffect(() => {
    api.profiles().then(setProfiles).catch(() => {});
    const tick = () => api.device().then(setDeviceStatus).catch(() => setDeviceStatus(null));
    tick();
    const t = window.setInterval(tick, 4000);
    return () => window.clearInterval(t);
  }, []);

  useEffect(() => {
    if (setId !== null) loadAppRuns(setId).catch(() => {});
    else { setAppRuns([]); setAppRunId(null); }
  }, [setId, loadAppRuns]);

  useEffect(() => {
    if (appRunId !== null) loadAppResults(appRunId).catch(() => {});
    else setAppResults(new Map());
  }, [appRunId, loadAppResults]);

  useEffect(() => {
    loadSets().then((s) => { if (s[0]) setSetId(s[0].id); }).catch((e) => notify(e.message, "error"));
    api.currentJob().then(setJob).catch(() => {});
    loadSettings();
    const poll = () => api.health()
      .then((h) => { setHealth(h); setJob((j) => jobFromServer(j, h.job)); })
      .catch(() => setHealth(null));
    poll();
    const t = window.setInterval(poll, 5000);
    return () => window.clearInterval(t);
  }, [loadSets, loadSettings]);

  useEffect(() => {
    setSel1(emptySelection);
    setSel2(emptySelection);
    if (setId !== null) loadItems(setId).catch((e) => notify(e.message, "error"));
    else setItems([]);
  }, [setId, loadItems]);

  // Rows can stop being selectable (edited, disabled, failed verify): drop them from the selection.
  useEffect(() => {
    setSel1((s) => prune(s, new Set(items.filter(step1Selectable).map((i) => i.id))));
    setSel2((s) => prune(s, new Set(items.filter(step2Selectable).map((i) => i.id))));
  }, [items]);

  const step2Ready = items.some(step2Selectable);
  useEffect(() => {
    if (section === "step2" && !step2Ready && items.length > 0) setSection("step1");
  }, [section, step2Ready, items.length]);

  useEffect(() => connectEvents((e: ProgressEvent) => {
    const kind = classifyEvent(e);
    const track = () =>
      setJob((j) => (j ? { ...j, done: e.done, total: e.total } : { id: e.job_id, name: "", done: e.done, total: e.total }));
    if (kind === "block1-item") {
      const it = e.item as Item;
      if (it.audio_set_id === setIdRef.current) setItems((prev) => prev.map((p) => (p.id === it.id ? it : p)));
      track();
    } else if (kind === "app-item") {
      const r = e.item as AppResult;
      if (r.app_run_id === appRunRef.current) setAppResults((prev) => new Map(prev).set(r.item_id, r));
      track();
    } else if (kind === "log") {
      const time = new Date().toLocaleTimeString("vi-VN");
      setJobLogs((l) => [...l, `${time} ${e.message}`].slice(-300));
    } else if (kind === "progress") {
      setJob((j) => (j ? { ...j, done: e.done, total: e.total } : j));
    } else {
      finishedJobs.current.add(e.job_id);
      setJob(null);
      loadSets().catch(() => {});
      if (setIdRef.current !== null) {
        loadItems(setIdRef.current).catch(() => {});
        loadAppRuns(setIdRef.current).catch(() => {});
      }
      if (appRunRef.current !== null) loadAppResults(appRunRef.current).catch(() => {});
      if (e.kind === "done") notify("Đã chạy xong.");
      if (e.kind === "cancelled") notify("Đã dừng. Bấm chạy lại để tiếp tục từ câu chưa xong.");
      if (e.kind === "error") notify(`Job dừng vì lỗi: ${e.message}`, "error");
    }
  }, (up) => {
    // After a (re)connect we may have missed a terminal event: ask the server.
    if (up) api.currentJob().then((cur) => setJob((j) => jobFromServer(j, cur))).catch(() => {});
  }), [loadItems, loadSets, loadAppRuns, loadAppResults]);

  const appMode = section === "step2";
  // Step 2 filters on the app verdict of the selected run; step 1 on the Block 1 status.
  const statusOf = useCallback((it: Item) => (appMode ? appResults.get(it.id)?.status : it.status),
    [appMode, appResults]);
  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter((it) =>
      (!appMode || step2Listed(it)) &&
      (filter === "all" || statusOf(it) === filter) &&
      (!q || it.text_raw.toLowerCase().includes(q) || it.tc_id.toLowerCase().includes(q) ||
        (it.text_tts ?? "").toLowerCase().includes(q)));
  }, [items, filter, search, appMode, statusOf]);
  const selection = appMode ? sel2 : sel1;
  const setSelection = appMode ? setSel2 : setSel1;
  const isSelectable = appMode ? step2Selectable : step1Selectable;
  const visibleSelectable = visible.filter(isSelectable).map((i) => i.id);
  const selectedIds = selection.ids.size ? [...selection.ids] : null;

  const startApp = async (serial: string, profile: string) => {
    if (setId === null) return;
    try {
      setJobLogs([]);
      const r = await api.startAppRun(setId, serial, profile, sel2.ids.size ? [...sel2.ids] : null);
      setJob(jobAfterStart(r.job_id, finishedJobs.current));
      await loadAppRuns(setId, r.id);
    } catch (e) {
      notifyError(e);
    }
  };

  const resumeApp = async (runId: number) => {
    try {
      const r = await api.resumeAppRun(runId);
      setJob(jobAfterStart(r.job_id, finishedJobs.current));
    } catch (e) {
      notify((e as Error).message, "error");
    }
  };

  const patch = async (id: number, p: { text_tts?: string; enabled?: boolean }) => {
    try {
      const updated = await api.patchItem(id, p);
      setItems((prev) => prev.map((x) => (x.id === id ? updated : x)));
    } catch (e) {
      notify((e as Error).message, "error");
    }
  };

  const startBlock1 = async (action: "generate" | "verify" | "regenerate", ids: number[] | null) => {
    if (setId === null) return;
    try {
      const r = await api[action](setId, ids);
      setJob(jobAfterStart(r.job_id, finishedJobs.current));
    } catch (e) {
      notifyError(e);
    }
  };

  const exportForm = async () => {
    if (appRunId === null) return;
    try {
      await api.downloadFormReport(appRunId);
    } catch (e) {
      notifyError(e);
    }
  };

  const exportZip = async (audio: ZipAudio) => {
    if (appRunId === null) return;
    try {
      await api.downloadSessionZip(appRunId, audio, audio === "selected" ? [...sel2.ids] : null);
      setDialog(null);
    } catch (e) {
      notifyError(e);
    }
  };

  const stop = async () => {
    if (job) await api.cancelJob(job.id).catch((e) => notify(e.message, "error"));
  };

  const deleteSet = async (id: number) => {
    const name = sets.find((s) => s.id === id)?.name ?? `#${id}`;
    try {
      await api.deleteSet(id);
      const left = await loadSets();
      // The open set is gone: open the next one (the list is newest first) instead of a dangling id.
      if (setIdRef.current === id) setSetId(left[0]?.id ?? null);
      notify(`Đã xóa bộ "${name}".`);
    } catch (e) {
      notify((e as Error).message, "error");
    }
  };

  const exportSet = async (id: number) => {
    try {
      await api.exportSet(id);
    } catch (e) {
      notify((e as Error).message, "error");
    }
  };

  const importSet = async (file: File) => {
    try {
      const r = await api.importSet(file);
      await loadSets();
      setSetId(r.id);
      notify(r.missing_audio > 0
        ? `Đã nạp bộ audio. ${r.missing_audio} câu thiếu audio, cần sinh lại.`
        : "Đã nạp bộ audio.");
    } catch (e) {
      notifyError(e);
    }
  };

  const clearAll = async () => {
    try {
      const { sets: n } = await api.clearAllData();
      const left = await loadSets();
      setSetId(left[0]?.id ?? null);
      notify(`Đã xóa toàn bộ dữ liệu (${n} bộ audio).`);
    } catch (e) {
      notify((e as Error).message, "error");
    }
  };

  const report = async (format: "xlsx" | "csv") => {
    if (setId === null) return;
    try {
      await api.downloadReport(setId, format, appMode ? appRunId : null);
    } catch (e) {
      notify((e as Error).message, "error");
    }
  };

  const current = sets.find((s) => s.id === setId);
  const currentRun = appRuns.find((r) => r.id === appRunId);
  const listedItems = items.filter(step2Listed);
  const readyCount = items.filter(step2Selectable).length;
  const summary = appMode ? countBy(listedItems, (it) => appResults.get(it.id)?.status) : countBy(items, (it) => it.status);
  const total = appMode ? listedItems.length : items.length;

  // Headline numbers next to the title: what the user checks after every run.
  let kpis = null;
  if (current && !appMode) {
    const passRatio = passRate(summary["Đạt"] ?? 0, summary["Audio không đạt"] ?? 0);
    const rejectRatio = passRatio === null ? null : 1 - passRatio;
    const tooMany = rejectRatio !== null && rejectRatio > (settings?.reject_warn_ratio ?? 0.1);
    kpis = (
      <>
        <span className="kpi"><b>{items.length}</b> câu</span>
        <span className="kpi ok"><b>{formatPct(passRatio)}</b> Đạt</span>
        <span className={`kpi ${tooMany ? "bad" : ""}`} title={tooMany ? "Tỉ lệ loại vượt ngưỡng cảnh báo" : undefined}>
          <b>{formatPct(rejectRatio)}</b> Loại
        </span>
      </>
    );
  } else if (current && currentRun) {
    kpis = (
      <>
        <span className="kpi ok"><b>{formatPct(passRate(currentRun.summary["Đúng"] ?? 0, currentRun.summary["Sai"] ?? 0))}</b> Đúng</span>
        <span className="kpi muted">#{currentRun.id} · {currentRun.device_model ?? currentRun.serial}
          {currentRun.app_version ? ` · app ${currentRun.app_version}` : ""}</span>
      </>
    );
  } else if (current) {
    kpis = <span className="kpi"><b>{readyCount}</b> câu có audio sẵn sàng</span>;
  }

  return (
    <div className={`layout ${appMode ? "" : "no-device"}`}>
      <Sidebar
        section={section}
        step2Ready={step2Ready}
        onSection={(s) => {
          setSection(s);
          setFilter("all");
        }}
        health={health}
        sets={sets}
        currentSetId={setId}
        onSelectSet={setSetId}
        onDeleteSet={deleteSet}
        onExportSet={exportSet}
        onImportSet={importSet}
        onClearAll={clearAll}
        deleteLocked={job ? `Đang chạy: ${job.name} — dừng job trước khi xóa, xuất hoặc nạp bộ audio` : null}
        device={deviceStatus}
      />
      <main className="center">
        <header className="center-head">
          <div className="title-block">
            <h1 className="ellipsis">{current ? current.name : "Chưa có bộ audio"}</h1>
            {current && (
              <span className="muted small ellipsis" title={current.sheets.join(", ")}>
                {current.source_file} · {current.sheets.length} sheet · giọng Bắc {current.voice ?? "mặc định"}
                {" · "}Trung {current.voice_trung || current.voice || "mặc định"}
                {" · "}Nam {current.voice_nam || current.voice || "mặc định"}
              </span>
            )}
          </div>
          {kpis && <div className="kpis">{kpis}</div>}
        </header>
        <RunBar
          mode={appMode ? "step2" : "step1"}
          selectedCount={selection.ids.size}
          onClearSelection={() => setSelection(emptySelection)}
          hasSet={setId !== null}
          job={job}
          statuses={appMode ? APP_STATUSES : STATUSES}
          summary={summary}
          total={total}
          filter={filter}
          search={search}
          onFilter={setFilter}
          onSearch={setSearch}
          onImport={() => setDialog("import")}
          onGenerate={() => startBlock1("generate", selectedIds)}
          onVerify={() => startBlock1("verify", selectedIds)}
          onRegenerate={() => startBlock1("regenerate", selectedIds)}
          onStop={stop}
          onReport={report}
          settingsSaving={settingsSaving}
          settingsControls={settings ? (
            <RunSettings settings={settings} busy={!!job} saving={settingsSaving} setCount={sets.length} onSave={saveSettings} />
          ) : settingsLoadFailed ? (
            <span className="small">Chưa tải được cài đặt. <button className="link-btn" onClick={loadSettings}>Thử lại</button></span>
          ) : <span className="muted small">Đang tải cài đặt…</span>}
          appActions={appMode && setId !== null && (
          <AppRunPanel
            devices={devices}
            profiles={profiles}
            runs={appRuns}
            runId={appRunId}
            busy={!!job || settingsSaving}
            readyCount={readyCount}
            selectedCount={sel2.ids.size}
            onExportForm={exportForm}
            onExportZip={() => setDialog("zip")}
            onStart={startApp}
            onSaveProfile={saveProfile}
            onResume={resumeApp}
            onSelectRun={setAppRunId}
          />
          )}
        />
        {setId === null ? (
          <div className="empty">
            <p>Nạp file testcase (.xlsx / .csv) để bắt đầu.</p>
            <button className="btn primary" disabled={settingsSaving} onClick={() => setDialog("import")}>Nạp file</button>
          </div>
        ) : (
          <ItemTable
            items={visible}
            onPatch={patch}
            app={appMode ? appResults : undefined}
            showSheet={(current?.sheets.length ?? 0) > 1}
            selected={selection.ids}
            isSelectable={isSelectable}
            onRowSelect={(index, shift) => {
              const id = visible[index]?.id;
              const pos = visibleSelectable.indexOf(id);
              if (pos >= 0) setSelection((s) => clickRow(s, visibleSelectable, pos, shift));
            }}
            onToggleAll={() => setSelection((s) => toggleAllVisible(s, visibleSelectable))}
            onRegenerate={appMode || job || settingsSaving ? undefined : (id) => startBlock1("regenerate", [id])}
          />
        )}
      </main>
      {appMode && (
        <DevicePanel
          jobLogs={jobLogs}
          profile={profiles[0] ?? null}
          onProfileSaved={(p) => { setProfiles((ps) => ps.map((x) => (x.name === p.name ? p : x))); notify(`Đã lưu hồ sơ ${p.name}`); }}
        />
      )}

      {dialog === "import" && (
        <ImportDialog
          onClose={() => setDialog(null)}
          onCreated={async (id) => {
            await loadSets();
            setSetId(id);
            setFilter("all");
            notify("Đã tạo bộ audio.");
          }}
        />
      )}
      {dialog === "zip" && currentRun && (
        <ExportZipDialog
          totalCount={appResults.size}
          failedCount={(currentRun.summary["Sai"] ?? 0) + (currentRun.summary["Lỗi thao tác"] ?? 0)}
          selectedCount={sel2.ids.size}
          onClose={() => setDialog(null)}
          onExport={exportZip}
        />
      )}
      {toast && <div className={`toast ${toast.kind}`}>{toast.text}</div>}
    </div>
  );
}
