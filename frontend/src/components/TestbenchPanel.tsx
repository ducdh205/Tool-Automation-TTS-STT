import { useCallback, useEffect, useState } from "react";
import { api, ApiError, type DeviceStatus, type Health, type TtsDevice, type TtsDeviceKind } from "../api";
import { Icon } from "./Icon";
import { ThemeSwitch } from "./ThemeSwitch";

type Level = "ok" | "warn" | "bad" | "off";

const OPEN_KEY = "testbench.open";
const NO_NVIDIA = "Máy không có GPU NVIDIA";
const NO_TORCH = "Chưa có PyTorch CUDA";
const BUSY = "Đang có tác vụ chạy";
const INSTALL_ASK = "Chưa có PyTorch CUDA. Tải và cài khoảng 2.5 GB? Trong lúc cài vẫn sinh audio bằng CPU được.";
const STATE: Record<string, { label: string; level: Level }> = {
  device: { label: "Đã kết nối", level: "ok" },
  unauthorized: { label: "Chưa cho phép", level: "warn" },
  offline: { label: "Mất kết nối", level: "warn" },
  no_wda: { label: "Chưa chạy WDA", level: "warn" },
};

/** Ready to test = reference STT up and at least one phone connected; else the first thing to fix. */
export function readiness(health: Health | null, device: DeviceStatus | null): { ready: boolean; hint: string | null } {
  const online = device?.devices.some((d) => d.state === "device") ?? false;
  let hint: string | null = null;
  if (!health?.wyoming) hint = "Chưa chạy STT tham chiếu — Verify sẽ không dùng được";
  else if (device && !device.adb && !device.ios) hint = "Không tìm thấy adb";
  else if (device && device.devices.length === 0) hint = "Cắm điện thoại qua USB và bật Gỡ lỗi USB";
  else if (device && !online && device.devices.some((d) => d.state === "unauthorized"))
    hint = 'Mở khóa điện thoại và bấm "Cho phép" gỡ lỗi USB';
  else if (device && !online && device.devices.some((d) => d.state === "no_wda"))
    hint = "Chạy WebDriverAgent trên iPhone và chuyển cổng 8100";
  return { ready: !!health?.wyoming && online, hint };
}

function readOpen(): boolean {
  try { return localStorage.getItem(OPEN_KEY) !== "0"; } catch { return true; }
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="tb-row">
      <span className="tb-label">{label}</span>
      <div className="tb-values">{children}</div>
    </div>
  );
}

function Status({ level, text, title }: { level: Level; text: string; title?: string }) {
  return (
    <span className={`tb-status ${level}`} title={title}>
      <span className={`dot ${level}`} />
      <span className="ellipsis">{text}</span>
    </span>
  );
}

function useTtsDevice(): [TtsDevice | null, (t: TtsDevice) => void] {
  const [tts, setTts] = useState<TtsDevice | null>(null);
  const installing = tts?.install.state === "running";
  useEffect(() => {
    let alive = true;
    let timer: number;
    const tick = async () => {
      try {
        const t = await api.ttsDevice();
        if (!alive) return;
        setTts(t);
        timer = window.setTimeout(tick, t.install.state === "running" ? 2000 : 10000);
      } catch {
        if (alive) timer = window.setTimeout(tick, 10000);
      }
    };
    tick();
    return () => { alive = false; window.clearTimeout(timer); };
  }, [installing]);
  return [tts, setTts];
}

