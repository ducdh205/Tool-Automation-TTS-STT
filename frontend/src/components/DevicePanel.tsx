import { useEffect, useRef, useState } from "react";
import { startMirror, streamSupported, type StreamSession } from "../scrcpy";
import { Icon } from "./Icon";
import { IosConnectBox } from "./IosConnect";
import { api, type AppProfile, type DeviceInfo, type DeviceInputBody, type DeviceKey, type DeviceStatus, type UiNodeInfo } from "../api";

const STATE_LABEL: Record<string, string> = {
  device: "Đã kết nối",
  unauthorized: "Chưa cho phép gỡ lỗi USB",
  offline: "Mất kết nối",
  no_wda: "Chưa kết nối iPhone",
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

/** Pointer position on an object-fit:contain picture of nw x nh -> picture pixels (null = outside it). */
function toPicture(el: HTMLElement, nw: number, nh: number, clientX: number, clientY: number): { x: number; y: number } | null {
  const r = el.getBoundingClientRect();
  if (!nw || !nh) return null;
  const scale = Math.min(r.width / nw, r.height / nh);
  const ox = r.left + (r.width - nw * scale) / 2, oy = r.top + (r.height - nh * scale) / 2;
  const x = (clientX - ox) / scale, y = (clientY - oy) / scale;
  if (x < 0 || y < 0 || x >= nw || y >= nh) return null;
  return { x, y };
}

type ToDevice = (el: HTMLElement, clientX: number, clientY: number) => { x: number; y: number } | null;

/** Tap (moved < 6 px) or swipe on the picture, sent in phone pixels. */
function usePointerInput(toDevice: ToDevice, onInput: (b: DeviceInputBody) => void) {
  const down = useRef<{ x: number; y: number; cx: number; cy: number; t: number } | null>(null);
  return {
    onPointerDown: (e: React.PointerEvent<HTMLElement>) => {
      const p = toDevice(e.currentTarget, e.clientX, e.clientY);
      if (!p) return;
      e.currentTarget.setPointerCapture(e.pointerId);
      down.current = { ...p, cx: e.clientX, cy: e.clientY, t: performance.now() };
    },
    onPointerUp: (e: React.PointerEvent<HTMLElement>) => {
      const start = down.current;
      down.current = null;
      if (!start) return;
      const moved = Math.hypot(e.clientX - start.cx, e.clientY - start.cy);
      if (moved < 6) {
        onInput({ action: "tap", x: start.x, y: start.y });
        return;
      }
      const el = e.currentTarget;
      const r = el.getBoundingClientRect();
      // clamp the end point into the picture so swipes that leave it still count
      const end = toDevice(el, Math.min(Math.max(e.clientX, r.left), r.right - 1),
        Math.min(Math.max(e.clientY, r.top), r.bottom - 1)) ?? start;
      const ms = Math.round(Math.min(Math.max(performance.now() - start.t, 100), 2000));
      onInput({ action: "swipe", x: start.x, y: start.y, x2: end.x, y2: end.y, duration_ms: ms });
    },
    onPointerCancel: () => { down.current = null; },
  };
}

function Waiting({ error }: { error?: string | null }) {
  return (
    <div className="phone-empty">
      <div className="phone-icon">⏳</div>
      <b>{error ? "Không chụp được màn hình" : "Đang lấy màn hình…"}</b>
      {error && <span className="muted small">{error}</span>}
    </div>
  );
}

/** Android: live scrcpy mirror; iPhone, no WebCodecs, or a failed stream: screenshots. */
function PhoneScreen({ serial, ios, onInput }: { serial: string; ios: boolean; onInput: (b: DeviceInputBody) => void }) {
  const [fallback, setFallback] = useState<string | null>(null);
  useEffect(() => setFallback(null), [serial]);
  if (!ios && streamSupported() && fallback === null)
    return <MirrorScreen key={serial} serial={serial} onInput={onInput} onFail={setFallback} />;
  return <PollScreen serial={serial} onInput={onInput} />;
}

function MirrorScreen({ serial, onInput, onFail }: {
  serial: string; onInput: (b: DeviceInputBody) => void; onFail: (reason: string) => void;
}) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const session = useRef<StreamSession | null>(null);
  const [live, setLive] = useState(false);
  useEffect(() => {
    if (!canvas.current) return;
    return startMirror(serial, canvas.current, {
      onSession: (s) => { session.current = s; },
      onLive: () => setLive(true),
      onFail,
    });
  }, [serial, onFail]);
  const pointer = usePointerInput((el, cx, cy) => {
    const c = el as HTMLCanvasElement, s = session.current;
    const p = toPicture(c, c.width, c.height, cx, cy);
    if (!p || !s) return null;
    // stream pixels -> phone pixels (the server scales the stream down)
    const x = Math.min(Math.round(p.x * s.device_width / c.width), s.device_width - 1);
    const y = Math.min(Math.round(p.y * s.device_height / c.height), s.device_height - 1);
    return { x, y };
  }, onInput);
  return (
    <>
      <canvas ref={canvas} className="phone-img interactive" style={live ? undefined : { display: "none" }}
        aria-label="Màn hình điện thoại" {...pointer} />
      {!live && <Waiting />}
    </>
  );
}

