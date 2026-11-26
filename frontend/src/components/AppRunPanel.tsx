import { useEffect, useState } from "react";
import type { AppProfile, AppRun, DeviceInfo } from "../api";
import { Icon } from "./Icon";
import { Popover } from "./Popover";

interface Props {
  devices: DeviceInfo[];
  profiles: AppProfile[];
  runs: AppRun[];
  runId: number | null;
  busy: boolean;
  /** Rows with audio (verified or not): what a run without a selection tests. */
  readyCount: number;
  /** Rows picked in the Step 2 table (0 = run every row with audio). */
  selectedCount: number;
  onStart: (serial: string, profile: string) => void;
  /** Saves an edited profile (the pause between sentences lives on the app profile). */
  onSaveProfile?: (profile: AppProfile) => Promise<void>;
  onExportForm: () => void;
  onExportZip: () => void;
  onResume: (runId: number) => void;
  /** Runs the picked cases again inside the selected run (its other results stay). */
  onRerun?: (runId: number, serial: string) => void;
  onSelectRun: (runId: number | null) => void;
}

/** Same upper bound as the backend (ProfileIn.between_delay_s). */
const MAX_GAP_S = 60;

const RECENT_RUNS = 5;
const MORE = "__more__";
const runLabel = (r: AppRun) => `#${r.id} · ${r.device_model ?? r.serial} · ${r.created_at.slice(5, 16).replace("T", " ")}`;

