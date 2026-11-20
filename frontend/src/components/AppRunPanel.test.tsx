import { render, screen } from "@testing-library/react";
import { AppRunPanel } from "./AppRunPanel";

const profile = { name: "Vita Work (dev)", package: "p", open_label: "a", stop_label: "b", idle_label: "c",
  close_label: "d", sheet_label: "", pre_delay_s: 1, post_delay_s: 1, listen_timeout_s: 6, result_timeout_s: 10 };

describe("AppRunPanel", () => {
  it("disables run without a connected device", () => {
    render(<AppRunPanel devices={[]} profiles={[profile]} runs={[]} runId={null} busy={false} passedCount={5}
      onStart={() => {}} onResume={() => {}} onSelectRun={() => {}} />);
    expect((screen.getByText("Chạy trên app") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText(/Chưa có thiết bị/)).toBeTruthy();
  });
  it("disables run when no sentence passed block 1", () => {
    render(<AppRunPanel devices={[{ serial: "S", state: "device", model: "M" }]} profiles={[profile]} runs={[]}
      runId={null} busy={false} passedCount={0} onStart={() => {}} onResume={() => {}} onSelectRun={() => {}} />);
    expect((screen.getByText("Chạy trên app") as HTMLButtonElement).disabled).toBe(true);
  });
  it("shows app accuracy of the selected run", () => {
    const run = { id: 7, audio_set_id: 1, serial: "S", device_model: "M", profile_name: "Vita Work (dev)",
      app_version: "1.0", created_at: "2026-11-20T15:00:00", summary: { "Đúng": 3, "Sai": 1, "Lỗi thao tác": 1 } };
    render(<AppRunPanel devices={[{ serial: "S", state: "device", model: "M" }]} profiles={[profile]} runs={[run]}
      runId={7} busy={false} passedCount={5} onStart={() => {}} onResume={() => {}} onSelectRun={() => {}} />);
    expect(screen.getByText(/Đúng 75%/)).toBeTruthy();
  });
});
