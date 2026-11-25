import { fireEvent, render, screen } from "@testing-library/react";
import { adbStatus, Sidebar } from "./Sidebar";

describe("adbStatus", () => {
  it("is unknown before the first poll", () => {
    expect(adbStatus(null)).toMatchObject({ level: "off", label: "ADB: đang kiểm tra…" });
  });
  it("reports a missing adb binary", () => {
    expect(adbStatus({ adb: false, error: "x", devices: [] })).toMatchObject({ level: "bad", label: "ADB: không tìm thấy adb" });
  });
  it("reports no device", () => {
    expect(adbStatus({ adb: true, error: null, devices: [] })).toMatchObject({ level: "bad", label: "ADB: chưa có thiết bị" });
  });
  it("shows the model of the connected device", () => {
    const s = adbStatus({ adb: true, error: null, devices: [{ serial: "S1", state: "device", model: "Pixel 7" }] });
    expect(s).toMatchObject({ level: "ok", label: "ADB · Pixel 7" });
    expect(s.title).toContain("S1");
  });
  it("falls back to the serial and counts extra devices", () => {
    const s = adbStatus({ adb: true, error: null, devices: [
      { serial: "S1", state: "device", model: null },
      { serial: "S2", state: "device", model: "M2" },
    ] });
    expect(s.label).toBe("ADB · S1 (+1)");
  });
  it("warns when the only device is not authorized", () => {
    expect(adbStatus({ adb: true, error: null, devices: [{ serial: "S1", state: "unauthorized", model: null }] }))
      .toMatchObject({ level: "warn", label: "ADB · S1 — chưa cho phép" });
  });
});

describe("Sidebar status row", () => {
  const base = { section: "step1" as const, step2Ready: true, onSection: () => {}, sets: [], currentSetId: null, onSelectSet: () => {} };

  it("names the connected phone in the footer", () => {
    render(<Sidebar {...base} health={{ wyoming: true, wyoming_error: null, gpu: true, job: null }}
      device={{ adb: true, error: null, devices: [{ serial: "S1", state: "device", model: "Pixel 7" }] }} />);
    expect(screen.getByText("Pixel 7")).toBeTruthy();
    expect(screen.queryByText(/chưa chạy/)).toBeNull();
  });

  it("spells out what needs attention", () => {
    render(<Sidebar {...base} health={{ wyoming: false, wyoming_error: "refused", gpu: false, job: null }}
      device={{ adb: true, error: null, devices: [{ serial: "S1", state: "unauthorized", model: null }] }} />);
    expect(screen.getByText("STT tham chiếu chưa chạy")).toBeTruthy();
    expect(screen.getByText("ADB · S1 — chưa cho phép")).toBeTruthy();
  });
});

describe("Sidebar steps", () => {
  const base = { onSection: () => {}, health: null, sets: [], currentSetId: null, onSelectSet: () => {} };

  it("has two steps; step 2 is disabled until a row passed", () => {
    render(<Sidebar {...base} section="step1" step2Ready={false} />);
    expect(screen.getByText("Bước 1 — Audio")).toBeTruthy();
    const step2 = screen.getByText("Bước 2 — Test app").closest("button")!;
    expect(step2.disabled).toBe(true);
    expect(step2.title).toBe("Cần ít nhất một câu Đạt ở Bước 1");
    expect(screen.queryByText("Báo cáo")).toBeNull();
  });

  it("switches step and offers the theme switch", () => {
    const onSection = vi.fn();
    render(<Sidebar {...base} onSection={onSection} section="step1" step2Ready />);
    fireEvent.click(screen.getByText("Bước 2 — Test app"));
    expect(onSection).toHaveBeenCalledWith("step2");
    expect(screen.getByTitle("Đổi giao diện sáng / tối")).toBeTruthy();
  });
});

describe("Sidebar audio sets", () => {
  const set = { id: 3, name: "E2E Climate Sync", source_file: "f.xlsx", sheets: ["S1"], voice: null,
    created_at: "", summary: { "Đạt": 1, "Chờ": 260 } };
  const base = { section: "step1" as const, step2Ready: true, onSection: () => {}, health: null,
    sets: [set], currentSetId: 3, onSelectSet: () => {} };

  it("deletes a set after the user confirms", () => {
    const onDeleteSet = vi.fn();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<Sidebar {...base} onDeleteSet={onDeleteSet} />);
    fireEvent.click(screen.getByRole("button", { name: "Xóa bộ E2E Climate Sync" }));
    expect(confirm.mock.calls[0][0]).toContain("E2E Climate Sync");
    expect(confirm.mock.calls[0][0]).toContain("261 câu");
    expect(onDeleteSet).toHaveBeenCalledWith(3);
  });

  it("keeps the set when the user cancels", () => {
    const onDeleteSet = vi.fn();
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<Sidebar {...base} onDeleteSet={onDeleteSet} />);
    fireEvent.click(screen.getByRole("button", { name: "Xóa bộ E2E Climate Sync" }));
    expect(onDeleteSet).not.toHaveBeenCalled();
  });

  it("locks deletion while a job runs", () => {
    render(<Sidebar {...base} onDeleteSet={() => {}} deleteLocked="Đang chạy job" />);
    const del = screen.getByRole("button", { name: "Xóa bộ E2E Climate Sync" }) as HTMLButtonElement;
    expect(del.disabled).toBe(true);
    expect(del.title).toBe("Đang chạy job");
  });
});

describe("Sidebar clear all data", () => {
  const set = { id: 3, name: "Bộ A", source_file: "f.xlsx", sheets: ["S1"], voice: null,
    created_at: "", summary: { "Chờ": 2 } };
  const base = { section: "step1" as const, step2Ready: true, onSection: () => {}, health: null,
    sets: [set, { ...set, id: 4, name: "Bộ B" }], currentSetId: 3, onSelectSet: () => {} };

  it("clears everything after the user confirms", () => {
    const onClearAll = vi.fn();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<Sidebar {...base} onClearAll={onClearAll} />);
    fireEvent.click(screen.getByRole("button", { name: "Xóa toàn bộ dữ liệu" }));
    expect(confirm.mock.calls[0][0]).toContain("2 bộ audio");
    expect(confirm.mock.calls[0][0]).toContain("Cài đặt và hồ sơ app được giữ lại");
    expect(onClearAll).toHaveBeenCalledTimes(1);
  });

  it("does nothing when the user cancels", () => {
    const onClearAll = vi.fn();
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<Sidebar {...base} onClearAll={onClearAll} />);
    fireEvent.click(screen.getByRole("button", { name: "Xóa toàn bộ dữ liệu" }));
    expect(onClearAll).not.toHaveBeenCalled();
  });

  it("is locked while a job runs and hidden without a handler", () => {
    const { unmount } = render(<Sidebar {...base} onClearAll={() => {}} deleteLocked="Đang chạy job" />);
    const btn = screen.getByRole("button", { name: "Xóa toàn bộ dữ liệu" }) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    expect(btn.title).toBe("Đang chạy job");
    unmount();
    render(<Sidebar {...base} />);
    expect(screen.queryByRole("button", { name: "Xóa toàn bộ dữ liệu" })).toBeNull();
  });
});
