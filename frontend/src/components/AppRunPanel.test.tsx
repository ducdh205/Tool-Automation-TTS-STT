import { fireEvent, render, screen } from "@testing-library/react";
import { AppRunPanel } from "./AppRunPanel";

const profile = { name: "Vita Work (dev)", package: "p", open_label: "a", stop_label: "b", idle_label: "c",
  close_label: "d", sheet_label: "", pre_delay_s: 1, post_delay_s: 1, listen_timeout_s: 6, result_timeout_s: 10 };
const device = { serial: "S", state: "device", model: "M" };
const run = { id: 7, audio_set_id: 1, serial: "S", device_model: "M", profile_name: "Vita Work (dev)",
  app_version: "1.0", created_at: "2026-11-20T15:00:00", summary: { "Đúng": 3, "Sai": 1, "Lỗi thao tác": 1 } };

function panel(over: Partial<Parameters<typeof AppRunPanel>[0]> = {}) {
  return {
    devices: [device], profiles: [profile], runs: [], runId: null, busy: false, passedCount: 5, selectedCount: 0,
    onStart: () => {}, onResume: () => {}, onSelectRun: () => {}, onExportForm: () => {}, onExportZip: () => {},
    ...over,
  };
}

describe("AppRunPanel", () => {
  it("disables run without a connected device", () => {
    render(<AppRunPanel {...panel({ devices: [] })} />);
    expect((screen.getByText("Chạy trên app (tất cả)") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/Chưa có thiết bị/)).toBeTruthy();
  });
  it("disables run when no sentence passed block 1", () => {
    render(<AppRunPanel {...panel({ passedCount: 0 })} />);
    expect((screen.getByText("Chạy trên app (tất cả)") as HTMLButtonElement).disabled).toBe(true);
  });
  it("asks for the device only when several phones are connected", () => {
    const { rerender } = render(<AppRunPanel {...panel()} />);
    expect(screen.queryByRole("combobox", { name: "Thiết bị" })).toBeNull();
    const onStart = vi.fn();
    rerender(<AppRunPanel {...panel({ devices: [device, { serial: "T", state: "device", model: "N" }], onStart })} />);
    fireEvent.change(screen.getByRole("combobox", { name: "Thiết bị" }), { target: { value: "T" } });
    fireEvent.click(screen.getByText("Chạy trên app (tất cả)"));
    expect(onStart).toHaveBeenCalledWith("T", "Vita Work (dev)");
  });
  it("offers resume for the cases left over", () => {
    const onResume = vi.fn();
    render(<AppRunPanel {...panel({ runs: [run], runId: 7, onResume })} />);
    fireEvent.click(screen.getByText("Chạy tiếp (1)"));
    expect(onResume).toHaveBeenCalledWith(7);
  });
  it("run label follows the selection", () => {
    const onStart = vi.fn();
    render(<AppRunPanel {...panel({ selectedCount: 3, onStart })} />);
    fireEvent.click(screen.getByText("Chạy trên app (3)"));
    expect(onStart).toHaveBeenCalledWith("S", "Vita Work (dev)");
  });
  it("export buttons need a selected run", () => {
    const onExportForm = vi.fn();
    const onExportZip = vi.fn();
    const { rerender } = render(<AppRunPanel {...panel()} />);
    expect((screen.getByRole("button", { name: "Xuất" }) as HTMLButtonElement).disabled).toBe(true);
    rerender(<AppRunPanel {...panel({ runs: [run], runId: 7, onExportForm, onExportZip })} />);
    fireEvent.click(screen.getByRole("button", { name: "Xuất" }));
    fireEvent.click(screen.getByRole("button", { name: /^Excel theo form/ }));
    fireEvent.click(screen.getByRole("button", { name: "Xuất" }));
    fireEvent.click(screen.getByRole("button", { name: /^Zip phiên/ }));
    expect(onExportForm).toHaveBeenCalled();
    expect(onExportZip).toHaveBeenCalled();
  });
});
