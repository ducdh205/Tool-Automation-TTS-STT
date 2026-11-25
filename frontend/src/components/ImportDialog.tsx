import { useEffect, useRef, useState } from "react";
import { api, type InspectResult, type MappingField, type SheetPreview } from "../api";

interface Props {
  onClose: () => void;
  onCreated: (setId: number) => void | Promise<void>;
}

const FIXED = "__fixed__";

interface FieldDef { key: MappingField; label: string; hint: string; level: "required" | "recommended" | "optional" }
const FIELDS: FieldDef[] = [
  { key: "id_col", label: "Mã câu (Case ID)", hint: "Tự sinh theo số dòng nếu để trống.", level: "recommended" },
  { key: "text_col", label: "Câu lệnh *", hint: "Cột dùng để đọc thành audio.", level: "required" },
  { key: "turn_col", label: "Kịch bản hội thoại", hint: "Bước / lượt — gom các câu cùng hội thoại.", level: "optional" },
  { key: "expected_col", label: "Kết quả mong đợi", hint: "Dùng để AI đối chiếu chấm điểm.", level: "recommended" },
  { key: "region_col", label: "Vùng miền", hint: "Giọng vùng miền của câu (vd BAC-HN).", level: "recommended" },
];

type Mapping = Record<MappingField, string>;
const EMPTY: Mapping = { text_col: "", id_col: "", region_col: "", expected_col: "", turn_col: "" };

