import { useCallback, useEffect, useRef, useState } from "react";

export const TOAST_MS = 6000;

export type Toast = { text: string; kind: "info" | "error" };

/** One toast at a time; each new one restarts the timer, so it always stays its full time. */
export function useToast() {
  const [toast, setToast] = useState<Toast | null>(null);
  const timer = useRef<number | undefined>(undefined);

  const notify = useCallback((text: string, kind: Toast["kind"] = "info") => {
    window.clearTimeout(timer.current);
    setToast({ text, kind });
    timer.current = window.setTimeout(() => setToast(null), TOAST_MS);
  }, []);

  useEffect(() => () => window.clearTimeout(timer.current), []);

  return { toast, notify };
}
