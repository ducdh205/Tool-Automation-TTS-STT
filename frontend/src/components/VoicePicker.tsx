import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Voice } from "../api";

export type VoiceField = "voice" | "voice_trung" | "voice_nam";

/** One voice per region; rows whose region column is blank or unknown use the Bắc voice. */
export const VOICE_REGIONS: { field: VoiceField; region: string; preferred: string[] }[] = [
  { field: "voice", region: "Bắc", preferred: ["Ngọc Huyền", "Hải Đăng", "Mai Anh"] },
  { field: "voice_trung", region: "Trung", preferred: ["Quang Sơn", "Ngọc Trân"] },
  { field: "voice_nam", region: "Nam", preferred: ["Thùy Dung", "Adam", "Minh Triết"] },
];

interface Props {
  values: Record<VoiceField, string>;
  saved: Record<VoiceField, string>;
  disabled: boolean;
  onChange: (field: VoiceField, voice: string) => void;
}

const regionOf = (v: Voice) => v.label.split("·")[1]?.trim();

export function VoicePicker({ values, saved, disabled, onChange }: Props) {
  const [voices, setVoices] = useState<Voice[]>([]);
  const [voiceStatus, setVoiceStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [previewStatus, setPreviewStatus] = useState<"idle" | "loading" | "playing" | "error">("idle");
  const [previewField, setPreviewField] = useState<VoiceField | null>(null);
  const preview = useRef<HTMLAudioElement | null>(null);

  const stopAudio = useCallback(() => {
    const audio = preview.current;
    preview.current = null;
    audio?.pause();
  }, []);

  const stopPreview = useCallback((status: "idle" | "error" = "idle") => {
    stopAudio();
    setPreviewStatus(status);
  }, [stopAudio]);

  useEffect(() => stopAudio, [stopAudio]);
  useEffect(() => {
    if (disabled) stopPreview();
  }, [disabled, stopPreview]);

  const loadVoices = () => {
    if (voiceStatus === "ready" || voiceStatus === "loading") return;
    setVoiceStatus("loading");
    api.voices().then((list) => {
      setVoices(list);
      setVoiceStatus("ready");
    }).catch(() => setVoiceStatus("error"));
  };

  const playPreview = async (field: VoiceField) => {
    const wasPlaying = preview.current !== null && previewField === field;
    stopPreview();
    if (wasPlaying) return;
    const audio = new Audio(api.voicePreviewUrl(values[field]));
    preview.current = audio;
    setPreviewField(field);
    setPreviewStatus("loading");
    const finish = (status: "idle" | "error") => {
      if (preview.current === audio) stopPreview(status);
    };
    audio.onended = () => finish("idle");
    audio.onerror = () => finish("error");
    try {
      await audio.play();
      if (preview.current === audio) setPreviewStatus("playing");
    } catch {
      finish("error");
    }
  };

  const optionsFor = (region: string, preferred: string[]) => {
    const own = voices.filter((v) => regionOf(v) === region);
    const rank = (v: Voice) => (preferred.includes(v.id) ? preferred.indexOf(v.id) : preferred.length);
    return { own: [...own].sort((a, b) => rank(a) - rank(b)), other: voices.filter((v) => regionOf(v) !== region) };
  };

  return (
    <fieldset className="field run-voice">
      <legend>Giọng VieNeu theo vùng miền</legend>
      {VOICE_REGIONS.map(({ field, region, preferred }) => {
        const { own, other } = optionsFor(region, preferred);
        const savedVoice = saved[field];
        const listed = voices.some(({ id }) => id === savedVoice);
        const active = previewField === field && (previewStatus === "loading" || previewStatus === "playing");
        const id = `run-${field.replace("_", "-")}`;
        return (
          <div className="voice-row" key={field}>
            <label htmlFor={id}>Miền {region}</label>
            <div className="voice-picker">
              <select id={id} value={values[field]} disabled={disabled}
                onFocus={loadVoices} onPointerDown={loadVoices}
                onChange={(event) => {
                  stopPreview();
                  onChange(field, event.target.value);
                }} aria-describedby="run-voice-note">
                {!listed && <option value={savedVoice}>{savedVoice || "Mặc định"}</option>}
                {own.length > 0 && (
                  <optgroup label={`Miền ${region}`}>
                    {own.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
                  </optgroup>
                )}
                {other.length > 0 && (
                  <optgroup label="Vùng khác">
                    {other.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
                  </optgroup>
                )}
              </select>
              <button className="btn" type="button" disabled={disabled || !values[field]}
                aria-label={`${active ? "Dừng nghe" : "Nghe thử"} giọng miền ${region}`} onClick={() => playPreview(field)}>
                {active ? "Dừng nghe" : "Nghe thử"}
              </button>
            </div>
          </div>
        );
      })}
      <small id="run-voice-note" className="muted" aria-live="polite">
        {voiceStatus === "loading" ? "Đang tải danh sách giọng…" :
          voiceStatus === "error" ? "Chưa tải được danh sách giọng. Bấm lại để thử." :
            "Mỗi câu dùng giọng theo cột vùng miền; dòng trống/không rõ vùng dùng giọng Bắc. Áp dụng cho bộ audio tạo mới."}
      </small>
      {previewStatus === "loading" && <small role="status" className="muted">Đang tải audio nghe thử…</small>}
      {previewStatus === "error" && <small role="alert" className="warn">Chưa phát được mẫu giọng. Bấm Nghe thử để thử lại.</small>}
    </fieldset>
  );
}
