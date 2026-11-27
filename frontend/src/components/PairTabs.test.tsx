import { fireEvent, render, screen } from "@testing-library/react";
import { PairTabs } from "./PairTabs";

const base = { audio_set_id: 1, profile_name: "p", app_version: null, created_at: "2026-11-27T13:00:00",
  summary: {}, wer_threshold: 0 };
const runs = [{ ...base, id: 3, serial: "A1", device_model: "22120RN86G", pair_run_id: 4 },
  { ...base, id: 4, serial: "I1", device_model: "iPhone 15", pair_run_id: 3 }];
const devices = [{ serial: "A1", state: "device", model: "22120RN86G", platform: "android" as const },
  { serial: "I1", state: "device", model: "iPhone 15", platform: "ios" as const }];

describe("PairTabs", () => {
  it("shows pair tabs and switches runs", () => {
    const onSelect = vi.fn();
    render(<PairTabs runs={[runs[0], runs[1]]} devices={devices} current={3} onSelect={onSelect} />);
    const android = screen.getByRole("button", { name: "Android · 22120RN86G" });
    const iphone = screen.getByRole("button", { name: "iPhone · iPhone 15" });
    expect(android.getAttribute("aria-pressed")).toBe("true");
    expect(iphone.getAttribute("aria-pressed")).toBe("false");
    fireEvent.click(iphone);
    expect(onSelect).toHaveBeenCalledWith(4);
  });
  it("uses the platform saved with the run when the phone is unplugged", () => {
    render(<PairTabs runs={[{ ...runs[0], platform: "android" }, { ...runs[1], platform: "ios" }]} devices={[]}
      current={3} onSelect={() => {}} />);
    expect(screen.getByRole("button", { name: "iPhone · iPhone 15" })).toBeTruthy();
  });
  it("names the phone only when its platform is unknown", () => {
    render(<PairTabs runs={[runs[0], runs[1]]} devices={[]} current={4} onSelect={() => {}} />);
    expect(screen.getByRole("button", { name: "22120RN86G" })).toBeTruthy();
  });
});
