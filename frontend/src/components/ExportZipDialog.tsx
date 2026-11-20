import { useState } from "react";
import { formatSize } from "../format";

export type ZipAudio = "failed" | "all" | "selected";
/** ~3 s of 48 kHz 16-bit mono WAV: only for the size hint. */
export const AVG_WAV_BYTES = 300_000;

interface Props {
  totalCount: number;
  failedCount: number;
  selectedCount: number;
  onClose: () => void;
  onExport: (audio: ZipAudio) => Promise<void> | void;
}

export function ExportZipDialog({ totalCount, failedCount, selectedCount, onClose, onExport }: Props) {
  const [audio, setAudio] = useState<ZipAudio>("failed");
  const [busy, setBusy] = useState(false);

  const option = (value: ZipAudio, label: string, disabled = false) => (
    <label className="radio-line">
      <input type="radio" name="zip-audio" value={value} checked={audio === value} disabled={disabled || busy}
        onChange={() => setAudio(value)} />
      {label}
    </label>
  );

  const run = async () => {
    setBusy(true);
    try {
      await onExport(audio);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={busy ? undefined : onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <header>
          <h2>Xuất zip phiên</h2>
          <button className="icon-btn" title="Đóng" onClick={onClose} disabled={busy}>✕</button>
        </header>
        <div className="form-grid">
          <div className="field">Audio kèm theo</div>
          {option("failed", `Chỉ case Sai / Lỗi thao tác (${failedCount})`)}
          {option("all", `Tất cả (${totalCount}) — ~${formatSize(totalCount * AVG_WAV_BYTES)}`)}
          {option("selected", `Các case đang chọn (${selectedCount})`, selectedCount === 0)}
          <small className="muted">Ảnh chụp, kết quả và log luôn có cho mọi case.</small>
        </div>
        <footer>
          <button className="btn" onClick={onClose} disabled={busy}>Hủy</button>
          <button className="btn primary" onClick={run} disabled={busy}>{busy ? "Đang tạo zip…" : "Xuất zip"}</button>
        </footer>
      </div>
    </div>
  );
}