/** Step 2 actions, rendered inside the RunBar toolbar: start a run on the left, past runs and exports on the right. */
export function AppRunPanel(p: Props) {
  const ready = p.devices.filter((d) => d.state === "device");
  const [serial, setSerial] = useState<string>("");
  const [profile, setProfile] = useState<string>("");
  useEffect(() => { if (!ready.some((d) => d.serial === serial)) setSerial(ready[0]?.serial ?? ""); }, [ready, serial]);
  useEffect(() => { if (!profile && p.profiles[0]) setProfile(p.profiles[0].name); }, [p.profiles, profile]);

  const current = p.profiles.find((x) => x.name === profile);
  const savedGap = String(current?.between_delay_s ?? 0);
  const [gap, setGap] = useState<string | null>(null); // null = show the saved value
  useEffect(() => setGap(null), [profile, savedGap]);
  const gapValue = gap ?? savedGap;
  const gapValid = gapValue.trim() !== "" && Number(gapValue) >= 0 && Number(gapValue) <= MAX_GAP_S;
  const commitGap = async () => {
    if (gap === null || !current || !p.onSaveProfile) return;
    if (!gapValid || Number(gap) === Number(savedGap)) {
      setGap(null);
      return;
    }
    try {
      await p.onSaveProfile({ ...current, between_delay_s: Number(gap) });
    } catch {
      setGap(null); // the caller reports the error; fall back to the saved value
    }
  };

  const run = p.runs.find((r) => r.id === p.runId);
  const pending = run ? (run.summary["Chờ"] ?? 0) + (run.summary["Lỗi thao tác"] ?? 0) : 0;
  const canStart = !!serial && !!profile && !p.busy && p.readyCount > 0;
  // Picking cases while a run is shown means "run these again": keep them in that run.
  const rerun = !!run && p.selectedCount > 0 && !!p.onRerun;
  const samePhone = !!run && run.serial === serial;

  // Past runs: only the newest few until asked for more; the selected run always stays listed.
  const [showAllRuns, setShowAllRuns] = useState(false);
  const shownRuns = showAllRuns ? p.runs : p.runs.filter((r, i) => i < RECENT_RUNS || r.id === p.runId);
  const hiddenRuns = p.runs.length - shownRuns.length;

  return (
    <>
      {/* One phone is the usual case and the device panel already names it: only ask when there is a choice. */}
      {ready.length === 0 && <span className="muted small">Chưa có thiết bị</span>}
      {ready.length > 1 && (
        <select className="compact-select" aria-label="Thiết bị" value={serial} onChange={(e) => setSerial(e.target.value)}>
          {ready.map((d) => <option key={d.serial} value={d.serial}>{d.model ?? d.serial}</option>)}
        </select>
      )}
      <select className="compact-select" aria-label="Hồ sơ app" title="Hồ sơ app" value={profile}
        onChange={(e) => setProfile(e.target.value)}>
        {p.profiles.map((x) => <option key={x.name}>{x.name}</option>)}
      </select>
      {p.onSaveProfile && (
        <label className="gap-field" title="Thời gian nghỉ sau mỗi câu trước khi phát câu tiếp theo (lưu vào hồ sơ app)">
          <span>Nghỉ giữa câu</span>
          <input type="number" min={0} max={MAX_GAP_S} step={0.5} aria-label="Nghỉ giữa các câu (giây)"
            aria-invalid={!gapValid} value={gapValue} disabled={p.busy || !current}
            onChange={(e) => setGap(e.target.value)} onBlur={() => void commitGap()}
            onKeyDown={(e) => {
              if (e.key === "Enter") e.currentTarget.blur();
              if (e.key === "Escape") setGap(null);
            }} />
          <span>s</span>
        </label>
      )}
      {rerun && run && (
        <button className="btn primary" disabled={!canStart || !samePhone}
          onClick={() => p.onRerun?.(run.id, serial)}
          title={samePhone
            ? `Chạy lại ${p.selectedCount} case đã chọn trong lần test #${run.id}; kết quả các case khác giữ nguyên, kết quả cũ lưu vào lịch sử`
            : `Lần test #${run.id} chạy trên máy ${run.device_model ?? run.serial}: chọn máy đó, hoặc tạo lần test mới`}>
          <Icon name="refresh" />Chạy lại ({p.selectedCount}) vào #{run.id}
        </button>
      )}
      <button className={`btn ${rerun ? "" : "primary"}`} disabled={!canStart} onClick={() => p.onStart(serial, profile)}
        title={p.readyCount ? (rerun ? "Tạo lần test mới chỉ gồm các case đã chọn" : "") : "Sinh audio ở Khối 1 trước"}>
        <Icon name="play" />{rerun ? `Lần test mới (${p.selectedCount})` : `Chạy trên app (${p.selectedCount || "tất cả"})`}
      </button>
      <Popover iconOnly buttonClassName="info-btn" panelLabel="Chuẩn bị trước khi chạy" label={<Icon name="info" />}>
        {() => (
          <div className="tip">
            Đặt âm lượng loa máy tính ~70%, điện thoại cách loa 20–40 cm, phòng yên tĩnh.
          </div>
        )}
      </Popover>
      <span className="spacer" />
      <select className="compact-select" aria-label="Lần test" title="Lần test" value={p.runId ?? ""}
        onChange={(e) => {
          if (e.target.value === MORE) return setShowAllRuns(true);
          setShowAllRuns(false);
          p.onSelectRun(e.target.value ? Number(e.target.value) : null);
        }} disabled={!p.runs.length}>
        {!p.runs.length && <option value="">Chưa có lần test</option>}
        {shownRuns.map((r) => <option key={r.id} value={r.id}>{runLabel(r)}</option>)}
        {hiddenRuns > 0 && <option value={MORE}>Xem thêm ({hiddenRuns} lần test cũ hơn)…</option>}
      </select>
      <button className="btn" disabled={!run || p.busy || pending === 0} onClick={() => run && p.onResume(run.id)}>
        <Icon name="refresh" />Chạy tiếp{pending ? ` (${pending})` : ""}
      </button>
      <Popover buttonClassName="btn" panelLabel="Xuất phiên test" align="right" disabled={!run}
        label={<><Icon name="download" />Xuất<Icon name="chevron" size={13} /></>}>
        {(_open, close) => (
          <div className="menu">
            <button className="menu-item" onClick={() => { close(); p.onExportForm(); }}>
              Excel kết quả<small>File input gốc + cột Text app, Kết quả, Ghi chú, Ảnh</small>
            </button>
            <button className="menu-item" onClick={() => { close(); p.onExportZip(); }}>
              Zip phiên…<small>Mỗi testcase một folder: kết quả, log, ảnh, audio</small>
            </button>
          </div>
        )}
      </Popover>
    </>
  );
}
