import type { ReactNode } from "react";
import type { Job } from "../api";
import { STATUS_CLASS } from "../status";
import { Icon } from "./Icon";
import { Popover } from "./Popover";

interface Props {
  /** Step 1 shows the Block 1 actions; step 2 shows `appActions` (from AppRunPanel) in the same slot. */
  mode: "step1" | "step2";
  hasSet: boolean;
  /** Every running job: each gets its own progress line and Stop button. */
  jobs: Job[];
  /** Why this step's run buttons are off (a conflicting job runs), or null when they are free. */
  blocked: string | null;
  /** Like `blocked`, for "Sinh lại" (it also waits for an app test on this set); defaults to `blocked`. */
  regenBlocked?: string | null;
  /** Count per status for the filter chips (Block 1 statuses in step 1, app verdicts in step 2). */
  statuses: readonly string[];
  summary: Record<string, number>;
  total: number;
  filter: string;
  search: string;
  onFilter: (f: string) => void;
  onSearch: (s: string) => void;
  onImport: () => void;
  onGenerate: () => void;
  onVerify: () => void;
  onRegenerate: () => void;
  onStop: (jobId: string) => void;
  onReport: (format: "xlsx" | "csv") => void;
  settingsControls?: ReactNode;
  settingsSaving?: boolean;
  appActions?: ReactNode;
  selectedCount: number;
  onClearSelection: () => void;
}

export function RunBar(p: Props) {
  const n = p.selectedCount;
  const scope = n ? String(n) : "tất cả";
  const actionDisabled = !!p.blocked || p.settingsSaving;
  const why = p.blocked ?? undefined;
  const regenWhy = p.regenBlocked === undefined ? p.blocked : p.regenBlocked;
  // Empty statuses only add noise; the active one stays so the filter can be seen and cleared.
  const chips = p.statuses.filter((s) => (p.summary[s] ?? 0) > 0 || p.filter === s);

  return (
    <div className="runbar">
      <div className="toolbar">
        {p.mode === "step1" ? (
          <>
            <button className="btn" onClick={p.onImport} disabled={p.settingsSaving}><Icon name="upload" />Nạp file</button>
            <span className="divider" />
            <button className="btn primary" onClick={p.onGenerate} disabled={!p.hasSet || actionDisabled} title={why}>
              <Icon name="play" />Sinh audio ({scope})
            </button>
            <button className="btn primary" onClick={p.onVerify} disabled={!p.hasSet || actionDisabled} title={why}>
              <Icon name="check" />Verify ({scope})
            </button>
            <button className="btn" onClick={p.onRegenerate} disabled={!p.hasSet || !!regenWhy || !!p.settingsSaving}
              title={regenWhy ?? "Sinh audio mới (seed khác) — sau đó bấm Verify lại"}>
              <Icon name="refresh" />Sinh lại ({n ? n : "tất cả không đạt"})
            </button>
            <span className="spacer" />
            {p.settingsControls}
            <Popover buttonClassName="btn" panelLabel="Xuất báo cáo" align="right" disabled={!p.hasSet}
              label={<><Icon name="download" />Xuất<Icon name="chevron" size={13} /></>}>
              {(_open, close) => (
                <div className="menu">
                  <button className="menu-item" onClick={() => { close(); p.onReport("xlsx"); }}>Excel (.xlsx)</button>
                  <button className="menu-item" onClick={() => { close(); p.onReport("csv"); }}>CSV</button>
                </div>
              )}
            </Popover>
          </>
        ) : p.appActions}
      </div>

      {p.jobs.map((j) => (
        <div key={j.id} className="progress-line" role="status" aria-label={j.name}>
          <span className="small ellipsis job-name" title={j.name}>{j.name}</span>
          <div className="progress"><div className="bar" style={{ width: `${j.total ? (j.done / j.total) * 100 : 0}%` }} /></div>
          <span className="small num">{j.done}/{j.total}</span>
          <button className="btn danger small-btn" onClick={() => p.onStop(j.id)}><Icon name="stop" size={12} />Dừng</button>
        </div>
      ))}

      <div className="filters">
        <div className="chips">
          <button className={`chip ${p.filter === "all" ? "active" : ""}`} onClick={() => p.onFilter("all")}>
            Tất cả <small>{p.total}</small>
          </button>
          {chips.map((s) => (
            <button key={s} className={`chip ${STATUS_CLASS[s] ?? ""} ${p.filter === s ? "active" : ""}`} onClick={() => p.onFilter(s)}>
              <span className="chip-dot" />{s} <small>{p.summary[s] ?? 0}</small>
            </button>
          ))}
        </div>
        {n > 0 && (
          <span className="sel-chip">
            Đã chọn {n}
            <button className="sel-clear" aria-label="Bỏ chọn" title="Bỏ chọn" onClick={p.onClearSelection}>
              <Icon name="x" size={12} />
            </button>
          </span>
        )}
        <label className="search">
          <Icon name="search" size={13} />
          <input placeholder="Tìm câu, TC_ID…" value={p.search} onChange={(e) => p.onSearch(e.target.value)} />
        </label>
      </div>
    </div>
  );
}
