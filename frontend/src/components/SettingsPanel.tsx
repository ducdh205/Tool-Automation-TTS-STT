import { useEffect, useState } from "react";
import { api, type Settings, type Voice } from "../api";

export function SettingsPanel({ onClose }: { onClose: () => void }) {
  const [s, setS] = useState<Settings | null>(null);
  const [voices, setVoices] = useState<Voice[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    api.settings().then(setS).catch((e) => setError(String(e.message)));
    api.voices().then(setVoices).catch(() => setVoices([]));
  }, []);

  const num = (k: keyof Settings) => (e: React.ChangeEvent<HTMLInputElement>) =>
    s && setS({ ...s, [k]: Number(e.target.value) });

  const save = async () => {
    if (!s) return;
    setSaving(true);
    try {
      await api.saveSettings(s);
      onClose();
    } catch (e) {
      setError(String((e as Error).message));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <header>
          <h2>Cài đặt</h2>
          <button className="icon-btn" onClick={onClose}>✕</button>
        </header>
        {!s ? <div className="muted">Đang tải…</div> : (
          <div className="form-grid">
            <label>Giọng VieNeu
              <select value={s.voice ?? ""} onChange={(e) => setS({ ...s, voice: e.target.value })}>
                {voices === null && <option>{s.voice} (đang tải danh sách…)</option>}
                {voices?.map((v) => <option key={v.id} value={v.id}>{v.label}</option>)}
              </select>
              <small className="muted">Áp dụng cho bộ audio tạo mới.</small>
            </label>
            <label>Ngưỡng WER để Đạt
              <input type="number" min={0} max={1} step={0.05} value={s.wer_threshold} onChange={num("wer_threshold")} />
              <small className="muted">0 = phải khớp hoàn toàn sau chuẩn hóa.</small>
            </label>
            <label>Cảnh báo khi tỉ lệ audio bị loại vượt
              <input type="number" min={0} max={1} step={0.01} value={s.reject_warn_ratio} onChange={num("reject_warn_ratio")} />
            </label>
            <label>Thời gian chờ STT (giây)
              <input type="number" min={5} max={300} value={s.stt_timeout_s} onChange={num("stt_timeout_s")} />
            </label>
          </div>
        )}
        {error && <div className="error">{error}</div>}
        <footer>
          <button className="btn" onClick={onClose}>Hủy</button>
          <button className="btn primary" disabled={!s || saving} onClick={save}>Lưu</button>
        </footer>
      </div>
    </div>
  );
}
