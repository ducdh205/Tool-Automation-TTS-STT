import type { ReactNode } from "react";
import { STATUSES, type ItemStatus, type Job } from "../api";
import { formatPct } from "../format";

interface Props {
  /** Step 1 shows the Block 1 actions; step 2 only filters and progress (its actions live in AppRunPanel). */
  mode: "step1" | "step2";
  hasSet: boolean;
  job: Job | null;
  summary: Record<string, number>;
  filter: ItemStatus | "all";
  search: string;
  onFilter: (f: ItemStatus | "all") => void;
  onSearch: (s: string) => void;
  onImport: () => void;
  onGenerate: () => void;
  onVerify: () => void;
  onRegenerate: () => void;
  onStop: () => void;
  onReport: (format: "xlsx" | "csv") => void;
  rejectWarn: number;
  settingsControls?: ReactNode;
  settingsSaving?: boolean;
  selectedCount: number;
  onClearSelection: () => void;
}

export function RunBar(p: Props) {
  const passed = p.summary["Đạt"] ?? 0;
  const failed = p.summary["Audio không đạt"] ?? 0;
  const verified = passed + failed;
  const reject = verified ? failed / verified : 0;
  const total = Object.values(p.summary).reduce((a, b) => a + b, 0);
  const pct = p.job && p.job.total ? (p.job.done / p.job.total) * 100 : 0;
  const n = p.selectedCount;
  const scope = n ? String(n) : "tất cả";
  const busy = !!p.job;
  const actionDisabled = busy || p.settingsSaving;

  return (
    <div className="runbar">
      {p.mode === "step1" && (
        <div className="toolbar">
          <button className="btn" onClick={p.onImport} disabled={actionDisabled}>Nạp file</button>
          <button className="btn primary" onClick={p.onGenerate} disabled={!p.hasSet || actionDisabled}>Sinh audio ({scope})</button>
          <button className="btn primary" onClick={p.onVerify} disabled={!p.hasSet || actionDisabled}>Verify ({scope})</button>
          <button className="btn" onClick={p.onRegenerate} disabled={!p.hasSet || actionDisabled}
            title="Sinh audio mới (seed khác) — sau đó bấm Verify lại">
            Sinh lại ({n ? n : "tất cả không đạt"})
          </button>
          <button className="btn danger" onClick={p.onStop} disabled={!busy}>Dừng</button>
          <span className="spacer" />
          <button className="btn" onClick={() => p.onReport("xlsx")} disabled={!p.hasSet}>Xuất Excel</button>
          <button className="btn ghost" onClick={() => p.onReport("csv")} disabled={!p.hasSet}>CSV</button>
        </div>
      )}
      {p.mode === "step1" && p.settingsControls}
      {n > 0 && (
        <div className="small selection-line">
          Đang chọn {n} case · <button className="link-btn" onClick={p.onClearSelection}>Bỏ chọn</button>
        </div>
      )}
      <div className="filters">
        <div className="chips">
          <button className={`chip ${p.filter === "all" ? "active" : ""}`} onClick={() => p.onFilter("all")}>
            Tất cả <small>{total}</small>
          </button>
          {STATUSES.map((s) => (
            <button key={s} className={`chip ${p.filter === s ? "active" : ""}`} onClick={() => p.onFilter(s)}>
              {s} <small>{p.summary[s] ?? 0}</small>
            </button>
          ))}
        </div>
        <input className="search" placeholder="Tìm câu, TC_ID…" value={p.search} onChange={(e) => p.onSearch(e.target.value)} />
      </div>
      <div className="progress-line">
        <div className="progress"><div className="bar" style={{ width: `${pct}%` }} /></div>
        <span className="small">
          {p.job ? `${p.job.done}/${p.job.total}` : "Sẵn sàng"}
          {" · "}Đạt {formatPct(verified ? passed / verified : null)}
          {" · "}
          <span className={reject > p.rejectWarn ? "warn" : ""}>Loại {formatPct(verified ? reject : null)}</span>
        </span>
      </div>
    </div>
  );
}
