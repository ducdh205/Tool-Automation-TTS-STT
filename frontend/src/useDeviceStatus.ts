import { useEffect, useState } from "react";
import { api, type DeviceStatus } from "./api";

export interface DeviceState {
  status: DeviceStatus | null; // null until the first answer, and after a failed request
  error: string | null; // why the last request failed
}

/** The one poller of /api/device (each call lists adb and go-ios devices: keep it single).
 *
 * The next request starts ``intervalMs`` after the previous one ended, so a slow adb never piles calls up.
 */
export function useDeviceStatus(intervalMs: number): DeviceState {
  const [state, setState] = useState<DeviceState>({ status: null, error: null });
  useEffect(() => {
    let alive = true;
    let timer: number | undefined;
    const tick = async () => {
      try {
        const s = await api.device();
        if (alive) setState({ status: s, error: null });
      } catch (e) {
        if (alive) setState({ status: null, error: String(e) });
      }
      if (alive) timer = window.setTimeout(tick, intervalMs);
    };
    tick();
    return () => { alive = false; window.clearTimeout(timer); };
  }, [intervalMs]);
  return state;
}