export function ImportDialog({ onClose, onCreated }: Props) {
  const [info, setInfo] = useState<InspectResult | null>(null);
  const [fileName, setFileName] = useState("");
  const [sheet, setSheet] = useState<string | null>(null);
  const [picked, setPicked] = useState<Set<string>>(new Set());
  const [headerRow, setHeaderRow] = useState("1");
  const [preview, setPreview] = useState<SheetPreview | null>(null);
  const [previewFor, setPreviewFor] = useState("");
  const [mapping, setMapping] = useState<Mapping>(EMPTY);
  const [regionValue, setRegionValue] = useState("");
  const [name, setName] = useState("");
  const [keepOpen, setKeepOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const touched = useRef(new Set<MappingField>());
  const seq = useRef(0);
  const headerTouched = useRef(false);

  const headerNum = Number.parseInt(headerRow, 10);
  const headerOk = Number.isInteger(headerNum) && headerNum >= 1;

  useEffect(() => {
    if (!info || !headerOk) return;
    const mine = ++seq.current;
    const t = setTimeout(async () => {
      try {
        const pv = await api.preview({ file_id: info.file_id, sheet, header_row: headerNum });
        if (mine !== seq.current) return;
        setPreview(pv);
        setPreviewFor(`${sheet}|${headerNum}`);
        setError(null);
        setMapping((cur) => {
          const next = { ...cur };
          for (const f of FIELDS) {
            const keep = touched.current.has(f.key) && (cur[f.key] === FIXED || pv.columns.includes(cur[f.key]));
            next[f.key] = keep ? cur[f.key] : touched.current.has(f.key) ? "" : (pv.suggestions[f.key] ?? "");
          }
          return next;
        });
      } catch (e) {
        if (mine !== seq.current) return;
        setPreview(null);
        setPreviewFor("");
        setError(String((e as Error).message));
      }
    }, headerTouched.current ? 300 : 0);
    return () => clearTimeout(t);
  }, [info, sheet, headerNum, headerOk]);

  const onFile = async (f: File | undefined) => {
    if (!f) return;
    setBusy(true);
    setError(null);
    try {
      const r = await api.inspect(f);
      touched.current = new Set();
      headerTouched.current = false;
      setMapping(EMPTY);
      setRegionValue("");
      setPreview(null);
      setHeaderRow("1");
      setFileName(f.name);
      setName(f.name.replace(/\.(xlsx|csv|xlsm)$/i, ""));
      setSheet(r.sheets[0] ?? null);
      setPicked(new Set(r.sheets[0] ? [r.sheets[0]] : []));
      setInfo(r);
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  };

  const setField = (key: MappingField, value: string) => {
    touched.current.add(key);
    setMapping((m) => ({ ...m, [key]: value }));
  };

  const toggle = (n: string) => {
    const next = new Set(picked);
    if (next.has(n)) next.delete(n); else next.add(n);
    setPicked(next);
  };

  const regionFixed = mapping.region_col === FIXED;
  const isCsv = !!info && info.sheets.length === 0;

  const create = async () => {
    if (!info) return;
    setBusy(true);
    setError(null);
    const sheets = isCsv ? [] : [...picked];
    try {
      const r = await api.createSet({
        file_id: info.file_id,
        sheets,
        name,
        mapping: {
          header_row: headerNum,
          text_col: mapping.text_col,
          id_col: mapping.id_col || null,
          region_col: mapping.region_col && !regionFixed ? mapping.region_col : null,
          region_value: regionFixed ? regionValue.trim() : null,
          expected_col: mapping.expected_col || null,
          turn_col: mapping.turn_col || null,
        },
      });
      await onCreated(r.id);
      if (keepOpen) {
        setPicked(new Set());
      } else {
        onClose();
      }
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setBusy(false);
    }
  };

  const canCreate =
    !!info && !busy && !!name.trim() && headerOk && !!mapping.text_col && previewFor === `${sheet}|${headerNum}` &&
    (isCsv || picked.size > 0) && (!regionFixed || !!regionValue.trim());

  const mappedLabel = (col: string) => FIELDS.filter((f) => mapping[f.key] === col).map((f) => f.label.replace(" *", ""));

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal import-modal" onClick={(e) => e.stopPropagation()}>
        <header>
          <div>
            <div className="import-eyebrow">NHẬP DỮ LIỆU TESTCASE</div>
            <h2>{fileName || "Chọn file"}</h2>
          </div>
          <button className="icon-btn" aria-label="Đóng" onClick={onClose}>✕</button>
        </header>

        {!info && (
          <label className="file-drop">
            <input type="file" accept=".xlsx,.xlsm,.csv" onChange={(e) => onFile(e.target.files?.[0])} />
            <span>Chọn file .xlsx hoặc .csv</span>
          </label>
        )}
        {info && (
          <label className="import-change muted small">
            <input type="file" accept=".xlsx,.xlsm,.csv" hidden onChange={(e) => onFile(e.target.files?.[0])} />
            <span className="link-btn">Đổi file khác</span>
          </label>
        )}

        {info && (
          <div className="import-body">
            <div className="import-top">
              {!isCsv && (
                <div className="import-cell">
                  <label htmlFor="imp-sheet"><b>Sheet</b></label>
                  <select id="imp-sheet" value={sheet ?? ""} onChange={(e) => setSheet(e.target.value)}>
                    {info.sheets.map((s) => <option key={s} value={s}>{s}</option>)}
                  </select>
                </div>
              )}
              <div className="import-cell">
                <label htmlFor="imp-header"><b>Dòng tiêu đề</b></label>
                <input
                  id="imp-header" type="number" min={1} value={headerRow}
                  onChange={(e) => { headerTouched.current = true; setHeaderRow(e.target.value); }}
                />
              </div>
              <div className="import-cell">
                <b>Tổng số dòng</b>
                <span className="import-total">{preview ? preview.row_count : "—"}</span>
              </div>
            </div>

            {!isCsv && (
              <div className="import-sheets">
                <div className="row-between">
                  <span className="muted small">Nạp các sheet (dùng chung mapping, gộp thành một bộ audio)</span>
                  <button
                    className="link-btn"
                    onClick={() => setPicked(picked.size === info.sheets.length ? new Set() : new Set(info.sheets))}
                  >
                    {picked.size === info.sheets.length ? "Bỏ chọn" : "Chọn tất cả"}
                  </button>
                </div>
                <div className="sheet-list">
                  {info.sheets.map((s) => (
                    <label key={s} className="sheet-item">
                      <input type="checkbox" checked={picked.has(s)} onChange={() => toggle(s)} aria-label={s} />
                      <span className="ellipsis">{s}</span>
                      <small />
                    </label>
                  ))}
                </div>
                <label className="import-keep">
                  <input type="checkbox" checked={keepOpen} onChange={(e) => setKeepOpen(e.target.checked)} />
                  Giữ cửa sổ này để nạp tiếp sheet khác
                </label>
              </div>
            )}

            <div className="import-grid">
              {FIELDS.map((f) => {
                const missing = f.level === "recommended" && !mapping[f.key];
                const cols = preview?.columns ?? [];
                return (
                  <div key={f.key} className={`import-field ${f.level}`}>
                    <label htmlFor={`imp-${f.key}`} className={f.level === "required" ? "req" : undefined}>{f.label}</label>
                    <select id={`imp-${f.key}`} value={mapping[f.key]} onChange={(e) => setField(f.key, e.target.value)}>
                      <option value="">— Không map —</option>
                      {f.key === "region_col" && <option value={FIXED}>Giá trị cố định…</option>}
                      {cols.map((c) => <option key={c} value={c}>{c}</option>)}
                    </select>
                    {f.key === "region_col" && regionFixed && (
                      <input
                        aria-label="Giá trị vùng miền cố định" placeholder="vd BAC-HN"
                        value={regionValue} onChange={(e) => setRegionValue(e.target.value)}
                      />
                    )}
                    <small className={missing ? "warn" : "muted"}>{f.hint}</small>
                  </div>
                );
              })}
            </div>

            <div className="import-preview">
              <div className="row-between">
                <b>Xem trước dữ liệu</b>
                {preview && (
                  <span className="muted small">{preview.row_count} dòng dữ liệu · hiển thị tối đa 20 dòng</span>
                )}
              </div>
              <div className="import-table-wrap">
                {preview && (
                  <table className="import-table">
                    <thead>
                      <tr>
                        {preview.columns.map((c) => (
                          <th key={c} className={mappedLabel(c).length ? "mapped" : undefined}>
                            {c}
                            {mappedLabel(c).map((l) => <small key={l} className="tag">{l}</small>)}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {preview.rows.map((r, i) => (
                        <tr key={i}>
                          {r.map((v, j) => (
                            <td key={j} className={mappedLabel(preview.columns[j]).length ? "mapped" : undefined}>{v}</td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </div>

            <label className="field">Tên bộ audio
              <input value={name} onChange={(e) => setName(e.target.value)} />
            </label>
          </div>
        )}

        {error && <div className="error">{error}</div>}
        <footer>
          <button className="btn" onClick={onClose}>Huỷ</button>
          <button className="btn primary" disabled={!canCreate} onClick={create}>
            {busy ? "Đang xử lý…" : "Tạo bộ audio"}
          </button>
        </footer>
      </div>
    </div>
  );
}
