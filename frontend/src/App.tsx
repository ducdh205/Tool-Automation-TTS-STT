import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type AudioSet, type Health, type Item, type ItemStatus, type Job, type ProgressEvent } from "./api";
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
    if (e.kind === "item" && e.item) {
      const it = e.item;
      if (it.audio_set_id === setIdRef.current) setItems((prev) => prev.map((p) => (p.id === it.id ? it : p)));
      setJob((j) => (j ? { ...j, done: e.done, total: e.total } : { id: e.job_id, name: "", done: e.done, total: e.total }));
    } else if (e.kind === "progress") {
      setJob((j) => (j ? { ...j, done: e.done, total: e.total } : j));
    } else {
      finishedJobs.current.add(e.job_id);
      setJob(null);
      loadSets().catch(() => {});
      if (setIdRef.current !== null) loadItems(setIdRef.current).catch(() => {});
      if (e.kind === "done") notify("Đã chạy xong Khối 1.");
      if (e.kind === "cancelled") notify("Đã dừng. Bấm chạy lại để tiếp tục từ câu chưa xong.");
      if (e.kind === "error") notify(`Job dừng vì lỗi: ${e.message}`, "error");
    }
  }, (up) => {
    // After a (re)connect we may have missed a terminal event: ask the server.
    if (up) api.currentJob().then((cur) => setJob((j) => jobFromServer(j, cur))).catch(() => {});
  }), [loadItems, loadSets]);

  const visible = useMemo(() => {
    const q = search.trim().toLowerCase();
    return items.filter((it) =>
      (filter === "all" || it.status === filter) &&
      (!q || it.text_raw.toLowerCase().includes(q) || it.tc_id.toLowerCase().includes(q) ||
        (it.text_tts ?? "").toLowerCase().includes(q)));
  }, [items, filter, search]);

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
      await api.downloadReport(setId, format);
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
        {setId === null ? (
          <div className="empty">
            <p>Nạp file testcase (.xlsx / .csv) để bắt đầu.</p>
            <button className="btn primary" onClick={() => setDialog("import")}>Nạp file</button>
          </div>
        ) : (
          <ItemTable items={visible} onPatch={patch} />
        )}
      </main>
      <DevicePanel />

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