/** Live-ish screen: fetch the next screencap as soon as the previous one has loaded. */
function PollScreen({ serial, onInput }: { serial: string; onInput: (b: DeviceInputBody) => void }) {
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

  const pointer = usePointerInput((el, cx, cy) => {
    const img = el as HTMLImageElement;
    const p = toPicture(img, img.naturalWidth, img.naturalHeight, cx, cy);
    return p && { x: Math.round(p.x), y: Math.round(p.y) };
  }, onInput);
  if (src)
    return <img className="phone-img interactive" src={src} alt="Màn hình điện thoại" draggable={false} {...pointer} />;
  return <Waiting error={error} />;
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

const ROLES: { key: keyof AppProfile; label: string }[] = [
  { key: "open_label", label: "Mở mic" },
  { key: "stop_label", label: "Dừng nghe" },
  { key: "idle_label", label: "Mic chờ" },
  { key: "close_label", label: "Đóng" },
];

interface Props {
  /** Lines from the running Block 2 job (newest last). */
  jobLogs?: string[];
  /** Profile that pin mode assigns labels to. */
  profile?: AppProfile | null;
  onProfileSaved?: (p: AppProfile) => void;
  /** Phone of the run on screen: the panel switches to it (two phones in one job). */
  serial?: string | null;
}

export function DevicePanel({ jobLogs = [], profile = null, onProfileSaved, serial = null }: Props) {
  const status = useDeviceStatus();
  const [pinning, setPinning] = useState(false);
  const [pinned, setPinned] = useState<UiNodeInfo | null>(null);
  const [pinError, setPinError] = useState<string | null>(null);
  const [picked, setPicked] = useState<string | null>(serial);
  useEffect(() => { if (serial) setPicked(serial); }, [serial]);
  const [log, setLog] = useState<string[]>([]);
  const [text, setText] = useState("");
  const devices = status?.devices ?? [];
  const current: DeviceInfo | undefined = devices.find((d) => d.serial === picked) ?? devices[0];

  const online = current?.state === "device";
  const ios = current?.platform === "ios";
  const locked = !!current && !!status?.busy?.includes(current.serial); // a block 2 job drives this phone
  const send = async (b: DeviceInputBody) => {
    if (!current || locked) return;
    if (pinning && b.action === "tap") {
      // Pin mode: look up the control under the finger instead of tapping the phone.
      setPinError(null);
      try {
        setPinned(await api.nodeAt(current.serial, b.x, b.y));
      } catch (e) {
        setPinned(null);
        setPinError(e instanceof Error ? e.message : String(e));
      }
      return;
    }
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

  const firstLine = (l: string) => l.split(/\r?\n/)[0];
  const assign = async (k: keyof AppProfile) => {
    if (!profile || !pinned?.label) return;
    try {
      const saved = await api.saveProfile({ ...profile, [k]: firstLine(pinned.label) });
      onProfileSaved?.(saved);
      setPinned(null);
    } catch (e) {
      setPinError(e instanceof Error ? e.message : String(e));
    }
  };

  let screen;
  if (!status) screen = <Empty title="Đang kiểm tra thiết bị…" hint="" />;
  else if (!status.adb && !status.ios) screen = <Empty title="Không tìm thấy adb" hint="Đặt Android platform-tools vào vendor/platform-tools." />;
  else if (!current && status.ios)
    screen = <IosConnectBox title="Chưa kết nối thiết bị"
      hint="Android: cắm cáp và bật Gỡ lỗi USB. iPhone: cắm cáp, mở khóa, bấm “Tin cậy” rồi bấm Kết nối iPhone." />;
  else if (!current) screen = <Empty title="Chưa kết nối thiết bị" hint="Cắm cáp USB và bật Gỡ lỗi USB trong Tùy chọn nhà phát triển." />;
  else if (current.state === "no_wda")
    screen = <IosConnectBox title="iPhone chưa sẵn sàng" hint="Mở khóa iPhone rồi bấm Kết nối iPhone." />;
  else if (current.state === "unauthorized")
    screen = <Empty title="Chờ cho phép trên điện thoại" hint="Mở khóa điện thoại và bấm “Cho phép” gỡ lỗi USB." />;
  else if (current.state !== "device") screen = <Empty title={STATE_LABEL[current.state] ?? current.state} hint="Thử rút ra cắm lại cáp." />;
  else screen = <PhoneScreen serial={current.serial} ios={ios} onInput={send} />;

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
        <div className="muted small">{current.model ?? (ios ? "iPhone" : "Android")} · {current.serial}</div>
      ) : null}
      <div className="phone">
        <div className="phone-screen">{screen}</div>
      </div>
      {online && locked && (
        <div className="small warn-box">Đang chạy test app — tạm khóa chạm, phím và ghim nút.</div>
      )}
      {online && (
        <div className="pin-bar">
          <button className={`btn small-btn ${pinning ? "primary" : ""}`} disabled={!profile || locked}
            onClick={() => { setPinning(!pinning); setPinned(null); setPinError(null); }}
            title="Bật rồi chạm lên màn hình để xem nhãn nút và gán cho hồ sơ app">
            <Icon name="pin" size={13} />{pinning ? "Đang ghim — chạm lên nút trên màn hình" : "Ghim nút cho hồ sơ app"}
          </button>
          {pinning && pinned && (
            <div className="pin-result">
              <div className="small"><b>{firstLine(pinned.label) || "(không có nhãn)"}</b> <span className="muted">{pinned.cls.split(".").pop()}</span></div>
              <div className="chips">
                {ROLES.map((r) => (
                  <button key={r.key} className="chip" disabled={!pinned.label} onClick={() => assign(r.key)}
                    title={`Hiện tại: ${String(profile?.[r.key] ?? "")}`}>{r.label}</button>
                ))}
              </div>
            </div>
          )}
          {pinning && pinError && <div className="small error">{pinError}</div>}
        </div>
      )}
      {online && (
        <div className="device-controls">
          <div className="device-keys">
            <button className="btn" title="Quay lại" aria-label="Quay lại" onClick={() => key("back")}><Icon name="back" /></button>
            <button className="btn" title="Màn hình chính" aria-label="Màn hình chính" onClick={() => key("home")}><Icon name="home" /></button>
            {!ios && <button className="btn" title="Đa nhiệm" aria-label="Đa nhiệm" onClick={() => key("recents")}><Icon name="recents" /></button>}
            <span className="divider" />
            <button className="btn" title="Giảm âm lượng" aria-label="Giảm âm lượng" onClick={() => key("voldown")}><Icon name="volDown" /></button>
            <button className="btn" title="Tăng âm lượng" aria-label="Tăng âm lượng" onClick={() => key("volup")}><Icon name="volUp" /></button>
            {!ios && <button className="btn" title="Nút nguồn (tắt/bật màn hình)" aria-label="Nút nguồn" onClick={() => key("power")}><Icon name="power" /></button>}
          </div>
          <form
            className="device-text"
            onSubmit={(e) => {
              e.preventDefault();
              if (text) send({ action: "text", text }).then(() => setText(""));
              else key("enter");
            }}
          >
            <input value={text} onChange={(e) => setText(e.target.value)} placeholder={ios ? "Gõ chữ (có dấu), Enter để gửi" : "Gõ chữ không dấu, Enter để gửi"} />
            <button className="btn" type="button" title="Xoá 1 ký tự" aria-label="Xoá 1 ký tự" onClick={() => key("del")}><Icon name="backspace" /></button>
          </form>
        </div>
      )}
      <div className="device-log">
        <div className="side-title">Nhật ký thao tác</div>
        {status?.error && <div className="muted small">{status.error}</div>}
        {jobLogs.length > 0 && (
          <div className="device-log-list small log-lines">
            {[...jobLogs].reverse().map((l, i) => <div key={`j${i}`}>{l}</div>)}
          </div>
        )}
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
