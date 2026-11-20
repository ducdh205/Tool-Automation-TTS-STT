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
  // The bar shows the settings in effect; editing happens in one panel behind that summary.
  const trigger = await controls.findByRole("button", { name: /voice-1 · WER ≤ 0% · 30s/ });
  expect(controls.queryByRole("combobox", { name: "Giọng VieNeu" })).toBeNull();
  expect(screen.queryByRole("button", { name: /^Cài đặt$/ })).toBeNull();
  fireEvent.click(trigger);
  const panel = within(controls.getByRole("dialog", { name: "Cài đặt chạy" }));
  const voice = panel.getByRole("combobox", { name: "Giọng VieNeu" });
  fireEvent.focus(voice);
  await panel.findByRole("option", { name: /Giọng thử/ });
  fireEvent.change(voice, { target: { value: "voice-2" } });
  expect(trigger.textContent).toContain("voice-2");
  expect(trigger.textContent).toContain("chưa lưu");

  const info = panel.getByRole("button", { name: "Cách chấm WER và CER" });
  fireEvent.click(info);
  expect(panel.getByRole("dialog", { name: "Cách chấm WER và CER" }).textContent).toContain("chỉ để tham khảo");
  fireEvent.click(info);
  expect(panel.queryByRole("dialog", { name: "Cách chấm WER và CER" })).toBeNull();

  const wer = panel.getByRole("spinbutton", { name: /Ngưỡng WER/ });
  expect((wer as HTMLInputElement).value).toBe("0");
  expect(panel.getByText("0% là khớp hoàn toàn")).toBeTruthy();
  fireEvent.change(wer, { target: { value: "25" } });
  fireEvent.change(panel.getByRole("spinbutton", { name: "Thời gian chờ STT (giây)" }), { target: { value: "45" } });
  const reject = panel.getByRole("spinbutton", { name: /Cảnh báo khi tỉ lệ loại/ });
  expect((reject as HTMLInputElement).value).toBe("10");
  fireEvent.change(reject, { target: { value: "20" } });
  fireEvent.click(panel.getByRole("button", { name: "Lưu cài đặt" }));

  await waitFor(() => expect(save).toHaveBeenCalledWith({
    ...settings, voice: "voice-2", wer_threshold: 0.25, stt_timeout_s: 45, reject_warn_ratio: 0.2,
  }));
  // Saved: the panel closes and the summary shows the new values.
  await waitFor(() => expect(controls.queryByRole("dialog", { name: "Cài đặt chạy" })).toBeNull());
  expect(trigger.textContent).toContain("WER ≤ 25% · 45s");
  expect(trigger.textContent).not.toContain("chưa lưu");
});

it("deletes the open audio set and opens the next one", async () => {
  const mk = (id: number, name: string) => ({ id, name, source_file: "f.xlsx", sheets: ["S1"], voice: null,
    created_at: "", summary: { "Chờ": 1 } });
  vi.spyOn(api, "profiles").mockResolvedValue([]);
  vi.spyOn(api, "device").mockResolvedValue({ adb: false, devices: [], error: null });
  const sets = vi.spyOn(api, "sets").mockResolvedValue([mk(2, "Bộ B"), mk(1, "Bộ A")]);
  vi.spyOn(api, "currentJob").mockResolvedValue(null);
  vi.spyOn(api, "health").mockResolvedValue({ wyoming: true, wyoming_error: null, gpu: true, job: null });
  vi.spyOn(api, "settings").mockResolvedValue(settings);
  vi.spyOn(api, "appRuns").mockResolvedValue([]);
  const items = vi.spyOn(api, "items").mockResolvedValue([]);
  const del = vi.spyOn(api, "deleteSet").mockResolvedValue({ ok: true });
  vi.spyOn(window, "confirm").mockReturnValue(true);

  render(<App />);
  await waitFor(() => expect(items).toHaveBeenCalledWith(2));
  sets.mockResolvedValue([mk(1, "Bộ A")]);
  fireEvent.click(await screen.findByRole("button", { name: "Xóa bộ Bộ B" }));

  await waitFor(() => expect(del).toHaveBeenCalledWith(2));
  await waitFor(() => expect(items).toHaveBeenCalledWith(1));
  expect(screen.queryByText("Bộ B")).toBeNull();
});
