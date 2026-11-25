import { useEffect, useRef, useState, type FormEvent } from "react";
import { api, type Settings } from "../api";
import { usePreviewAudio } from "./usePreviewAudio";
import { Icon } from "./Icon";
import { Popover } from "./Popover";
import { ScoringGuide } from "./ScoringGuide";
import { VOICE_REGIONS, VoicePicker, type VoiceField } from "./VoicePicker";

type RunValues = Pick<Settings, VoiceField | "voice_speed" | "wer_threshold" | "stt_timeout_s" | "reject_warn_ratio">;
type Field = VoiceField | "speed" | "wer" | "timeout" | "reject";

/** Time-stretch range kept by the backend (tts/speed.py): beyond it the voice sounds smeared. */
const MIN_SPEED = 0.7;
const MAX_SPEED = 1.3;

interface Props {
  settings: RunValues;
  busy: boolean;
  saving: boolean;
  /** Audio sets that already exist: saving then asks whether to wipe their progress too. */
  setCount: number;
  /** `resetProgress`: the user chose to also wipe generated audio and results (rows are kept). */
  onSave: (values: RunValues, resetProgress: boolean) => Promise<void>;
}

/** Stops a playing clip when the settings panel closes (the panel's open state lives in Popover). */
function StopWhenClosed({ open, stop }: { open: boolean; stop: () => void }) {
  useEffect(() => { if (!open) stop(); }, [open, stop]);
  return null;
}

/** Ratio → percent text without float noise (0.07 → "7", not "7.000000000000001"). */
const pct = (ratio: number) => String(Number((ratio * 100).toPrecision(15)));

