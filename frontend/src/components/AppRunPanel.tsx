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
  passedCount: number;
  /** Rows picked in the Step 2 table (0 = run every row that passed). */
  selectedCount: number;
  onStart: (serial: string, profile: string) => void;
  onExportForm: () => void;
  onExportZip: () => void;
  onResume: (runId: number) => void;
  onSelectRun: (runId: number | null) => void;
}

const runLabel = (r: AppRun) => `#${r.id} · ${r.device_model ?? r.serial} · ${r.created_at.slice(5, 16).replace("T", " ")}`;

/** Step 2 actions, rendered inside the RunBar toolbar: start a run on the left, past runs and exports on the right. */
export function AppRunPanel(p: Props) {
  const ready = p.devices.filter((d) => d.state === "device");
  const [serial, setSerial] = useState<string>("");
  const [profile, setProfile] = useState<string>("");
  useEffect(() => { if (!ready.some((d) => d.serial === serial)) setSerial(ready[0]?.serial ?? ""); }, [ready, serial]);
  useEffect(() => { if (!profile && p.profiles[0]) setProfile(p.profiles[0].name); }, [p.profiles, profile]);

  const run = p.runs.find((r) => r.id === p.runId);
  const pending = run ? (run.summary["Chờ"] ?? 0) + (run.summary["Lỗi thao tác"] ?? 0) : 0;
  const canStart = !!serial && !!profile && !p.busy && p.passedCount > 0;

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
      <button className="btn primary" disabled={!canStart} onClick={() => p.onStart(serial, profile)}
        title={p.passedCount ? "" : "Chạy Khối 1 trước: chỉ câu Đạt mới được test trên app"}>
        <Icon name="play" />Chạy trên app ({p.selectedCount || "tất cả"})
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
        onChange={(e) => p.onSelectRun(e.target.value ? Number(e.target.value) : null)} disabled={!p.runs.length}>
        {!p.runs.length && <option value="">Chưa có lần test</option>}
        {p.runs.map((r) => <option key={r.id} value={r.id}>{runLabel(r)}</option>)}
      </select>
      <button className="btn" disabled={!run || p.busy || pending === 0} onClick={() => run && p.onResume(run.id)}>
        <Icon name="refresh" />Chạy tiếp{pending ? ` (${pending})` : ""}
      </button>
      <Popover buttonClassName="btn" panelLabel="Xuất phiên test" align="right" disabled={!run}
        label={<><Icon name="download" />Xuất<Icon name="chevron" size={13} /></>}>
        {(_open, close) => (
          <div className="menu">
            <button className="menu-item" onClick={() => { close(); p.onExportForm(); }}>
              Excel theo form<small>Kết quả thực tế, KQ ASR, Bằng chứng…</small>
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
