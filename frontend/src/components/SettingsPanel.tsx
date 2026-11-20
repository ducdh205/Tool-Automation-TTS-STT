import { useState, type FormEvent } from "react";

interface Props {
  rejectWarn: number | undefined;
  loadFailed: boolean;
  saving: boolean;
  onRetry: () => void;
  onSave: (value: number) => Promise<void>;
  onClose: () => void;
}

export function SettingsPanel({ rejectWarn, loadFailed, saving, onRetry, onSave, onClose }: Props) {
  const [draft, setDraft] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const value = draft ?? String(rejectWarn ?? "");

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (rejectWarn === undefined || saving) return;
    setError(null);
    try {
      await onSave(Number(value));
      onClose();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <form className="modal" onClick={(e) => e.stopPropagation()} onSubmit={save}>
        <header>
          <h2>Cài đặt</h2>
          <button className="icon-btn" type="button" onClick={onClose}>✕</button>
        </header>
        {rejectWarn === undefined ? (
          loadFailed ? (
            <div>Chưa tải được cài đặt. <button className="link-btn" type="button" onClick={onRetry}>Thử lại</button></div>
          ) : <div className="muted">Đang tải…</div>
        ) : (
          <div className="form-grid">
            <label>Cảnh báo khi tỉ lệ audio bị loại vượt
              <input type="number" min={0} max={1} step="any" required value={value} disabled={saving}
                onChange={(e) => setDraft(e.target.value)} />
            </label>
          </div>
        )}
        {error && <div className="error" role="alert">{error}</div>}
        <footer>
          <button className="btn" type="button" onClick={onClose}>Hủy</button>
          <button className="btn primary" type="submit" disabled={rejectWarn === undefined || saving}>Lưu</button>
        </footer>
      </form>
    </div>
  );
}
