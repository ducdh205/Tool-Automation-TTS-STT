import type { AudioSet, DeviceStatus, Health } from "../api";
import { Icon } from "./Icon";
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
  /** Called once the user confirmed deleting a set; omit to hide the delete buttons. */
  onDeleteSet?: (id: number) => void;
  /** Why deleting is not possible now (a job is running): the buttons are disabled with this tooltip. */
  deleteLocked?: string | null;
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
  section, onSection, step2Ready, health, sets, currentSetId, onSelectSet, onDeleteSet, deleteLocked = null, device = null,
}: Props) {
  const adb = adbStatus(device);
  const stt = { level: (health?.wyoming ? "ok" : "bad") as Level, label: "STT", title: health?.wyoming
    ? "STT tham chiếu (wyoming) sẵn sàng" : `STT tham chiếu (wyoming) chưa chạy${health?.wyoming_error ? `: ${health.wyoming_error}` : ""}` };
  const gpu = { level: (health?.gpu ? "ok" : "warn") as Level, label: health?.gpu ? "GPU" : "CPU",
    title: health?.gpu ? "TTS chạy GPU" : "TTS chạy CPU (chậm hơn)" };
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
              title={locked ? STEP2_LOCKED : n.hint}
              onClick={() => onSection(n.id)}
            >
              {n.label}
            </button>
          );
        })}
      </nav>

      <div className="side-block">
        <div className="side-title">Bộ audio</div>
        {sets.length === 0 && <div className="muted small side-note">Chưa có — nạp file để tạo</div>}
        <div className="set-list">
          {sets.map((s) => {
            const total = Object.values(s.summary).reduce((a, b) => a + b, 0);
            const passed = s.summary["Đạt"] ?? 0;
            return (
              <div key={s.id} className="set-row">
                <button
                  className={`set-item ${s.id === currentSetId ? "active" : ""}`}
                  onClick={() => onSelectSet(s.id)}
                  title={`${s.source_file} · ${s.sheets.join(", ")}\n${passed}/${total} câu Đạt`}
                >
                  <span className="set-line">
                    <span className="ellipsis">{s.name}</span>
                    <small>{total} câu</small>
                  </span>
                  <span className="set-bar"><span style={{ width: total ? `${(passed / total) * 100}%` : 0 }} /></span>
                </button>
                {onDeleteSet && (
                  <button
                    className="icon-btn set-delete"
                    aria-label={`Xóa bộ ${s.name}`}
                    title={deleteLocked ?? "Xóa bộ audio"}
                    disabled={!!deleteLocked}
                    onClick={() => {
                      if (window.confirm(`Xóa bộ "${s.name}" (${total} câu)?\n\n`
                        + "Audio, các lần test app và kết quả của bộ này sẽ bị xóa, không hoàn tác được.")) {
                        onDeleteSet(s.id);
                      }
                    }}
                  >
                    <Icon name="trash" size={14} />
                  </button>
                )}
              </div>
            );
          })}
        </div>
      </div>

      <div className="side-footer">
        <div className="status-row">
          <StatusChip {...stt} />
          <StatusChip {...gpu} />
          <StatusChip level={adb.level} title={adb.title ?? adb.label} label={adbShort(device)} />
          <span className="spacer" />
          <ThemeSwitch />
        </div>
        {/* Spell out only what needs the user: STT blocks Verify; a plugged-in phone waiting for permission. */}
        {stt.level !== "ok" && <Dot level="bad" label="STT tham chiếu chưa chạy" title={stt.title} />}
        {adb.level === "warn" && <Dot {...adb} />}
      </div>
    </aside>
  );
}

function StatusChip({ level, label, title }: { level: Level; label: string; title?: string }) {
  return (
    <span className="status-chip" title={title}>
      <span className={`dot ${level}`} />
      <span className="ellipsis">{label}</span>
    </span>
  );
}

/** Chip text for ADB: the phone's name when there is one. */
function adbShort(s: DeviceStatus | null): string {
  const d = s?.devices.find((x) => x.state === "device") ?? s?.devices[0];
  return d ? d.model ?? d.serial : "ADB";
}
