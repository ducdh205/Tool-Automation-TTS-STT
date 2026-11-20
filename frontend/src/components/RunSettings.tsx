import { useRef, useState, type FormEvent } from "react";
import type { Settings } from "../api";
import { Icon } from "./Icon";
import { Popover } from "./Popover";
import { ScoringGuide } from "./ScoringGuide";
import { VoicePicker } from "./VoicePicker";

type RunValues = Pick<Settings, "voice" | "wer_threshold" | "stt_timeout_s" | "reject_warn_ratio">;
type Field = "voice" | "wer" | "timeout" | "reject";

interface Props {
  settings: RunValues;
  busy: boolean;
  saving: boolean;
  onSave: (values: RunValues) => Promise<void>;
}

/** Ratio → percent text without float noise (0.07 → "7", not "7.000000000000001"). */
const pct = (ratio: number) => String(Number((ratio * 100).toPrecision(15)));

/** Every run setting behind one summary button: the bar shows what is in effect, the panel edits it. */
export function RunSettings({ settings, busy, saving, onSave }: Props) {
  const [draft, setDraft] = useState<Partial<Record<Field, string>>>({});
  const [error, setError] = useState<string | null>(null);
  const closePanel = useRef<() => void>(() => {});

  const saved: Record<Field, string> = {
    voice: settings.voice ?? "",
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

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (locked || !changed) return;
    if (Number(value("timeout")) <= 0) {
      setError("Thời gian chờ STT phải lớn hơn 0 giây.");
      return;
    }
    setError(null);
    try {
      await onSave({
        voice: value("voice") || null,
        wer_threshold: ratio("wer", settings.wer_threshold),
        stt_timeout_s: Number(value("timeout")),
        reject_warn_ratio: ratio("reject", settings.reject_warn_ratio),
      });
      setDraft({});
      closePanel.current();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const summary = (
    <>
      <Icon name="settings" />
      <span className="ellipsis">{value("voice") || "Giọng mặc định"} · WER ≤ {value("wer")}% · {value("timeout")}s</span>
      {changed && <span className="unsaved">chưa lưu</span>}
      <Icon name="chevron" size={13} />
    </>
  );

  return (
    <form className="run-settings" onSubmit={save} aria-label="Cài đặt chạy">
      <Popover className="run-settings-anchor" buttonClassName="btn settings-trigger" panelLabel="Cài đặt chạy"
        disabled={busy} align="right" label={summary}>
        {(open, close) => {
          closePanel.current = close;
          return (
          <div className="settings-panel">
            <VoicePicker voice={value("voice")} savedVoice={saved.voice} disabled={locked || !open} onChange={edit("voice")} />
            <div className="settings-grid">
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
                  disabled={locked} onChange={(e) => edit("timeout")(e.target.value)} />
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
          </div>
          );
        }}
      </Popover>
    </form>
  );
}
