import { render, screen } from "@testing-library/react";
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
    render(<Sidebar section="data" onSection={() => {}} health={null} sets={[]} currentSetId={null}
      onSelectSet={() => {}} onSettings={() => {}}
      device={{ adb: true, error: null, devices: [{ serial: "S1", state: "device", model: "Pixel 7" }] }} />);
    expect(screen.getByText("ADB · Pixel 7")).toBeTruthy();
  });
});