/** Every run setting behind one summary button: the bar shows what is in effect, the panel edits it. */
export function RunSettings({ settings, busy, saving, setCount, onSave }: Props) {
  const [draft, setDraft] = useState<Partial<Record<Field, string>>>({});
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const closePanel = useRef<() => void>(() => {});
  const speedPreview = usePreviewAudio();
  const stopSpeedPreview = speedPreview.stop;
  // Stop the clip when a job starts or the save begins (the button is locked then).
  useEffect(() => { if (busy || saving) stopSpeedPreview(); }, [busy, saving, stopSpeedPreview]);

  const saved: Record<Field, string> = {
    voice: settings.voice ?? "",
    voice_trung: settings.voice_trung ?? "",
    voice_nam: settings.voice_nam ?? "",
    speed: String(settings.voice_speed ?? 1),
    wer: pct(settings.wer_threshold),
    timeout: String(settings.stt_timeout_s),
    reject: pct(settings.reject_warn_ratio),
  };
  const value = (f: Field) => draft[f] ?? saved[f];
  const changed = (Object.keys(saved) as Field[]).some((f) => value(f) !== saved[f]);
  const locked = busy || saving;
  const edit = (f: Field) => (v: string) => setDraft((d) => ({ ...d, [f]: v }));
  // Keep the stored ratio when a percent field is untouched, so 0.07 does not round-trip through 7 / 100.
  const ratio = (f: "wer" | "reject", stored: number) => (value(f) === saved[f] ? stored : Number(value(f)) / 100);

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (locked || !changed) return;
    if (Number(value("timeout")) <= 0) {
      setError("Thời gian chờ STT phải lớn hơn 0 giây.");
      return;
    }
    const speed = Number(value("speed"));
    if (!(speed >= MIN_SPEED && speed <= MAX_SPEED)) {
      setError(`Tốc độ giọng phải trong khoảng ${MIN_SPEED}–${MAX_SPEED}.`);
      return;
    }
    setError(null);
    // Old sets were generated with the old settings: let the user drop them in the same step.
    if (setCount > 0) setConfirming(true);
    else void save(false);
  };

  const save = async (resetProgress: boolean) => {
    setConfirming(false);
    try {
      await onSave({
        voice: value("voice") || null,
        voice_trung: value("voice_trung") || null,
        voice_nam: value("voice_nam") || null,
        voice_speed: Number(value("speed")),
        wer_threshold: ratio("wer", settings.wer_threshold),
        stt_timeout_s: Number(value("timeout")),
        reject_warn_ratio: ratio("reject", settings.reject_warn_ratio),
      }, resetProgress);
      setDraft({});
      closePanel.current();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const speedSummary = Number(value("speed")) === 1 ? "" : ` · ${value("speed")}x`;
  const voiceSummary = VOICE_REGIONS.map(({ field }) => value(field) || "Mặc định").join(" / ") + speedSummary;
  // Preview at the draft speed so the user hears it before saving; an out-of-range draft plays normally.
  const draftSpeed = Number(value("speed"));
  const speedValid = value("speed").trim() !== "" && draftSpeed >= MIN_SPEED && draftSpeed <= MAX_SPEED;
  const previewSpeed = speedValid ? draftSpeed : 1;
  const speedLabel = `${draftSpeed.toFixed(2)}x`;
  const summary = (
    <>
      <Icon name="settings" />
      <span className="ellipsis" title={voiceSummary}>{voiceSummary} · WER ≤ {value("wer")}% · {value("timeout")}s</span>
      {changed && <span className="unsaved">chưa lưu</span>}
      <Icon name="chevron" size={13} />
    </>
  );

  return (
    <form className="run-settings" onSubmit={submit} aria-label="Cài đặt chạy">
      <Popover className="run-settings-anchor" buttonClassName="btn settings-trigger" panelLabel="Cài đặt chạy"
        disabled={busy} align="right" label={summary}>
        {(open, close) => {
          closePanel.current = close;
          return (
          <div className="settings-panel">
            <VoicePicker values={{ voice: value("voice"), voice_trung: value("voice_trung"), voice_nam: value("voice_nam") }}
              saved={{ voice: saved.voice, voice_trung: saved.voice_trung, voice_nam: saved.voice_nam }}
              disabled={locked || !open} speed={previewSpeed}
              onChange={(f, v) => { if (f === "voice") speedPreview.stop(); edit(f)(v); }} />
            <StopWhenClosed open={open} stop={stopSpeedPreview} />
            <div className="settings-grid">
              <div className="field speed-field">
                <div className="label-row">
                  <label htmlFor="run-speed">Tốc độ giọng (x)</label>
                  <output htmlFor="run-speed" className="speed-value">{speedLabel}</output>
                  {Number(value("speed")) !== 1 && (
                    <button className="link-btn" type="button" disabled={locked}
                      onClick={() => { speedPreview.stop(); edit("speed")("1"); }}>Về 1x</button>
                  )}
                </div>
                <div className="speed-row">
                  <span className="muted small" aria-hidden="true">{MIN_SPEED}x</span>
                  <input id="run-speed" type="range" min={MIN_SPEED} max={MAX_SPEED} step={0.05}
                    value={speedValid ? value("speed") : 1} disabled={locked} aria-describedby="run-speed-note"
                    aria-valuetext={speedLabel}
                    onChange={(e) => { speedPreview.stop(); edit("speed")(String(Number(e.target.value))); }} />
                  <span className="muted small" aria-hidden="true">{MAX_SPEED}x</span>
                  <button className="btn" type="button" disabled={locked || !open || !speedValid || !value("voice")}
                    aria-label={speedPreview.active ? "Dừng nghe tốc độ giọng" : "Nghe thử tốc độ giọng"}
                    title={`Nghe giọng miền Bắc (${value("voice") || "chưa chọn"}) ở tốc độ ${value("speed")}x`}
                    onClick={() => void speedPreview.toggle(api.voicePreviewUrl(value("voice"), draftSpeed))}>
                    {speedPreview.active ? "Dừng nghe" : "Nghe thử"}
                  </button>
                </div>
                <small id="run-speed-note" className="muted" aria-live="polite">
                  {speedPreview.status === "loading" ? "Đang tạo audio nghe thử…" :
                    speedPreview.status === "error" ? "Chưa phát được. Bấm Nghe thử để thử lại." :
                      !speedValid ? `Tốc độ đã lưu nằm ngoài ${MIN_SPEED}–${MAX_SPEED}: kéo để chọn lại` :
                        `1 là bình thường; ${MIN_SPEED}–${MAX_SPEED}, giữ nguyên cao độ. Nghe thử bằng giọng miền Bắc.`}
                </small>
              </div>
              <div className="field">
                <div className="label-row">
                  <label htmlFor="run-wer">Ngưỡng WER để đạt (%)</label>
                  <Popover iconOnly buttonClassName="info-btn" panelLabel="Cách chấm WER và CER" label={<Icon name="info" size={13} />}>
                    {() => <ScoringGuide />}
                  </Popover>
                </div>
                <input id="run-wer" type="number" min={0} max={100} step="any" required value={value("wer")} disabled={locked}
                  aria-describedby="run-wer-note" onChange={(e) => edit("wer")(e.target.value)} />
                <small id="run-wer-note" className="muted">0% là khớp hoàn toàn</small>
              </div>
              <div className="field">
                <label htmlFor="run-timeout">Thời gian chờ STT (giây)</label>
                <input id="run-timeout" type="number" min={0} max={600} step="any" required value={value("timeout")}
                  disabled={locked} aria-describedby="run-timeout-note" onChange={(e) => edit("timeout")(e.target.value)} />
                <small id="run-timeout-note" className="muted">Tối đa chờ STT tham chiếu nhận dạng 1 câu (Khối 1)</small>
              </div>
              <div className="field">
                <label htmlFor="run-reject">Cảnh báo khi tỉ lệ loại vượt (%)</label>
                <input id="run-reject" type="number" min={0} max={100} step="any" required value={value("reject")}
                  disabled={locked} onChange={(e) => edit("reject")(e.target.value)} />
              </div>
            </div>
            {error && <div className="error" role="alert">{error}</div>}
            <div className="settings-actions">
              <button className="btn ghost" type="button" disabled={locked || !changed}
                onClick={() => { setDraft({}); setError(null); }}>Hoàn tác</button>
              <button className="btn primary" type="submit" disabled={locked || !changed}>
                {saving ? "Đang lưu…" : "Lưu cài đặt"}
              </button>
            </div>
            {confirming && open && (
              <div className="modal-backdrop" onClick={() => setConfirming(false)}>
                <div className="modal confirm-modal" role="alertdialog" aria-label="Xóa tiến trình cũ?"
                  onClick={(e) => e.stopPropagation()}>
                  <header><h2>Xóa tiến trình cũ?</h2></header>
                  <p>
                    Audio đã sinh, kết quả STT/WER và các lần chạy app trong {setCount} bộ audio được tạo bằng
                    cài đặt cũ. Lưu cài đặt và xóa toàn bộ tiến trình này, đưa mọi câu về "Chờ"? Danh sách câu
                    đã nạp được giữ lại. Không thể hoàn tác.
                  </p>
                  <footer>
                    <button className="btn" type="button" onClick={() => setConfirming(false)}>Hủy</button>
                    <button className="btn danger" type="button" onClick={() => save(true)}>Lưu &amp; xóa tiến trình</button>
                  </footer>
                </div>
              </div>
            )}
          </div>
          );
        }}
      </Popover>
    </form>
  );
}
