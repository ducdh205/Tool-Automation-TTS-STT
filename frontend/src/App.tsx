import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  api, type AppProfile, type AppResult, type AppRun, type AudioSet, type DeviceInfo, type Health, type Item,
  type ItemStatus, type Job, type ProgressEvent,
} from "./api";
import { classifyEvent } from "./events";
import { AppRunPanel } from "./components/AppRunPanel";
import { connectEvents } from "./ws";
import { jobAfterStart, jobFromServer } from "./jobState";
import { Sidebar, type Section } from "./components/Sidebar";
import { RunBar } from "./components/RunBar";
import { ItemTable } from "./components/ItemTable";
import { ImportDialog } from "./components/ImportDialog";
import { SettingsPanel } from "./components/SettingsPanel";
import { DevicePanel } from "./components/DevicePanel";

function countByStatus(items: Item[]): Record<string, number> {
  const out: Record<string, number> = {};
  for (const it of items) out[it.status] = (out[it.status] ?? 0) + 1;
  return out;
}

export default function App() {
  const [section, setSection] = useState<Section>("data");
  const [health, setHealth] = useState<Health | null>(null);
  const [sets, setSets] = useState<AudioSet[]>([]);
  const [setId, setSetId] = useState<number | null>(null);
  const [items, setItems] = useState<Item[]>([]);
  const [job, setJob] = useState<Job | null>(null);
  const [filter, setFilter] = useState<ItemStatus | "all">("all");
  const [search, setSearch] = useState("");
  const [dialog, setDialog] = useState<"import" | "settings" | null>(null);
  const [toast, setToast] = useState<{ text: string; kind: "info" | "error" } | null>(null);
  const [rejectWarn, setRejectWarn] = useState(0.1);
  const [devices, setDevices] = useState<DeviceInfo[]>([]);
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

  useEffect(() => {
    api.profiles().then(setProfiles).catch(() => {});
    const tick = () => api.device().then((d) => setDevices(d.devices)).catch(() => setDevices([]));
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
    api.settings().then((s) => setRejectWarn(s.reject_warn_ratio)).catch(() => {});
    const poll = () => api.health()
      .then((h) => { setHealth(h); setJob((j) => jobFromServer(j, h.job)); })
      .catch(() => setHealth(null));
    poll();
    const t = window.setInterval(poll, 5000);
    return () => window.clearInterval(t);
  }, [loadSets]);

  useEffect(() => {
    if (setId !== null) loadItems(setId).catch((e) => notify(e.message, "error"));
    else setItems([]);
  }, [setId, loadItems]);

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

  const appMode = section === "app";
  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter((it) =>
      (!appMode || it.status === "Đạt") &&
      (filter === "all" || it.status === filter) &&
      (!q || it.text_raw.toLowerCase().includes(q) || it.tc_id.toLowerCase().includes(q) ||
        (it.text_tts ?? "").toLowerCase().includes(q)));
  }, [items, filter, search, appMode]);

  const startApp = async (serial: string, profile: string) => {
    if (setId === null) return;
    try {
      setJobLogs([]);
      const r = await api.startAppRun(setId, serial, profile);
      setJob(jobAfterStart(r.job_id, finishedJobs.current));
      await loadAppRuns(setId, r.id);
    } catch (e) {
      notify((e as Error).message, "error");
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

  const run = async () => {
    if (setId === null) return;
    try {
      const r = await api.startBlock1(setId);
      setJob(jobAfterStart(r.job_id, finishedJobs.current));
      setSection("block1");
    } catch (e) {
      notify((e as Error).message, "error");
    }
  };

  const stop = async () => {
    if (job) await api.cancelJob(job.id).catch((e) => notify(e.message, "error"));
  };

  const report = async (format: "xlsx" | "csv") => {
    if (setId === null) return;
    try {
      await api.downloadReport(setId, format, section === "app" ? appRunId : null);
    } catch (e) {
      notify((e as Error).message, "error");
    }
  };

  const current = sets.find((s) => s.id === setId);

  return (
    <div className="layout">
      <Sidebar
        section={section}
        onSection={(s) => {
          setSection(s);
          if (s === "data") setDialog("import");
          if (s === "report") report("xlsx");
          if (s === "app") setFilter("all");
        }}
        health={health}
        sets={sets}
        currentSetId={setId}
        onSelectSet={setSetId}
        onSettings={() => setDialog("settings")}
      />
      <main className="center">
        <div className="center-head">
          <h1>{current ? current.name : "Chưa có bộ audio"}</h1>
          {current && (
            <span className="muted small">
              {current.source_file} · {current.sheets.length} sheet · giọng {current.voice}
            </span>
          )}
        </div>
        <RunBar
          hasSet={setId !== null}
          job={job}
          summary={countByStatus(items)}
          filter={filter}
          search={search}
          onFilter={setFilter}
          onSearch={setSearch}
          onImport={() => setDialog("import")}
          onRun={run}
          onStop={stop}
          onReport={report}
          rejectWarn={rejectWarn}
        />
        {appMode && setId !== null && (
          <AppRunPanel
            devices={devices}
            profiles={profiles}
            runs={appRuns}
            runId={appRunId}
            busy={!!job}
            passedCount={items.filter((i) => i.status === "Đạt").length}
            onStart={startApp}
            onResume={resumeApp}
            onSelectRun={setAppRunId}
          />
        )}
        {setId === null ? (
          <div className="empty">
            <p>Nạp file testcase (.xlsx / .csv) để bắt đầu.</p>
            <button className="btn primary" onClick={() => setDialog("import")}>Nạp file</button>
          </div>
        ) : (
          <ItemTable items={visible} onPatch={patch} app={appMode && appRunId !== null ? appResults : undefined} />
        )}
      </main>
      <DevicePanel
        jobLogs={jobLogs}
        profile={profiles[0] ?? null}
        onProfileSaved={(p) => { setProfiles((ps) => ps.map((x) => (x.name === p.name ? p : x))); notify(`Đã lưu hồ sơ ${p.name}`); }}
      />

      {dialog === "import" && (
        <ImportDialog
          onClose={() => setDialog(null)}
          onCreated={async (id) => {
            setDialog(null);
            await loadSets();
            setSetId(id);
            setFilter("all");
            notify("Đã tạo bộ audio.");
          }}
        />
      )}
      {dialog === "settings" && (
        <SettingsPanel onClose={() => {
          setDialog(null);
          api.settings().then((s) => setRejectWarn(s.reject_warn_ratio)).catch(() => {});
        }} />
      )}
      {toast && <div className={`toast ${toast.kind}`}>{toast.text}</div>}
    </div>
  );
}
