import { useEffect, useState } from "react";
import { api, type IosConnect } from "../api";

/** Polls the "Kết nối iPhone" state (fast while connecting). */
export function useIosConnect(enabled: boolean): [IosConnect | null, (s: IosConnect) => void] {
  const [s, setS] = useState<IosConnect | null>(null);
  useEffect(() => {
    if (!enabled) return;
    let alive = true;
    let timer: number;
    const tick = async () => {
      let next: IosConnect | null = null;
      try {
        next = await api.iosConnectStatus();
        if (alive) setS(next);
      } catch { /* no go-ios: the panel shows that already */ }
      if (alive) timer = window.setTimeout(tick, next?.state === "starting" ? 800 : 2000);
    };
    tick();
    return () => { alive = false; window.clearTimeout(timer); };
  }, [enabled]);
  return [s, setS];
}

/** Shown in the phone frame when an iPhone has no WebDriverAgent yet (or none is seen). */
export function IosConnectBox({ title, hint }: { title: string; hint: string }) {
  const [s, setS] = useIosConnect(true);
  const [err, setErr] = useState<string | null>(null);
  const starting = s?.state === "starting";
  const connect = async () => {
    setErr(null);
    try {
      setS(await api.iosConnect());
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  };
  return (
    <div className="phone-empty ios-connect">
      <div className="phone-icon">📱</div>
      <b>{title}</b>
      {!starting && s?.state !== "error" && <span className="muted small">{hint}</span>}
      <button className="btn primary" disabled={starting} onClick={connect}>
        {starting ? "Đang kết nối…" : s?.state === "error" ? "Kết nối lại" : "Kết nối iPhone"}
      </button>
      {starting && s?.step && <span className="small muted">{s.step}</span>}
      {s?.state === "error" && s.error && <span className="small error">{s.error}</span>}
      {s?.state === "error" && s.detail && (
        <details className="small muted">
          <summary>Chi tiết kỹ thuật</summary>
          <pre className="ios-connect-detail">{s.detail}</pre>
        </details>
      )}
      {err && <span className="small error">{err}</span>}
    </div>
  );
}
