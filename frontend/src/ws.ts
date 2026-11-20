import type { ProgressEvent } from "./api";

/** Subscribe to job events; reconnects automatically. Returns an unsubscribe function. */
export function connectEvents(onEvent: (e: ProgressEvent) => void, onStatus?: (up: boolean) => void): () => void {
  let ws: WebSocket | null = null;
  let closed = false;
  let timer: number | undefined;

  const open = () => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}/ws`);
    ws.onopen = () => onStatus?.(true);
    ws.onmessage = (m) => onEvent(JSON.parse(m.data) as ProgressEvent);
    ws.onclose = () => {
      onStatus?.(false);
      if (!closed) timer = window.setTimeout(open, 1500);
    };
  };
  open();
  return () => {
    closed = true;
    window.clearTimeout(timer);
    ws?.close();
  };
}
