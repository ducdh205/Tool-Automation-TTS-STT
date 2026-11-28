import { act, renderHook } from "@testing-library/react";
import { api, type DeviceStatus } from "./api";
import { useDeviceStatus } from "./useDeviceStatus";

const ONE: DeviceStatus = { adb: true, error: null, devices: [{ serial: "S", state: "device", model: "M" }] };

beforeEach(() => vi.useFakeTimers());
afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

const flush = () => act(async () => { await Promise.resolve(); await Promise.resolve(); });

it("polls at the given interval, one request at a time", async () => {
  const device = vi.spyOn(api, "device").mockResolvedValue(ONE);
  const { result } = renderHook(() => useDeviceStatus(2000));
  await flush();
  expect(result.current).toEqual({ status: ONE, error: null });
  expect(device).toHaveBeenCalledTimes(1);
  await act(async () => { vi.advanceTimersByTime(2000); });
  await flush();
  expect(device).toHaveBeenCalledTimes(2);
});

it("a failed request clears the status and keeps the error apart", async () => {
  vi.spyOn(api, "device").mockResolvedValueOnce(ONE).mockRejectedValueOnce(new Error("mất kết nối"));
  const { result } = renderHook(() => useDeviceStatus(1000));
  await flush();
  await act(async () => { vi.advanceTimersByTime(1000); });
  await flush();
  expect(result.current.status).toBeNull();
  expect(result.current.error).toContain("mất kết nối");
});

it("stops polling on unmount", async () => {
  const device = vi.spyOn(api, "device").mockResolvedValue(ONE);
  const { unmount } = renderHook(() => useDeviceStatus(1000));
  await flush();
  unmount();
  await act(async () => { vi.advanceTimersByTime(5000); });
  expect(device).toHaveBeenCalledTimes(1);
});
