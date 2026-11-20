import { useEffect, useRef, useState } from "react";
import { api, type DeviceInfo, type DeviceInputBody, type DeviceKey, type DeviceStatus } from "../api";

const STATE_LABEL: Record<string, string> = {
  device: "Đã kết nối",
  unauthorized: "Chưa cho phép gỡ lỗi USB",
  offline: "Mất kết nối",
};

function useDeviceStatus(): DeviceStatus | null {
  const [status, setStatus] = useState<DeviceStatus | null>(null);
  useEffect(() => {
    let alive = true;
    let timer: number;
    const tick = async () => {
      try {
        const s = await api.device();
        if (alive) setStatus(s);
      } catch (e) {
        if (alive) setStatus({ adb: false, error: String(e), devices: [] });
      }
      if (alive) timer = window.setTimeout(tick, 2000);
    };
    tick();
    return () => { alive = false; window.clearTimeout(timer); };
  }, []);
  return status;
}

/** Live-ish screen: fetch the next screencap as soon as the previous one has loaded. */
/** Map a pointer position on an object-fit:contain <img> to device pixels (null = outside the picture). */
function toDevice(img: HTMLImageElement, clientX: number, clientY: number): { x: number; y: number } | null {
  const r = img.getBoundingClientRect();
  const nw = img.naturalWidth, nh = img.naturalHeight;
  if (!nw || !nh) return null;
  const scale = Math.min(r.width / nw, r.height / nh);
  const ox = r.left + (r.width - nw * scale) / 2, oy = r.top + (r.height - nh * scale) / 2;
  const x = (clientX - ox) / scale, y = (clientY - oy) / scale;
  if (x < 0 || y < 0 || x >= nw || y >= nh) return null;
  return { x: Math.round(x), y: Math.round(y) };
}

function PhoneScreen({ serial, onInput }: { serial: string; onInput: (b: DeviceInputBody) => void }) {
  const down = useRef<{ x: number; y: number; cx: number; cy: number; t: number } | null>(null);
  const [src, setSrc] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const urlRef = useRef<string | null>(null);

  useEffect(() => {
    let alive = true;
    let timer: number;
    const next = async () => {
      try {
        const r = await fetch(`/api/device/${encodeURIComponent(serial)}/screen`, { cache: "no-store" });
        if (!r.ok) throw new Error((await r.json().catch(() => null))?.detail ?? `${r.status}`);
        const url = URL.createObjectURL(await r.blob());
        if (!alive) { URL.revokeObjectURL(url); return; }
        if (urlRef.current) URL.revokeObjectURL(urlRef.current);
        urlRef.current = url;
        setSrc(url);
        setError(null);
        timer = window.setTimeout(next, 150);
      } catch (e) {
        if (!alive) return;
        setError(e instanceof Error ? e.message : String(e));
        timer = window.setTimeout(next, 1500);
      }
    };
    next();
    return () => {
      alive = false;
      window.clearTimeout(timer);
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
      urlRef.current = null;
    };
  }, [serial]);

  if (src)
    return (
      <img
        className="phone-img interactive"
        src={src}
        alt="Màn hình điện thoại"
        draggable={false}
        onPointerDown={(e) => {
          const p = toDevice(e.currentTarget, e.clientX, e.clientY);
          if (!p) return;
          e.currentTarget.setPointerCapture(e.pointerId);
          down.current = { ...p, cx: e.clientX, cy: e.clientY, t: performance.now() };
        }}
        onPointerUp={(e) => {
          const start = down.current;
          down.current = null;
          if (!start) return;
          const moved = Math.hypot(e.clientX - start.cx, e.clientY - start.cy);
          if (moved < 6) {
            onInput({ action: "tap", x: start.x, y: start.y });
            return;
          }
          const img = e.currentTarget;
          const r = img.getBoundingClientRect();
          // clamp the end point into the picture so swipes that leave it still count
          const end = toDevice(img, Math.min(Math.max(e.clientX, r.left), r.right - 1),
            Math.min(Math.max(e.clientY, r.top), r.bottom - 1)) ?? start;
          const ms = Math.round(Math.min(Math.max(performance.now() - start.t, 100), 2000));
          onInput({ action: "swipe", x: start.x, y: start.y, x2: end.x, y2: end.y, duration_ms: ms });
        }}
        onPointerCancel={() => { down.current = null; }}
      />
    );
  return (
    <div className="phone-empty">
      <div className="phone-icon">⏳</div>
      <b>{error ? "Không chụp được màn hình" : "Đang lấy màn hình…"}</b>
      {error && <span className="muted small">{error}</span>}
    </div>
  );
}

