import type { AudioSet, DeviceStatus, Health } from "../api";
import { ThemeSwitch } from "./ThemeSwitch";

export type Section = "step1" | "step2";

interface Props {
  section: Section;
  onSection: (s: Section) => void;
  /** Step 2 needs at least one row that passed Block 1. */
  step2Ready: boolean;
  health: Health | null;
  sets: AudioSet[];
  currentSetId: number | null;
  onSelectSet: (id: number) => void;
  onSettings: () => void;
  /** Latest /api/device poll (null until the first answer). */
  device?: DeviceStatus | null;
}

const NAV: { id: Section; label: string; hint: string }[] = [
  { id: "step1", label: "Bước 1 — Audio", hint: "Nạp file · Sinh audio · Verify" },
  { id: "step2", label: "Bước 2 — Test app", hint: "Chạy trên điện thoại · Xuất phiên" },
];
const STEP2_LOCKED = "Cần ít nhất một câu Đạt ở Bước 1";

type Level = "ok" | "warn" | "bad" | "off";

function Dot({ ok, level, label, title }: { ok?: boolean; level?: Level; label: string; title?: string }) {
  return (
    <div className="status-line" title={title}>
      <span className={`dot ${level ?? (ok ? "ok" : "bad")}`} />
      <span className="ellipsis">{label}</span>
    </div>
  );
}

const STATE_HINT: Record<string, string> = { unauthorized: "chưa cho phép", offline: "mất kết nối" };

/** One-line ADB summary for the sidebar footer: prefers an online device, names it by model (else serial). */
export function adbStatus(s: DeviceStatus | null): { level: Level; label: string; title?: string } {
  if (!s) return { level: "off", label: "ADB: đang kiểm tra…" };
  if (!s.adb) return { level: "bad", label: "ADB: không tìm thấy adb", title: s.error ?? undefined };
  if (s.devices.length === 0) return { level: "bad", label: "ADB: chưa có thiết bị", title: "Cắm cáp USB và bật Gỡ lỗi USB" };
  const d = s.devices.find((x) => x.state === "device") ?? s.devices[0];
  const extra = s.devices.length > 1 ? ` (+${s.devices.length - 1})` : "";
  const online = d.state === "device";
  return {
    level: online ? "ok" : "warn",
    label: `ADB · ${d.model ?? d.serial}${extra}${online ? "" : ` — ${STATE_HINT[d.state] ?? d.state}`}`,
    title: s.devices.map((x) => `${x.model ?? "Android"} · ${x.serial} · ${x.state}`).join("\n"),
  };
}

export function Sidebar({
  section, onSection, step2Ready, health, sets, currentSetId, onSelectSet, onSettings, device = null,
}: Props) {
  return (
    <aside className="sidebar">
      <div className="brand">TTS → STT<small>Automation test</small></div>
      <nav>
        {NAV.map((n) => {
          const locked = n.id === "step2" && !step2Ready;
          return (
          <button
            key={n.id}
            className={`nav-item ${section === n.id ? "active" : ""}`}
            disabled={locked}
            title={locked ? STEP2_LOCKED : undefined}
            onClick={() => onSection(n.id)}
          >
            <span>{n.label}</span>
            <small>{n.hint}</small>
          </button>
          );
        })}
      </nav>

      <div className="side-block">
        <div className="side-title">Bộ audio</div>
        {sets.length === 0 && <div className="muted small">Chưa có — nạp file để tạo</div>}
        <div className="set-list">
          {sets.map((s) => (
            <button
              key={s.id}
              className={`set-item ${s.id === currentSetId ? "active" : ""}`}
              onClick={() => onSelectSet(s.id)}
              title={`${s.source_file} · ${s.sheets.join(", ")}`}
            >
              <span className="ellipsis">{s.name}</span>
              <small>{Object.values(s.summary).reduce((a, b) => a + b, 0)} câu</small>
            </button>
          ))}
        </div>
      </div>

      <div className="side-footer">
        <Dot ok={!!health?.wyoming} label="STT tham chiếu (wyoming)" title={health?.wyoming_error ?? undefined} />
        <Dot ok={!!health?.gpu} label={health?.gpu ? "GPU" : "TTS chạy CPU"} />
        <Dot {...adbStatus(device)} />
        <ThemeSwitch />
        <button className="nav-item small-btn" onClick={onSettings}>Cài đặt</button>
      </div>
    </aside>
  );
}
