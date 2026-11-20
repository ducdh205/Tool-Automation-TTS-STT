import { render, screen, waitFor } from "@testing-library/react";
import { DevicePanel } from "./DevicePanel";
import { api } from "../api";

const profile = { name: "P", package: "p", open_label: "a", stop_label: "b", idle_label: "c", close_label: "d",
  sheet_label: "", pre_delay_s: 0.3, post_delay_s: 1, listen_timeout_s: 6, result_timeout_s: 10 };

describe("DevicePanel lock (review2 #4)", () => {
  it("locks manual control and pin mode while a block 2 job drives the phone", async () => {
    vi.spyOn(api, "device").mockResolvedValue({
      adb: true, error: null, devices: [{ serial: "S", state: "device", model: "M" }], busy: "S",
    } as never);
    globalThis.fetch = vi.fn().mockResolvedValue(new Response(new Blob(["x"]), { status: 200 })) as never;
    globalThis.URL.createObjectURL = () => "blob:x";
    globalThis.URL.revokeObjectURL = () => {};
    render(<DevicePanel profile={profile} />);
    await waitFor(() => expect(screen.getByText(/đang chạy test app/i)).toBeTruthy());
    expect((screen.getByText(/Ghim nút/) as HTMLButtonElement).disabled).toBe(true);
  });
});