function Empty({ title, hint }: { title: string; hint: string }) {
  return (
    <div className="phone-empty">
      <div className="phone-icon">📱</div>
      <b>{title}</b>
      <span className="muted small">{hint}</span>
    </div>
  );
}

export function DevicePanel() {
  const status = useDeviceStatus();
  const [picked, setPicked] = useState<string | null>(null);
  const [log, setLog] = useState<string[]>([]);
  const [text, setText] = useState("");
  const devices = status?.devices ?? [];
  const current: DeviceInfo | undefined = devices.find((d) => d.serial === picked) ?? devices[0];

  const online = current?.state === "device";
  const send = async (b: DeviceInputBody) => {
    if (!current) return;
    const label =
      b.action === "tap" ? `Chạm (${b.x}, ${b.y})`
      : b.action === "swipe" ? `Vuốt (${b.x}, ${b.y}) → (${b.x2}, ${b.y2})`
      : b.action === "key" ? `Phím ${b.key}`
      : `Gõ “${b.text}”`;
    const time = new Date().toLocaleTimeString("vi-VN");
    try {
      await api.deviceInput(current.serial, b);
      setLog((l) => [`${time} ${label}`, ...l].slice(0, 50));
    } catch (e) {
      setLog((l) => [`${time} ✘ ${label}: ${e instanceof Error ? e.message : e}`, ...l].slice(0, 50));
    }
  };
  const key = (k: DeviceKey) => send({ action: "key", key: k });

  let screen;
  if (!status) screen = <Empty title="Đang kiểm tra thiết bị…" hint="" />;
  else if (!status.adb) screen = <Empty title="Không tìm thấy adb" hint="Đặt Android platform-tools vào vendor/platform-tools." />;
  else if (!current) screen = <Empty title="Chưa kết nối thiết bị" hint="Cắm cáp USB và bật Gỡ lỗi USB trong Tùy chọn nhà phát triển." />;
  else if (current.state === "unauthorized")
    screen = <Empty title="Chờ cho phép trên điện thoại" hint="Mở khóa điện thoại và bấm “Cho phép” gỡ lỗi USB." />;
  else if (current.state !== "device") screen = <Empty title={STATE_LABEL[current.state] ?? current.state} hint="Thử rút ra cắm lại cáp." />;
  else screen = <PhoneScreen serial={current.serial} onInput={send} />;

  return (
    <aside className="device">
      <div className="device-head">
        <span className="side-title">Thiết bị</span>
        {current && (
          <span className={`dot-label small ${current.state === "device" ? "ok" : "warn"}`}>
            ● {STATE_LABEL[current.state] ?? current.state}
          </span>
        )}
      </div>
      {devices.length > 1 ? (
        <select value={current?.serial} onChange={(e) => setPicked(e.target.value)}>
          {devices.map((d) => <option key={d.serial} value={d.serial}>{d.model ?? d.serial}</option>)}
        </select>
      ) : current ? (
        <div className="muted small">{current.model ?? "Android"} · {current.serial}</div>
      ) : null}
      <div className="phone">
        <div className="phone-screen">{screen}</div>
      </div>
      {online && (
        <div className="device-controls">
          <div className="device-keys">
            <button className="btn" title="Quay lại" onClick={() => key("back")}>◁</button>
            <button className="btn" title="Màn hình chính" onClick={() => key("home")}>○</button>
            <button className="btn" title="Đa nhiệm" onClick={() => key("recents")}>▢</button>
            <button className="btn" title="Giảm âm lượng" onClick={() => key("voldown")}>🔉</button>
            <button className="btn" title="Tăng âm lượng" onClick={() => key("volup")}>🔊</button>
            <button className="btn" title="Nút nguồn (tắt/bật màn hình)" onClick={() => key("power")}>⏻</button>
          </div>
          <form
            className="device-text"
            onSubmit={(e) => {
              e.preventDefault();
              if (text) send({ action: "text", text }).then(() => setText(""));
              else key("enter");
            }}
          >
            <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Gõ chữ không dấu, Enter để gửi" />
            <button className="btn" type="button" title="Xoá 1 ký tự" onClick={() => key("del")}>⌫</button>
          </form>
        </div>
      )}
      <div className="device-log">
        <div className="side-title">Nhật ký thao tác</div>
        {status?.error && <div className="muted small">{status.error}</div>}
        {log.length === 0 ? (
          <div className="muted small">{online ? "Bấm lên màn hình để chạm, kéo để vuốt." : "—"}</div>
        ) : (
          <div className="device-log-list small">
            {log.map((l, i) => <div key={i}>{l}</div>)}
          </div>
        )}
      </div>
    </aside>
  );
}
