import { fireEvent, render, screen } from "@testing-library/react";
import { AppRunPanel } from "./AppRunPanel";

const profile = { name: "Vita Work (dev)", package: "p", open_label: "a", stop_label: "b", idle_label: "c",
  close_label: "d", sheet_label: "", pre_delay_s: 1, post_delay_s: 1, listen_timeout_s: 6, result_timeout_s: 10 };
const device = { serial: "S", state: "device", model: "M" };
const run = { id: 7, audio_set_id: 1, serial: "S", device_model: "M", profile_name: "Vita Work (dev)",
  app_version: "1.0", created_at: "2026-11-20T15:00:00", summary: { "Đúng": 3, "Sai": 1, "Lỗi thao tác": 1 },
  wer_threshold: 0 };

function panel(over: Partial<Parameters<typeof AppRunPanel>[0]> = {}) {
  return {
    devices: [device], profiles: [profile], runs: [], runId: null, busy: false, readyCount: 5, selectedCount: 0,
    onStart: () => {}, onResume: () => {}, onSelectRun: () => {}, onExportForm: () => {}, onExportZip: () => {},
    ...over,
  };
}

describe("AppRunPanel", () => {
  it("regrades the shown run with a new WER threshold", () => {
    const onSetThreshold = vi.fn().mockResolvedValue(undefined);
    render(<AppRunPanel {...panel({ runs: [run], runId: 7, onSetThreshold })} />);
    const box = screen.getByRole("spinbutton", { name: "Ngưỡng WER để chấm Đúng (%)" }) as HTMLInputElement;
    expect(box.value).toBe("0");
    fireEvent.change(box, { target: { value: "20" } });
    fireEvent.blur(box);
    expect(onSetThreshold).toHaveBeenCalledWith(7, 0.2);
    fireEvent.change(box, { target: { value: "150" } });
    fireEvent.blur(box);
    expect(onSetThreshold).toHaveBeenCalledTimes(1); // out of range: back to the saved value
  });
  it("disables run without a connected device", () => {
    render(<AppRunPanel {...panel({ devices: [] })} />);
    expect((screen.getByText("Chạy trên app (tất cả)") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/Chưa có thiết bị/)).toBeTruthy();
  });
  it("disables run when no sentence passed block 1", () => {
    render(<AppRunPanel {...panel({ readyCount: 0 })} />);
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
  it("lists the 5 newest runs and the rest behind 'Xem thêm'", () => {
    const runs = [9, 8, 7, 6, 5, 4, 3].map((id) => ({ ...run, id }));
    const onSelectRun = vi.fn();
    render(<AppRunPanel {...panel({ runs, runId: 9, onSelectRun })} />);
    const select = screen.getByRole("combobox", { name: "Lần test" });
    const ids = () => Array.from(select.querySelectorAll("option")).map((o) => o.textContent!.split(" ")[0]);
    expect(ids()).toEqual(["#9", "#8", "#7", "#6", "#5", "Xem"]);
    fireEvent.change(select, { target: { value: "__more__" } });
    expect(onSelectRun).not.toHaveBeenCalled();
    expect(ids()).toEqual(["#9", "#8", "#7", "#6", "#5", "#4", "#3"]);
    fireEvent.change(select, { target: { value: "3" } });
    expect(onSelectRun).toHaveBeenCalledWith(3);
  });
  it("keeps an older selected run listed", () => {
    const runs = [9, 8, 7, 6, 5, 4, 3].map((id) => ({ ...run, id }));
    render(<AppRunPanel {...panel({ runs, runId: 3 })} />);
    const opts = Array.from(screen.getByRole("combobox", { name: "Lần test" }).querySelectorAll("option"));
    expect(opts.map((o) => o.textContent!.split(" ")[0])).toEqual(["#9", "#8", "#7", "#6", "#5", "#3", "Xem"]);
    expect(opts[6].textContent).toContain("1 lần test cũ hơn");
  });
  it("run label follows the selection", () => {
    const onStart = vi.fn();
    render(<AppRunPanel {...panel({ selectedCount: 3, onStart })} />);
    fireEvent.click(screen.getByText("Chạy trên app (3)"));
    expect(onStart).toHaveBeenCalledWith("S", "Vita Work (dev)");
  });
  it("picked cases with a run shown are run again inside that run", () => {
    const onRerun = vi.fn();
    const onStart = vi.fn();
    render(<AppRunPanel {...panel({ runs: [run], runId: 7, selectedCount: 2, onRerun, onStart })} />);
    fireEvent.click(screen.getByText("Chạy lại (2) vào #7"));
    expect(onRerun).toHaveBeenCalledWith(7, "S");
    fireEvent.click(screen.getByText("Lần test mới (2)"));
    expect(onStart).toHaveBeenCalledWith("S", "Vita Work (dev)");
  });
  it("no re-run into a run made on another phone", () => {
    render(<AppRunPanel {...panel({ runs: [{ ...run, serial: "X" }], runId: 7, selectedCount: 2, onRerun: () => {} })} />);
    expect((screen.getByText("Chạy lại (2) vào #7") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByText("Lần test mới (2)") as HTMLButtonElement).disabled).toBe(false);
  });
  it("without a pick there is no re-run button", () => {
    render(<AppRunPanel {...panel({ runs: [run], runId: 7, onRerun: () => {} })} />);
    expect(screen.queryByText(/Chạy lại/)).toBeNull();
    expect(screen.getByText("Chạy trên app (tất cả)")).toBeTruthy();
  });
  it("export buttons need a selected run", () => {
    const onExportForm = vi.fn();
    const onExportZip = vi.fn();
    const { rerender } = render(<AppRunPanel {...panel()} />);
    expect((screen.getByRole("button", { name: "Xuất" }) as HTMLButtonElement).disabled).toBe(true);
    rerender(<AppRunPanel {...panel({ runs: [run], runId: 7, onExportForm, onExportZip })} />);
    fireEvent.click(screen.getByRole("button", { name: "Xuất" }));
    fireEvent.click(screen.getByRole("button", { name: /^Excel kết quả/ }));
    fireEvent.click(screen.getByRole("button", { name: "Xuất" }));
    fireEvent.click(screen.getByRole("button", { name: /^Zip phiên/ }));
    expect(onExportForm).toHaveBeenCalled();
    expect(onExportZip).toHaveBeenCalled();
  });
  it("saves the pause between sentences on the selected profile", async () => {
    const onSaveProfile = vi.fn().mockResolvedValue(undefined);
    render(<AppRunPanel {...panel({ onSaveProfile })} />);
    const gap = screen.getByRole("spinbutton", { name: "Nghỉ giữa các câu (giây)" }) as HTMLInputElement;
    expect(gap.value).toBe("0");
    fireEvent.change(gap, { target: { value: "2.5" } });
    fireEvent.blur(gap);
    expect(onSaveProfile).toHaveBeenCalledWith({ ...profile, between_delay_s: 2.5 });
  });
  it("does not save an invalid or unchanged pause", () => {
    const onSaveProfile = vi.fn().mockResolvedValue(undefined);
    render(<AppRunPanel {...panel({ profiles: [{ ...profile, between_delay_s: 3 }], onSaveProfile })} />);
    const gap = screen.getByRole("spinbutton", { name: "Nghỉ giữa các câu (giây)" }) as HTMLInputElement;
    expect(gap.value).toBe("3");
    fireEvent.change(gap, { target: { value: "-1" } });
    expect(gap.getAttribute("aria-invalid")).toBe("true");
    fireEvent.blur(gap);
    fireEvent.change(gap, { target: { value: "3" } });
    fireEvent.blur(gap);
    expect(onSaveProfile).not.toHaveBeenCalled();
    expect(gap.value).toBe("3");
  });
  it("locks the pause while a job runs", () => {
    render(<AppRunPanel {...panel({ busy: true, onSaveProfile: vi.fn() })} />);
    expect((screen.getByRole("spinbutton", { name: "Nghỉ giữa các câu (giây)" }) as HTMLInputElement).disabled).toBe(true);
  });
});
