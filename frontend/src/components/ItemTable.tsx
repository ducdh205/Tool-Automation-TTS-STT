import { useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { api, type Item } from "../api";
import { formatPct, renderOps } from "../format";

const ROW_H = 34;

interface Props {
  items: Item[];
  onPatch: (id: number, patch: { text_tts?: string; enabled?: boolean }) => void;
}

const STATUS_CLASS: Record<string, string> = {
  "Chờ": "st-pending", "Không áp dụng": "st-skip", "Đã sinh audio": "st-gen",
  "Đạt": "st-pass", "Audio không đạt": "st-fail", "Lỗi": "st-error",
};

function SttText({ item }: { item: Item }) {
  if (item.error && item.status === "Lỗi") return <span className="muted" title={item.error}>{item.error}</span>;
  if (!item.ref_text && !item.ops.length) return <span className="muted">—</span>;
  if (!item.ops.length) return <span>{item.ref_text}</span>;
  return (
    <span>
      {renderOps(item.ops).map((s, i) => (
        <span key={i}><span className={`op-${s.kind}`} title={s.title}>{s.text}</span>{" "}</span>
      ))}
    </span>
  );
}

function EditableText({ item, onSave }: { item: Item; onSave: (t: string) => void }) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(item.text_tts ?? "");
  if (editing) {
    return (
      <input
        autoFocus
        className="cell-input"
        value={value}
        onChange={(e) => setValue(e.target.value)}
        onBlur={() => setEditing(false)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && value.trim()) { onSave(value.trim()); setEditing(false); }
          if (e.key === "Escape") setEditing(false);
        }}
      />
    );
  }
  return (
    <span
      className={item.text_tts ? "" : "muted"}
      title="Nhấp đúp để sửa câu đọc"
      onDoubleClick={() => { setValue(item.text_tts ?? item.text_raw); setEditing(true); }}
    >
      {item.text_tts ?? "—"}
    </span>
  );
}

function PlayButton({ item }: { item: Item }) {
  if (!item.audio_path) return <span className="muted">·</span>;
  // The file name is the cache key (text+voice+attempt): it changes whenever the audio does.
  const version = item.audio_path.split(/[\\/]/).pop() ?? "";
  const play = () => { void new Audio(api.audioUrl(item.id, version)).play(); };
  return <button className="icon-btn" title="Nghe audio" onClick={play}>▶</button>;
}

export function ItemTable({ items, onPatch }: Props) {
  const parentRef = useRef<HTMLDivElement>(null);
  const v = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_H,
    overscan: 12,
    initialRect: { width: 1200, height: 600 },
  });

  return (
    <div className="table">
      <div className="row head">
        <span /><span>#</span><span>Sheet</span><span>TC_ID</span><span>Lượt</span>
        <span>Câu gốc</span><span>Câu đọc</span><span /><span>Text STT tham chiếu</span>
        <span className="num">WER</span><span className="num">CER</span><span>Trạng thái</span>
      </div>
      <div ref={parentRef} className="table-body">
        <div style={{ height: v.getTotalSize(), position: "relative" }}>
          {v.getVirtualItems().map((vr) => {
            const it = items[vr.index];
            return (
              <div
                key={it.id}
                data-row
                className={`row ${it.enabled ? "" : "disabled"}`}
                style={{ position: "absolute", top: 0, left: 0, right: 0, height: ROW_H, transform: `translateY(${vr.start}px)` }}
              >
                <span>
                  <input
                    type="checkbox"
                    checked={!!it.enabled}
                    disabled={!it.text_tts}
                    title={it.text_tts ? "Bật/tắt câu này" : "Sửa câu đọc để bật lại"}
                    onChange={(e) => onPatch(it.id, { enabled: e.target.checked })}
                  />
                </span>
                <span className="muted">{vr.index + 1}</span>
                <span className="ellipsis" title={it.sheet}>{it.sheet}</span>
                <span className="ellipsis" title={it.tc_id}>{it.tc_id}</span>
                <span>{it.turn}</span>
                <span className="ellipsis" title={it.text_raw}>{it.text_raw}</span>
                <span className="ellipsis cell-tts"><EditableText item={it} onSave={(t) => onPatch(it.id, { text_tts: t })} /></span>
                <span><PlayButton item={it} /></span>
                <span className="ellipsis"><SttText item={it} /></span>
                <span className="num">{formatPct(it.wer)}</span>
                <span className="num">{formatPct(it.cer)}</span>
                <span>
                  <span className={`badge ${STATUS_CLASS[it.status] ?? ""}`} title={it.skip_reason ?? it.error ?? it.status}>
                    {it.status}{it.attempts > 1 ? ` ·${it.attempts}x` : ""}
                  </span>
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
