import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { api, ApiError, type DeviceStatus, type Health, type TtsDevice } from "../api";
import { readiness, TestbenchPanel } from "./TestbenchPanel";

const HEALTHY: Health = { wyoming: true, wyoming_error: null, gpu: false, job: null };
const ONE: DeviceStatus = { adb: true, error: null, devices: [{ serial: "S1", state: "device", model: "Pixel 7" }] };

function tts(over: Partial<TtsDevice> = {}): TtsDevice {
  return {
    device: "cpu", active: "cpu", load_error: null, nvidia: true, gpu_name: "RTX 3060", torch_cuda: true, uv: true,
    install: { state: "idle", log_tail: [], error: null }, ...over,
  };
}

async function renderPanel(t: TtsDevice, props: { health?: Health | null; device?: DeviceStatus | null; jobRunning?: boolean } = {}) {
  vi.spyOn(api, "ttsDevice").mockResolvedValue(t);
  render(<TestbenchPanel health={props.health ?? HEALTHY} device={props.device ?? ONE} jobRunning={props.jobRunning ?? false} />);
  await screen.findByText(t.device === "cuda" ? /^GPU · / : "CPU");
}

afterEach(() => vi.restoreAllMocks());

describe("readiness", () => {
  it("is ready with STT up and one connected phone", () => {
    expect(readiness(HEALTHY, ONE)).toEqual({ ready: true, hint: null });
  });
  it("names the first thing to fix, STT first", () => {
    const noStt = { ...HEALTHY, wyoming: false };
    expect(readiness(noStt, { adb: false, error: null, devices: [] }).hint)
      .toBe("Chưa chạy STT tham chiếu — Verify sẽ không dùng được");
    expect(readiness(HEALTHY, { adb: false, error: null, devices: [] }).hint).toBe("Không tìm thấy adb");
    expect(readiness(HEALTHY, { adb: true, error: null, devices: [] }).hint)
      .toBe("Cắm điện thoại qua USB và bật Gỡ lỗi USB");
    const r = readiness(HEALTHY, { adb: true, error: null, devices: [{ serial: "S1", state: "unauthorized", model: null }] });
    expect(r).toEqual({ ready: false, hint: 'Mở khóa điện thoại và bấm "Cho phép" gỡ lỗi USB' });
  });
  it("accepts an iPhone without adb and asks for WebDriverAgent when it is down", () => {
    const iphone = { serial: "U1", state: "device", model: "iPhone 15", platform: "ios" as const };
    expect(readiness(HEALTHY, { adb: false, ios: true, error: null, devices: [iphone] }))
      .toEqual({ ready: true, hint: null });
    expect(readiness(HEALTHY, { adb: false, ios: true, error: null, devices: [{ ...iphone, state: "no_wda" }] }))
      .toEqual({ ready: false, hint: "Bấm \"Kết nối iPhone\" ở khung Thiết bị" });
  });
});

describe("TestbenchPanel", () => {
  it("lists every phone", async () => {
    await renderPanel(tts(), { device: { adb: true, error: null, devices: [
      { serial: "S1", state: "device", model: "Pixel 7" },
      { serial: "S2", state: "unauthorized", model: null },
    ] } });
    expect(screen.getByText("Pixel 7")).toBeTruthy();
    expect(screen.getByText("S2")).toBeTruthy();
    expect(screen.getByText("Chưa cho phép")).toBeTruthy();
    expect(screen.getByText("Sẵn sàng test")).toBeTruthy();
  });

  it("locks GPU without an NVIDIA card", async () => {
    await renderPanel(tts({ nvidia: false, gpu_name: null, torch_cuda: false }));
    const gpu = screen.getByRole("button", { name: "GPU" }) as HTMLButtonElement;
    expect(gpu.disabled).toBe(true);
    expect(gpu.title).toBe("Máy không có GPU NVIDIA");
  });

  it("switches without asking when CUDA is ready", async () => {
    await renderPanel(tts());
    const confirm = vi.spyOn(window, "confirm");
    const set = vi.spyOn(api, "setTtsDevice").mockResolvedValue(tts({ device: "cuda", active: null }));
    const install = vi.spyOn(api, "installCuda");
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "GPU" })); });
    expect(set).toHaveBeenCalledWith("cuda");
    expect(confirm).not.toHaveBeenCalled();
    expect(install).not.toHaveBeenCalled();
  });

  it("asks before installing when CUDA is missing", async () => {
    await renderPanel(tts({ torch_cuda: false }));
    vi.spyOn(api, "setTtsDevice").mockRejectedValue(new ApiError("Chưa có PyTorch CUDA", 409));
    const install = vi.spyOn(api, "installCuda").mockResolvedValue(tts({ install: { state: "running", log_tail: [], error: null } }));
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "GPU" })); });
    expect(confirm).toHaveBeenCalledTimes(1);
    expect(install).not.toHaveBeenCalled();

    confirm.mockReturnValue(true);
    vi.spyOn(api, "ttsDevice").mockResolvedValue(tts({ torch_cuda: false, install: { state: "running", log_tail: [], error: null } }));
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "GPU" })); });
    expect(install).toHaveBeenCalledTimes(1);
    await screen.findByText("Đang cài PyTorch CUDA…");
  });

  it("locks the switch while a job runs", async () => {
    await renderPanel(tts(), { jobRunning: true });
    for (const name of ["CPU", "GPU"]) {
      const b = screen.getByRole("button", { name }) as HTMLButtonElement;
      expect(b.disabled).toBe(true);
      expect(b.title).toBe("Đang có tác vụ chạy");
    }
  });

  it("shows an install failure with retry", async () => {
    await renderPanel(tts({ torch_cuda: false, install: { state: "failed", log_tail: ["x1"], error: "hỏng mạng" } }));
    expect(screen.getByText("hỏng mạng")).toBeTruthy();
    const install = vi.spyOn(api, "installCuda").mockResolvedValue(tts({ install: { state: "running", log_tail: [], error: null } }));
    await act(async () => { fireEvent.click(screen.getByRole("button", { name: "Thử lại" })); });
    expect(install).toHaveBeenCalledTimes(1);
  });

  it("warns when GPU was chosen but CPU is in use", async () => {
    await renderPanel(tts({ device: "cuda", active: "cpu", load_error: "boom" }));
    expect(screen.getByText("Không nạp được GPU, đang dùng CPU")).toBeTruthy();
  });

  it("collapses", async () => {
    await renderPanel(tts());
    fireEvent.click(screen.getByRole("button", { name: "Thu gọn" }));
    expect(screen.queryByText("Pixel 7")).toBeNull();
    await waitFor(() => expect(screen.getByRole("button", { name: "Mở rộng" })).toBeTruthy());
  });
});
