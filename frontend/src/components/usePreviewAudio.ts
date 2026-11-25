import { useCallback, useEffect, useRef, useState } from "react";

export type PreviewStatus = "idle" | "loading" | "playing" | "error";

/** One preview clip at a time: play a URL, press again to stop; stops on unmount. */
export function usePreviewAudio() {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [status, setStatus] = useState<PreviewStatus>("idle");

  const stop = useCallback((next: "idle" | "error" = "idle") => {
    const audio = audioRef.current;
    audioRef.current = null;
    audio?.pause();
    setStatus(next);
  }, []);

  useEffect(() => () => {
    audioRef.current?.pause();
    audioRef.current = null;
  }, []);

  const toggle = useCallback(async (url: string) => {
    if (audioRef.current) {
      stop();
      return;
    }
    const audio = new Audio(url);
    audioRef.current = audio;
    setStatus("loading");
    const finish = (next: "idle" | "error") => {
      if (audioRef.current === audio) stop(next);
    };
    audio.onended = () => finish("idle");
    audio.onerror = () => finish("error");
    try {
      await audio.play();
      if (audioRef.current === audio) setStatus("playing");
    } catch {
      finish("error");
    }
  }, [stop]);

  return { status, active: status === "loading" || status === "playing", toggle, stop };
}
