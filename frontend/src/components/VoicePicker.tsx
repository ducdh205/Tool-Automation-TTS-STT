import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Voice } from "../api";

const REGIONAL_PRESETS = [
  { region: "Bắc", preferred: ["Ngọc Huyền", "Hải Đăng", "Mai Anh"] },
  { region: "Trung", preferred: ["Quang Sơn", "Ngọc Trân"] },
  { region: "Nam", preferred: ["Adam", "Thùy Dung", "Minh Triết"] },
];

interface Props {
  voice: string;
  savedVoice: string;
  disabled: boolean;
  onChange: (voice: string) => void;
}

export function VoicePicker({ voice, savedVoice, disabled, onChange }: Props) {
  const [voices, setVoices] = useState<Voice[]>([]);
  const [voiceStatus, setVoiceStatus] = useState<"idle" | "loading" | "ready" | "error">("idle");
  const [previewStatus, setPreviewStatus] = useState<"idle" | "loading" | "playing" | "error">("idle");
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

  const playPreview = async () => {
    if (preview.current) {
      stopPreview();
      return;
    }
    const audio = new Audio(api.voicePreviewUrl(voice));
    preview.current = audio;
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

  const groups = REGIONAL_PRESETS.map(({ region, preferred }) => {
    const available = voices.filter(({ label }) => label.split("·")[1]?.trim() === region);
    const byId = new Map(available.map((option) => [option.id, option]));
    const options = [...new Set([...preferred, ...byId.keys()])].flatMap((id) => byId.get(id) ?? []).slice(0, 3);
    return { region, options };
  });
  const showSaved = !groups.some(({ options }) => options.some(({ id }) => id === savedVoice));
  const savedLabel = voices.find(({ id }) => id === savedVoice)?.label ?? (savedVoice || "Mặc định");
  const previewActive = previewStatus === "loading" || previewStatus === "playing";

  return (
    <div className="field run-voice">
      <label htmlFor="run-voice">Giọng VieNeu</label>
      <div className="voice-picker">
        <select id="run-voice" value={voice} disabled={disabled}
          onFocus={loadVoices} onPointerDown={loadVoices}
          onChange={(event) => {
            stopPreview();
            onChange(event.target.value);
          }} aria-describedby="run-voice-note">
          {showSaved && <option value={savedVoice}>{savedLabel}</option>}
          {groups.map(({ region, options }) => options.length > 0 && (
            <optgroup key={region} label={`Miền ${region}`}>
              {options.map((option) => <option key={option.id} value={option.id}>{option.label}</option>)}
            </optgroup>
          ))}
        </select>
        <button className="btn" type="button" disabled={disabled || !voice} onClick={playPreview}>
          {previewActive ? "Dừng nghe" : "Nghe thử"}
        </button>
      </div>
      <small id="run-voice-note" className="muted" aria-live="polite">
        {voiceStatus === "loading" ? "Đang tải danh sách giọng…" :
          voiceStatus === "error" ? "Chưa tải được danh sách giọng. Bấm lại để thử." : "Áp dụng cho bộ audio tạo mới."}
      </small>
      {previewStatus === "loading" && <small role="status" className="muted">Đang tải audio nghe thử…</small>}
      {previewStatus === "error" && <small role="alert" className="warn">Chưa phát được mẫu giọng. Bấm Nghe thử để thử lại.</small>}
    </div>
  );
}