export function TestbenchPanel({ health, device, jobRunning }: {
  health: Health | null; device: DeviceStatus | null; jobRunning: boolean;
}) {
  const [open, setOpen] = useState(readOpen);
  const [tts, setTts] = useTtsDevice();
  const [error, setError] = useState<string | null>(null);
  const { ready, hint } = readiness(health, device);

  const toggle = () => {
    const next = !open;
    setOpen(next);
    try { localStorage.setItem(OPEN_KEY, next ? "1" : "0"); } catch { /* private mode */ }
  };

  const install = useCallback(async () => {
    setError(null);
    try { setTts(await api.installCuda()); } catch (e) { setError(e instanceof Error ? e.message : String(e)); }
  }, [setTts]);

  const choose = async (d: TtsDeviceKind) => {
    if (!tts || d === tts.device) return;
    setError(null);
    try {
      setTts(await api.setTtsDevice(d));
    } catch (e) {
      if (e instanceof ApiError && e.status === 409 && e.message === NO_TORCH) {
        if (window.confirm(INSTALL_ASK)) await install();
      } else {
        setError(e instanceof Error ? e.message : String(e));
      }
    }
  };

  const installing = tts?.install.state === "running";
  const locked = jobRunning || installing;
  const gpuLocked = locked || tts?.nvidia === false;
  const gpuTitle = locked ? BUSY : tts?.nvidia === false ? NO_NVIDIA : tts?.gpu_name ?? "GPU";
  const phones = device?.devices ?? [];

  return (
    <div className="testbench">
      <div className="tb-head">
        <span className="tb-title">Thiết bị kiểm thử</span>
        <span className={`dot ${ready ? "ok" : "bad"}`} />
        <span className="spacer" />
        <ThemeSwitch />
        <button className="icon-btn tb-toggle" aria-label={open ? "Thu gọn" : "Mở rộng"} onClick={toggle}>
          <span className={open ? "tb-chevron open" : "tb-chevron"}><Icon name="chevron" size={14} /></span>
        </button>
      </div>
      {open && (
        <>
          <div className={`tb-badge ${ready ? "ok" : "bad"}`}>{ready ? "Sẵn sàng test" : "Chưa sẵn sàng test"}</div>
          <Row label="Điện thoại">
            {!device && <Status level="off" text="Đang kiểm tra…" />}
            {device && !device.adb && !device.ios && <Status level="bad" text="Không tìm thấy adb" title={device.error ?? undefined} />}
            {(device?.adb || device?.ios) && phones.length === 0 && <Status level="bad" text="Chưa có thiết bị" />}
            {phones.map((d) => {
              const st = STATE[d.state] ?? { label: d.state, level: "warn" as Level };
              return (
                <div key={d.serial} className="tb-phone" title={d.serial}>
                  <span className={`dot ${st.level}`} />
                  <span className="ellipsis">{d.model ?? d.serial}</span>
                  <span className={`tb-phone-state ${st.level}`}>{st.label}</span>
                </div>
              );
            })}
          </Row>
          <Row label="STT tham chiếu">
            {health?.wyoming
              ? <Status level="ok" text="Sẵn sàng" />
              : <Status level={health ? "bad" : "off"} text="Chưa chạy" title={health?.wyoming_error ?? undefined} />}
          </Row>
          <Row label="Sinh audio (TTS)">
            <div className="tb-switch" role="radiogroup" aria-label="Thiết bị sinh audio">
              <button aria-pressed={tts?.device !== "cuda"} className={tts?.device !== "cuda" ? "on" : ""}
                disabled={!tts || locked} title={locked ? BUSY : "Chạy bằng CPU"} onClick={() => choose("cpu")}>CPU</button>
              <button aria-pressed={tts?.device === "cuda"} className={tts?.device === "cuda" ? "on" : ""}
                disabled={!tts || gpuLocked} title={gpuTitle} onClick={() => choose("cuda")}>GPU</button>
            </div>
            {tts && <span className="tb-sub">{tts.device === "cuda" ? `GPU · ${tts.gpu_name ?? "CUDA"}` : "CPU"}</span>}
            {tts?.device === "cuda" && tts.active === "cpu" && (
              <Status level="warn" text="Không nạp được GPU, đang dùng CPU" title={tts.load_error ?? undefined} />
            )}
            {installing && (
              <div className="tb-install">
                <span>Đang cài PyTorch CUDA…</span>
                {tts.install.log_tail.length > 0 && <small className="ellipsis">{tts.install.log_tail.at(-1)}</small>}
              </div>
            )}
            {tts?.install.state === "failed" && (
              <div className="tb-install bad">
                <span>{tts.install.error}</span>
                <button className="link-btn" onClick={install}>Thử lại</button>
              </div>
            )}
            {error && <span className="tb-error">{error}</span>}
          </Row>
          {hint && <p className="tb-hint">{hint}</p>}
        </>
      )}
    </div>
  );
}
