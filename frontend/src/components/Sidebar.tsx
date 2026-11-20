import type { AudioSet, Health } from "../api";

export type Section = "data" | "block1" | "app" | "report";

interface Props {
  section: Section;
  onSection: (s: Section) => void;
  health: Health | null;
  sets: AudioSet[];
  currentSetId: number | null;
  onSelectSet: (id: number) => void;
  onSettings: () => void;
}

const NAV: { id: Section; label: string; hint: string; disabled?: boolean }[] = [
  { id: "data", label: "Dữ liệu", hint: "Nạp file, chọn sheet" },
  { id: "block1", label: "Sinh audio & Verify", hint: "Khối 1" },
  { id: "app", label: "Test app", hint: "Khối 2 · điện thoại" },
  { id: "report", label: "Báo cáo", hint: "Xuất Excel / CSV" },
];

function Dot({ ok, label, title }: { ok: boolean; label: string; title?: string }) {
  return (
    <div className="status-line" title={title}>
      <span className={`dot ${ok ? "ok" : "bad"}`} />
      {label}
    </div>
  );
}

export function Sidebar({ section, onSection, health, sets, currentSetId, onSelectSet, onSettings }: Props) {
  return (
    <aside className="sidebar">
      <div className="brand">TTS → STT<small>Automation test</small></div>
      <nav>
        {NAV.map((n) => (
          <button
            key={n.id}
            className={`nav-item ${section === n.id ? "active" : ""}`}
            disabled={n.disabled}
            onClick={() => onSection(n.id)}
          >
            <span>{n.label}</span>
            <small>{n.hint}</small>
          </button>
        ))}
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

        
        <button className="nav-item small-btn" onClick={onSettings}>Cài đặt</button>
      </div>
    </aside>
  );
}
