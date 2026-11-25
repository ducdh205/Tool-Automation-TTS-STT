import { useEffect, useRef, useState } from "react";
import { useVirtualizer } from "@tanstack/react-virtual";
import { api, type AppResult, type Item, type WordOp } from "../api";
import { formatPct, renderOps } from "../format";
import { STATUS_CLASS, VERIFY_CLASS } from "../status";
import { Icon } from "./Icon";

const ROW_H = 34;
const NONE: ReadonlySet<number> = new Set();

interface Props {
  items: Item[];
  onPatch: (id: number, patch: { text_tts?: string; enabled?: boolean }) => void;
  /** Block 2: results of the selected app run, keyed by item id. Switches the STT columns to the app's. */
  app?: Map<number, AppResult>;
  /** Show the Sheet column (only worth its width when the set spans several sheets). */
  showSheet?: boolean;
  /** Case selection (ids). Without `onRowSelect` the checkboxes are inert. */
  selected?: ReadonlySet<number>;
  isSelectable?: (it: Item) => boolean;
  onRowSelect?: (index: number, shift: boolean) => void;
  onToggleAll?: () => void;
  /** Step 1: a ⟳ button on rows that have audio. */
  onRegenerate?: (id: number) => void;
}

function HeadCheckbox({ checked, indeterminate, disabled, onChange }:
  { checked: boolean; indeterminate: boolean; disabled: boolean; onChange: () => void }) {
  const ref = useRef<HTMLInputElement>(null);
  useEffect(() => { if (ref.current) ref.current.indeterminate = indeterminate; }, [indeterminate]);
  return <input ref={ref} type="checkbox" aria-label="Chọn tất cả" title="Chọn / bỏ chọn các dòng đang hiển thị"
    checked={checked} disabled={disabled} onChange={onChange} />;
}

function Ops({ ops }: { ops: WordOp[] }) {
  return (
    <span>
      {renderOps(ops).map((s, i) => (
        <span key={i}><span className={`op-${s.kind}`} title={s.title}>{s.text}</span>{" "}</span>
      ))}
    </span>
  );
}

function AppText({ r }: { r: AppResult | undefined }) {
  if (!r) return <span className="muted">chưa test</span>;
  if (r.status === "Lỗi thao tác") return <span className="muted" title={r.log ?? ""}>{r.error}</span>;
  if (r.status === "Chờ") return <span className="muted">chưa test</span>;
  if (!r.ops.length) return <span>{r.app_text || <i className="muted">(app không trả câu)</i>}</span>;
  return <Ops ops={r.ops} />;
}

function SttText({ item }: { item: Item }) {
  if (item.error && item.status === "Lỗi") return <span className="muted" title={item.error}>{item.error}</span>;
  if (!item.ref_text && !item.ops.length) return <span className="muted">—</span>;
  if (!item.ops.length) return <span>{item.ref_text}</span>;
  return <Ops ops={item.ops} />;
}

function EditableText({ item, onSave, readOnly }: { item: Item; onSave: (t: string) => void; readOnly?: boolean }) {
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
      className={`cell-text ${item.text_tts ? "" : "muted"}`}
      title={readOnly ? item.text_tts ?? item.text_raw : "Nhấp đúp để sửa câu đọc"}
      onDoubleClick={() => { if (readOnly) return; setValue(item.text_tts ?? item.text_raw); setEditing(true); }}
    >
      {/* A row without a reading text still shows what the sheet said, dimmed. */}
      {item.text_tts ?? item.text_raw}
    </span>
  );
}

function PlayButton({ item }: { item: Item }) {
  if (!item.audio_path) return <span className="play-slot" />;
  // The file name is the cache key (text+voice+attempt): it changes whenever the audio does.
  const version = item.audio_path.split(/[\\/]/).pop() ?? "";
  const play = () => { void new Audio(api.audioUrl(item.id, version)).play(); };
  return <button className="icon-btn play-slot" title="Nghe audio" onClick={play}><Icon name="play" size={12} /></button>;
}

function columns(app: boolean, sheet: boolean): string {
  return [
    "28px", "minmax(90px, 130px)", sheet && "minmax(90px, 150px)", "minmax(180px, 1fr)", "minmax(180px, 1.2fr)",
    "84px", app && "92px", "128px", !app && "52px",
  ].filter(Boolean).join(" ");
}

