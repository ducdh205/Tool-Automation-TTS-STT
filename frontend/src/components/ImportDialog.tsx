import { useState } from "react";
import { api, type InspectResult } from "../api";

interface Props {
  onClose: () => void;
  onCreated: (setId: number) => void;
}

export function ImportDialog({ onClose, onCreated }: Props) {
  const [info, setInfo] = useState<InspectResult | null>(null);
  const [fileName, setFileName] = useState("");
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [name, setName] = useState("");
  const [textCol, setTextCol] = useState("");
  const [idCol, setIdCol] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const onFile = async (f: File | undefined) => {
    if (!f) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.inspect(f);
      setInfo(r);
      setFileName(f.name);
      setName(f.name.replace(/\.(xlsx|csv|xlsm)$/i, ""));
      setPicked(new Set());
      setTextCol(r.columns[0] ?? "");
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  };

  const formSheets = info?.sheets.filter((s) => s.is_testcase && s.item_count > 0) ?? [];
  const total = formSheets.filter((s) => picked.has(s.name)).reduce((a, s) => a + s.item_count, 0);
  const toggle = (n: string) => {
    const next = new Set(picked);
    if (next.has(n)) next.delete(n); else next.add(n);
    setPicked(next);
  };

  const create = async () => {
    if (!info) return;
    setBusy(true);
    setError(null);
    try {
      const body = info.is_form
        ? { file_id: info.file_id, sheets: [...picked], name }
        : {
            file_id: info.file_id,
            sheets: info.sheets[0] ? [info.sheets[0].name] : [],
            name,
            mapping: { text_col: textCol, id_col: idCol || null },
          };
      const r = await api.createSet(body);
      onCreated(r.id);
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  };

  const canCreate = !!info && !busy && !!name.trim() && (info.is_form ? picked.size > 0 : !!textCol);

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <header>
          <h2>Nạp file testcase</h2>
          <button className="icon-btn" onClick={onClose}>✕</button>
        </header>
        <label className="file-drop">
          <input type="file" accept=".xlsx,.xlsm,.csv" onChange={(e) => onFile(e.target.files?.[0])} />
          {fileName ? <b>{fileName}</b> : <span>Chọn file .xlsx hoặc .csv</span>}
        </label>

        {info?.is_form && (
          <>
            <div className="row-between">
              <span className="muted small">Form testcase 36 cột · chọn sheet tính năng</span>
              <button
                className="link-btn"
                onClick={() => setPicked(picked.size === formSheets.length ? new Set() : new Set(formSheets.map((s) => s.name)))}
              >
                {picked.size === formSheets.length ? "Bỏ chọn" : "Chọn tất cả"}
              </button>
            </div>
            <div className="sheet-list">
              {formSheets.map((s) => (
                <label key={s.name} className="sheet-item">
                  <input type="checkbox" checked={picked.has(s.name)} onChange={() => toggle(s.name)} />
                  <span className="ellipsis">{s.name}</span>
                  <small>{s.item_count}</small>
                </label>
              ))}
            </div>
          </>
        )}

        {info && !info.is_form && (
          <div className="mapping">
            <span className="muted small">File không theo form testcase · chọn cột</span>
            <label>Cột câu nói
              <select value={textCol} onChange={(e) => setTextCol(e.target.value)}>
                {info.columns.map((c) => <option key={c}>{c}</option>)}
              </select>
            </label>
            <label>Cột mã (tùy chọn)
              <select value={idCol} onChange={(e) => setIdCol(e.target.value)}>
                <option value="">— số dòng —</option>
                {info.columns.map((c) => <option key={c}>{c}</option>)}
              </select>
            </label>
          </div>
        )}

        {info && (
          <label className="field">Tên bộ audio
            <input value={name} onChange={(e) => setName(e.target.value)} />
          </label>
        )}
        {error && <div className="error">{error}</div>}
        <footer>
          {info?.is_form && <span className="muted small">{picked.size} sheet · {total} dòng</span>}
          <button className="btn" onClick={onClose}>Hủy</button>
          <button className="btn primary" disabled={!canCreate} onClick={create}>
            {busy ? "Đang xử lý…" : "Tạo bộ audio"}
          </button>
        </footer>
      </div>
    </div>
  );
}
