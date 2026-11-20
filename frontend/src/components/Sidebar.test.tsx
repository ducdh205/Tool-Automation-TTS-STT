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

describe("Sidebar ADB line", () => {
  it("renders the device name in the footer", () => {
    render(<Sidebar section="step1" step2Ready onSection={() => {}} health={null} sets={[]} currentSetId={null}
      onSelectSet={() => {}} onSettings={() => {}}
      device={{ adb: true, error: null, devices: [{ serial: "S1", state: "device", model: "Pixel 7" }] }} />);
    expect(screen.getByText("ADB · Pixel 7")).toBeTruthy();
  });
});

describe("Sidebar steps", () => {
  const base = { onSection: () => {}, health: null, sets: [], currentSetId: null, onSelectSet: () => {}, onSettings: () => {} };

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