export function ItemTable({
  items, onPatch, app, showSheet = false, selected = NONE, isSelectable = () => false, onRowSelect, onToggleAll, onRegenerate,
}: Props) {
  const selectable = items.filter(isSelectable);
  const picked = selectable.filter((it) => selected.has(it.id)).length;
  const parentRef = useRef<HTMLDivElement>(null);
  const v = useVirtualizer({
    count: items.length,
    getScrollElement: () => parentRef.current,
    estimateSize: () => ROW_H,
    // Rows grow to fit wrapped text; fall back to the base height where layout is unavailable (tests).
    measureElement: (el) => Math.max(ROW_H, el.getBoundingClientRect().height),
    overscan: 12,
    initialRect: { width: 1200, height: 600 },
  });
  const grid = { gridTemplateColumns: columns(!!app, showSheet) };
  const verdict = app ? "Sai" : "Audio không đạt";

  return (
    <div className={`table ${app ? "app" : ""}`}>
      <div className="row head" style={grid}>
        <span>
          <HeadCheckbox
            checked={picked > 0 && picked === selectable.length}
            indeterminate={picked > 0 && picked < selectable.length}
            disabled={!onToggleAll || selectable.length === 0}
            onChange={() => onToggleAll?.()}
          />
        </span>
        <span>TC_ID</span>
        {showSheet && <span>Sheet</span>}
        <span>Câu đọc</span>
        <span>{app ? "Text app" : "Text STT tham chiếu"}</span>
        <span className="num hint" title={`WER: tỉ lệ lỗi theo từ, dùng để chấm. Đạt khi WER ≤ ngưỡng, vượt ngưỡng thì ${verdict}.\nCER (số nhỏ): lỗi theo ký tự, chỉ để tham khảo. CER thấp mà WER cao thường là sai dấu.`}>
          WER <small>CER</small>
        </span>
        {app && <span className="hint" title="Kết quả verify audio ở Bước 1 (STT tham chiếu). Câu chưa verify hoặc không đạt vẫn được test trên app.">Verify</span>}
        <span>Trạng thái</span>
        {!app && <span />}
      </div>
      <div ref={parentRef} className="table-body">
        <div style={{ height: v.getTotalSize(), position: "relative" }}>
          {v.getVirtualItems().map((vr) => {
            const it = items[vr.index];
            const ar = app?.get(it.id);
            const wer = app ? ar?.wer : it.wer;
            const cer = app ? ar?.cer : it.cer;
            const rewritten = !!it.text_tts && it.text_tts !== it.text_raw;
            return (
              <div
                key={it.id}
                data-row
                data-index={vr.index}
                ref={v.measureElement}
                className={`row ${it.enabled ? "" : "disabled"}`}
                style={{ ...grid, position: "absolute", top: 0, left: 0, right: 0, minHeight: ROW_H, transform: `translateY(${vr.start}px)` }}
              >
                <span>
                  <input
                    type="checkbox"
                    aria-label={`Chọn ${it.tc_id}`}
                    checked={selected.has(it.id)}
                    disabled={!onRowSelect || !isSelectable(it)}
                    onChange={() => {}}
                    onClick={(e) => onRowSelect?.(vr.index, e.shiftKey)}
                  />
                </span>
                <span className="cell-tc" title={`${it.sheet} · ${it.tc_id}${it.turn ? ` · lượt ${it.turn}` : ""} · dòng ${it.source_row}`}>
                  <span className="cell-wrap">{it.tc_id}</span>
                  {/* Only later turns are marked: a plain TC_ID reads as its first (often only) turn. */}
                  {it.turn && it.turn !== "1" && <small className="muted">·{it.turn}</small>}
                </span>
                {showSheet && <span className="cell-wrap muted" title={it.sheet}>{it.sheet}</span>}
                <span className="cell-tts">
                  <PlayButton item={it} />
                  <EditableText item={it} readOnly={!!app} onSave={(t) => onPatch(it.id, { text_tts: t })} />
                  {rewritten && (
                    <span className="raw-mark" title={`Câu gốc: ${it.text_raw}`} aria-label={`Câu gốc: ${it.text_raw}`}>
                      <Icon name="pencil" size={11} />
                    </span>
                  )}
                </span>
                <span className="cell-wrap">{app ? <AppText r={ar} /> : <SttText item={it} />}</span>
                <span className="num">{formatPct(wer)}{cer != null && <small className="muted cer">{formatPct(cer)}</small>}</span>
                {app && (
                  <span>
                    <span className={`badge ${VERIFY_CLASS[it.verify] ?? ""}`} title={`Verify audio: ${it.verify}`}>{it.verify}</span>
                  </span>
                )}
                <span>
                  {app ? (
                    <span className={`badge ${STATUS_CLASS[ar?.status ?? ""] ?? ""}`} title={ar?.error ?? ar?.status ?? ""}>
                      {ar?.status ?? "—"}
                    </span>
                  ) : (
                    <span className={`badge ${STATUS_CLASS[it.status] ?? ""}`} title={it.skip_reason ?? it.error ?? it.status}>
                      {it.status}{it.attempts > 1 ? ` ·${it.attempts}x` : ""}
                    </span>
                  )}
                </span>
                {!app && (
                  <span className="row-actions">
                    {onRegenerate && it.audio_path && (
                      <button className="icon-btn" title="Sinh lại audio" onClick={() => onRegenerate(it.id)}>
                        <Icon name="refresh" size={13} />
                      </button>
                    )}
                    <button
                      className={`icon-btn ${it.enabled ? "" : "off"}`}
                      title={it.text_tts ? "Bật/tắt câu này" : "Sửa câu đọc để bật lại"}
                      disabled={!it.text_tts}
                      onClick={() => onPatch(it.id, { enabled: !it.enabled })}
                    >
                      <Icon name="power" size={13} />
                    </button>
                  </span>
                )}
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
