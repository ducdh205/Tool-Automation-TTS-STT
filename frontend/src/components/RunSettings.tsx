import { useRef, useState, type FormEvent } from "react";
import type { Settings } from "../api";
import { Icon } from "./Icon";
import { Popover } from "./Popover";
import { ScoringGuide } from "./ScoringGuide";
import { VOICE_REGIONS, VoicePicker, type VoiceField } from "./VoicePicker";

type RunValues = Pick<Settings, VoiceField | "wer_threshold" | "stt_timeout_s" | "reject_warn_ratio">;
type Field = VoiceField | "wer" | "timeout" | "reject";

interface Props {
  settings: RunValues;
  busy: boolean;
  saving: boolean;
  /** Audio sets that already exist: saving then asks whether to delete them too. */
  setCount: number;
  /** `purgeSets`: the user chose to delete every existing audio set along with saving. */
  onSave: (values: RunValues, purgeSets: boolean) => Promise<void>;
}

/** Ratio → percent text without float noise (0.07 → "7", not "7.000000000000001"). */
const pct = (ratio: number) => String(Number((ratio * 100).toPrecision(15)));

/** Every run setting behind one summary button: the bar shows what is in effect, the panel edits it. */
export function RunSettings({ settings, busy, saving, setCount, onSave }: Props) {
  const [draft, setDraft] = useState<Partial<Record<Field, string>>>({});
  const [error, setError] = useState<string | null>(null);
  const [confirming, setConfirming] = useState(false);
  const closePanel = useRef<() => void>(() => {});

  const saved: Record<Field, string> = {
    voice: settings.voice ?? "",
    voice_trung: settings.voice_trung ?? "",
    voice_nam: settings.voice_nam ?? "",
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
    setError(null);
    // Old sets were generated with the old settings: let the user drop them in the same step.
    if (setCount > 0) setConfirming(true);
    else void save(false);
  };

  const save = async (purgeSets: boolean) => {
    setConfirming(false);
    try {
      await onSave({
        voice: value("voice") || null,
        voice_trung: value("voice_trung") || null,
        voice_nam: value("voice_nam") || null,
        wer_threshold: ratio("wer", settings.wer_threshold),
        stt_timeout_s: Number(value("timeout")),
        reject_warn_ratio: ratio("reject", settings.reject_warn_ratio),
      }, purgeSets);
      setDraft({});
      closePanel.current();
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const voiceSummary = VOICE_REGIONS.map(({ field }) => value(field) || "Mặc định").join(" / ");
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
              disabled={locked || !open} onChange={(f, v) => edit(f)(v)} />
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
            {confirming && open && (
              <div className="modal-backdrop" onClick={() => setConfirming(false)}>
                <div className="modal confirm-modal" role="alertdialog" aria-label="Xóa bộ audio cũ?"
                  onClick={(e) => e.stopPropagation()}>
                  <header><h2>Xóa bộ audio cũ?</h2></header>
                  <p>
                    Đang có {setCount} bộ audio sinh bằng cài đặt cũ. Lưu cài đặt và xóa luôn các bộ này
                    (gồm audio, kết quả chạy app và ảnh chụp)? Không thể hoàn tác.
                  </p>
                  <footer>
                    <button className="btn" type="button" onClick={() => setConfirming(false)}>Hủy</button>
                    <button className="btn" type="button" onClick={() => save(false)}>Chỉ lưu</button>
                    <button className="btn danger" type="button" onClick={() => save(true)}>Lưu &amp; xóa bộ cũ</button>
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
