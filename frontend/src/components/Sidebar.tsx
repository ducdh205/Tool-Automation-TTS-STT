import { useRef } from "react";
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
  /** Called when the user asks to export a set as a zip; omit to hide the export buttons. */
  onExportSet?: (id: number) => void;
  /** Called with the zip the user picked; omit to hide the import button. */
  onImportSet?: (file: File) => void;
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
  section, onSection, step2Ready, health, sets, currentSetId, onSelectSet, onDeleteSet, onExportSet, onImportSet,
  onClearAll, deleteLocked = null, device = null,
}: Props) {
  const importInput = useRef<HTMLInputElement>(null);
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
          <div className="side-actions">
            {onImportSet && (
              <>
                <button
                  className="icon-btn side-action"
                  aria-label="Nạp bộ audio"
                  title={deleteLocked ?? "Nạp bộ audio từ file .zip đã xuất"}
                  disabled={!!deleteLocked}
                  onClick={() => importInput.current?.click()}
                >
                  <Icon name="upload" size={13} />
                </button>
                <input
                  ref={importInput}
                  type="file"
                  accept=".zip"
                  hidden
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    e.target.value = ""; // the same file can be picked again
                    if (file) onImportSet(file);
                  }}
                />
              </>
            )}
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
                {onExportSet && (
                  <button
                    className="icon-btn set-export"
                    aria-label={`Xuất bộ ${s.name}`}
                    title={deleteLocked ?? "Xuất bộ audio ra file .zip"}
                    disabled={!!deleteLocked}
                    onClick={() => onExportSet(s.id)}
                  >
                    <Icon name="download" size={14} />
                  </button>
                )}
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
