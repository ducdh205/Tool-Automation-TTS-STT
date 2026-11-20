import { useEffect, useState } from "react";
import type { AppProfile, AppRun, DeviceInfo } from "../api";
import { formatPct } from "../format";

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

function rate(s: Record<string, number>): number | null {
  const ok = s["Đúng"] ?? 0;
  const tested = ok + (s["Sai"] ?? 0);
  return tested ? ok / tested : null;
}

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
    <div className="apprun">
      <div className="toolbar">
        <label className="inline">Thiết bị
          <select value={serial} onChange={(e) => setSerial(e.target.value)} disabled={!ready.length}>
            {!ready.length && <option value="">Chưa có thiết bị</option>}
            {ready.map((d) => <option key={d.serial} value={d.serial}>{d.model ?? d.serial}</option>)}
          </select>
        </label>
        <label className="inline">Hồ sơ app
          <select value={profile} onChange={(e) => setProfile(e.target.value)}>
            {p.profiles.map((x) => <option key={x.name}>{x.name}</option>)}
          </select>
        </label>
        <button className="btn primary" disabled={!canStart} onClick={() => p.onStart(serial, profile)}
          title={p.passedCount ? "" : "Chạy Khối 1 trước: chỉ câu Đạt mới được test trên app"}>
          Chạy trên app ({p.selectedCount || "tất cả"})
        </button>
        <span className="spacer" />
        <label className="inline">Lần test
          <select value={p.runId ?? ""} onChange={(e) => p.onSelectRun(e.target.value ? Number(e.target.value) : null)}>
            <option value="">—</option>
            {p.runs.map((r) => <option key={r.id} value={r.id}>#{r.id} · {r.device_model ?? r.serial} · {r.created_at.slice(5, 16).replace("T", " ")}</option>)}
          </select>
        </label>
        <button className="btn" disabled={!run || p.busy || pending === 0} onClick={() => run && p.onResume(run.id)}>
          Chạy tiếp{pending ? ` (${pending})` : ""}
        </button>
        <button className="btn" disabled={!run} onClick={p.onExportForm}
          title="File Excel theo form testcase: cột Kết quả thực tế, KQ ASR, Bằng chứng…">
          Xuất Excel (form)
        </button>
        <button className="btn" disabled={!run} onClick={p.onExportZip}
          title="Mỗi testcase một folder: kết quả, log, ảnh chụp, audio">
          Xuất zip phiên
        </button>
      </div>
      <div className="small muted">
        {run ? (
          <span>
            <b className="accent">Đúng {formatPct(rate(run.summary))}</b>
            {" · "}Đúng {run.summary["Đúng"] ?? 0} · Sai {run.summary["Sai"] ?? 0} · Lỗi thao tác {run.summary["Lỗi thao tác"] ?? 0} · Chờ {run.summary["Chờ"] ?? 0}
            {run.app_version ? ` · app ${run.app_version}` : ""}
          </span>
        ) : (
          <span>{p.passedCount} câu Đạt sẵn sàng · Đặt âm lượng loa máy tính ~70%, điện thoại cách loa 20–40 cm, phòng yên tĩnh.</span>
        )}
      </div>
    </div>
  );
}
