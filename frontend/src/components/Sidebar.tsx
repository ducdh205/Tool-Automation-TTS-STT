import type { AudioSet, DeviceStatus, Health } from "../api";
import { Icon } from "./Icon";
import { TestbenchPanel } from "./TestbenchPanel";

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
  /** Called once the user confirmed wiping all output data; omit to hide the button. */
  onClearAll?: () => void;
  /** Why deleting is not possible now (a job is running): the buttons are disabled with this tooltip. */
  deleteLocked?: string | null;
  /** Latest /api/device poll (null until the first answer). */
  device?: DeviceStatus | null;
}

const NAV: { id: Section; label: string; hint: string }[] = [
  { id: "step1", label: "Bước 1 — Audio", hint: "Nạp file · Sinh audio · Verify" },
  { id: "step2", label: "Bước 2 — Test app", hint: "Chạy trên điện thoại · Xuất phiên" },
];
const STEP2_LOCKED = "Cần sinh audio ở Bước 1 trước";

export function Sidebar({
  section, onSection, step2Ready, health, sets, currentSetId, onSelectSet, onDeleteSet, onClearAll, deleteLocked = null,
  device = null,
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
              title={locked ? STEP2_LOCKED : n.hint}
              onClick={() => onSection(n.id)}
            >
              {n.label}
            </button>
          );
        })}
      </nav>

      <div className="side-block">
        <div className="side-title-row">
          <div className="side-title">Bộ audio</div>
          {onClearAll && (
            <button
              className="icon-btn clear-all"
              aria-label="Xóa toàn bộ dữ liệu"
              title={deleteLocked ?? "Xóa toàn bộ dữ liệu output"}
              disabled={!!deleteLocked}
              onClick={() => {
                if (window.confirm(`Xóa toàn bộ dữ liệu output (${sets.length} bộ audio)?\n\n`
                  + "Audio đã sinh, các lần test app, ảnh chụp màn hình, báo cáo và file đã nạp sẽ bị xóa, "
                  + "không hoàn tác được.\nCài đặt và hồ sơ app được giữ lại.")) {
                  onClearAll();
                }
              }}
            >
              <Icon name="trash" size={13} />
              <span>Xóa tất cả</span>
            </button>
          )}
        </div>
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

      <TestbenchPanel health={health} device={device} jobRunning={!!health?.job} />
    </aside>
  );
}
