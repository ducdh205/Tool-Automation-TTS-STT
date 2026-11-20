import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import App from "./App";
import { api, type Settings } from "./api";

vi.mock("./ws", () => ({ connectEvents: () => () => {} }));

const settings: Settings = {
  voice: "voice-1", wer_threshold: 0, stt_timeout_s: 30, reject_warn_ratio: 0.1,
  max_regen: 3, wyoming_host: "localhost", wyoming_port: 10300, wyoming_cmd: [], port: 8765,
};

afterEach(() => vi.restoreAllMocks());

it("edits run settings from the action bar and saves WER as a ratio", async () => {
  vi.spyOn(api, "profiles").mockResolvedValue([]);
  vi.spyOn(api, "device").mockResolvedValue({ adb: false, devices: [], error: null });
  vi.spyOn(api, "sets").mockResolvedValue([]);
  vi.spyOn(api, "currentJob").mockResolvedValue(null);
  vi.spyOn(api, "health").mockResolvedValue({ wyoming: false, wyoming_error: null, gpu: false, job: null });
  vi.spyOn(api, "settings").mockResolvedValue(settings);
  vi.spyOn(api, "voices").mockResolvedValue([{ id: "voice-2", label: "Giọng thử — Nữ · Bắc · Tự nhiên" }]);
  const save = vi.spyOn(api, "saveSettings").mockImplementation(async (values) => values);

  render(<App />);
  const bar = screen.getAllByRole("button", { name: "Nạp file" })[0].closest(".runbar") as HTMLElement;
  const controls = within(bar);
  const voice = await controls.findByRole("combobox", { name: "Giọng VieNeu" });
  fireEvent.focus(voice);
  await controls.findByRole("option", { name: /Giọng thử/ });
  fireEvent.change(voice, { target: { value: "voice-2" } });
  const wer = controls.getByRole("spinbutton", { name: /Ngưỡng WER/ });
  expect((wer as HTMLInputElement).value).toBe("0");
  expect(controls.getByText("0% là khớp hoàn toàn")).toBeTruthy();
  fireEvent.change(wer, { target: { value: "25" } });
  fireEvent.change(controls.getByRole("spinbutton", { name: "Thời gian chờ STT (giây)" }), { target: { value: "45" } });
  fireEvent.click(controls.getByRole("button", { name: "Lưu cài đặt" }));

  await waitFor(() => expect(save).toHaveBeenCalledWith({ ...settings, voice: "voice-2", wer_threshold: 0.25, stt_timeout_s: 45 }));
  await waitFor(() => expect((controls.getByRole("button", { name: "Lưu cài đặt" }) as HTMLButtonElement).disabled).toBe(true));
  fireEvent.click(screen.getByRole("button", { name: /^Cài đặt$/ }));
  const panel = within(screen.getByRole("heading", { name: "Cài đặt" }).closest(".modal") as HTMLElement);
  expect(panel.getByRole("spinbutton", { name: /Cảnh báo/ })).toBeTruthy();
  expect(panel.queryByRole("spinbutton", { name: /Ngưỡng WER/ })).toBeNull();
  expect(panel.queryByRole("spinbutton", { name: /Thời gian chờ STT/ })).toBeNull();
  expect(panel.queryByRole("combobox")).toBeNull();
});
