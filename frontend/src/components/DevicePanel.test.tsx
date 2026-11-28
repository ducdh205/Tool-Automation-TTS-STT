import { render, screen, waitFor } from "@testing-library/react";
import { DevicePanel } from "./DevicePanel";
import { api, type DeviceStatus } from "../api";

const profile = { name: "P", package: "p", open_label: "a", stop_label: "b", idle_label: "c", close_label: "d",
  sheet_label: "", pre_delay_s: 0.3, post_delay_s: 1, listen_timeout_s: 6, result_timeout_s: 10 };

const ok = (status: DeviceStatus) => ({ status, error: null });

describe("DevicePanel lock (review2 #4)", () => {
  it("locks manual control and pin mode while a block 2 job drives the phone", async () => {
    const device = ok({ adb: true, error: null, devices: [{ serial: "S", state: "device", model: "M" }], busy: ["S"] } as never);
    globalThis.fetch = vi.fn().mockResolvedValue(new Response(new Blob(["x"]), { status: 200 })) as never;
    globalThis.URL.createObjectURL = () => "blob:x";
    globalThis.URL.revokeObjectURL = () => {};
    render(<DevicePanel device={device} profile={profile} />);
    await waitFor(() => expect(screen.getByText(/đang chạy test app/i)).toBeTruthy());
    expect((screen.getByText(/Ghim nút/) as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("DevicePanel iPhone connect button", () => {
  const base = { udid: null, bundle: null, external: false, step: null, detail: null };
  it("offers Kết nối iPhone when WDA is down, starts it and shows the reason it failed", async () => {
    const device = ok({
      adb: false, ios: true, error: null, devices: [{ serial: "U", state: "no_wda", model: "iPhone 15", platform: "ios" }],
    } as never);
    const status = vi.spyOn(api, "iosConnectStatus").mockResolvedValue({ ...base, state: "idle", error: null });
    const start = vi.spyOn(api, "iosConnect").mockResolvedValue({ ...base, state: "starting", step: "Đang tìm iPhone…", error: null });
    render(<DevicePanel device={device} />);
    const btn = await screen.findByRole("button", { name: "Kết nối iPhone" });
    btn.click();
    await waitFor(() => expect(start).toHaveBeenCalled());
    expect(await screen.findByText("Đang tìm iPhone…")).toBeTruthy();
    status.mockResolvedValue({ ...base, state: "error", error: "Chưa bật Chế độ nhà phát triển", detail: "DeveloperModeIsNotEnabledError" });
    expect(await screen.findByText("Chưa bật Chế độ nhà phát triển", {}, { timeout: 3000 })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Kết nối lại" })).toBeTruthy();
  });
});

describe("DevicePanel follows the shown run", () => {
  it("follows the serial prop", async () => {
    const device = ok({
      adb: true, error: null, busy: [],
      devices: [{ serial: "S1", state: "device", model: "M1" }, { serial: "S2", state: "device", model: "M2" }],
    } as never);
    globalThis.fetch = vi.fn().mockResolvedValue(new Response(new Blob(["x"]), { status: 200 })) as never;
    globalThis.URL.createObjectURL = () => "blob:x";
    globalThis.URL.revokeObjectURL = () => {};
    const { rerender } = render(<DevicePanel device={device} serial="S2" />);
    const pick = await screen.findByDisplayValue("M2");
    expect((pick as HTMLSelectElement).value).toBe("S2");
    rerender(<DevicePanel device={device} serial="S1" />);
    await waitFor(() => expect((screen.getByDisplayValue("M1") as HTMLSelectElement).value).toBe("S1"));
  });
});

describe("DevicePanel device states", () => {
  it("waits for the first answer", () => {
    render(<DevicePanel device={{ status: null, error: null }} />);
    expect(screen.getByText("Đang kiểm tra thiết bị…")).toBeTruthy();
  });

  it("a failed /api/device reads as no adb, with the reason", () => {
    render(<DevicePanel device={{ status: null, error: "Error: 500" }} />);
    expect(screen.getByText("Không tìm thấy adb")).toBeTruthy();
    expect(screen.getByText("Error: 500")).toBeTruthy();
  });
});
