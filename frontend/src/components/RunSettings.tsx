import { useState, type FormEvent } from "react";
import type { Settings } from "../api";
import { VoicePicker } from "./VoicePicker";

type RunValues = Pick<Settings, "voice" | "wer_threshold" | "stt_timeout_s">;

interface Props {
  settings: RunValues;
  busy: boolean;
  saving: boolean;
  onSave: (values: RunValues) => Promise<void>;
}

export function RunSettings({ settings, busy, saving, onSave }: Props) {
  const [draft, setDraft] = useState<Partial<{ voice: string; wer: string; timeout: string }>>({});
  const [error, setError] = useState<string | null>(null);

  const savedVoice = settings.voice ?? "";
  const savedWer = String(Number((settings.wer_threshold * 100).toPrecision(15)));
  const savedTimeout = String(settings.stt_timeout_s);
  const voice = draft.voice ?? savedVoice;
  const wer = draft.wer ?? savedWer;
  const timeout = draft.timeout ?? savedTimeout;
  const changed = voice !== savedVoice || wer !== savedWer || timeout !== savedTimeout;
  const locked = busy || saving;
  const edit = (field: "voice" | "wer" | "timeout") => (value: string) => setDraft((d) => ({ ...d, [field]: value }));

  const save = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (locked || !changed) return;
    if (Number(timeout) <= 0) {
      setError("Thời gian chờ STT phải lớn hơn 0 giây.");
      return;
    }
    setError(null);
    try {
      await onSave({
        voice: voice || null,
        wer_threshold: wer === savedWer ? settings.wer_threshold : Number(wer) / 100,
        stt_timeout_s: Number(timeout),
      });
      setDraft({});
    } catch (e) {
      setError((e as Error).message);
    }
  };

  return (
    <form className="run-settings" onSubmit={save} aria-label="Cài đặt chạy">
      <VoicePicker voice={voice} savedVoice={savedVoice} disabled={locked} onChange={edit("voice")} />
      <div className="field run-number">
        <label htmlFor="run-wer">Ngưỡng WER để đạt (%)</label>
        <input id="run-wer" type="number" min={0} max={100} step="any" required value={wer} disabled={locked}
          aria-describedby="run-wer-note" onChange={(event) => edit("wer")(event.target.value)} />
        <small id="run-wer-note" className="muted">0% là khớp hoàn toàn</small>
      </div>
      <div className="field run-number">
        <label htmlFor="run-timeout">Thời gian chờ STT (giây)</label>
        <input id="run-timeout" type="number" min={0} max={600} step="any" required value={timeout} disabled={locked}
          onChange={(event) => edit("timeout")(event.target.value)} />
      </div>
      <button className="btn" type="submit" disabled={locked || !changed}>
        {saving ? "Đang lưu…" : "Lưu cài đặt"}
      </button>
      {error && <div className="error run-settings-error" role="alert">{error}</div>}
    </form>
  );
}
