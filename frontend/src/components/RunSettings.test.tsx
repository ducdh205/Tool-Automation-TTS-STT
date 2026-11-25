import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { RunSettings } from "./RunSettings";

const settings = {
  voice: "voice-1", voice_trung: "voice-t", voice_nam: "voice-n", voice_speed: 1,
  wer_threshold: 0, stt_timeout_s: 30, reject_warn_ratio: 0.1,
};

class FakeAudio {
  static urls: string[] = [];
  static paused = 0;
  onended: (() => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(url: string) { FakeAudio.urls.push(url); }
  play() { return Promise.resolve(); }
  pause() { FakeAudio.paused += 1; }
}

function openPanel() {
  render(<RunSettings settings={settings} busy={false} saving={false} setCount={0} onSave={async () => {}} />);
  fireEvent.click(screen.getByRole("button", { name: /voice-1/ }));
  return within(screen.getByRole("dialog", { name: "Cài đặt chạy" }));
}

describe("RunSettings speed preview", () => {
  beforeEach(() => {
    FakeAudio.urls = [];
    FakeAudio.paused = 0;
    (globalThis as unknown as { Audio: unknown }).Audio = FakeAudio;
  });

  it("plays the Bắc voice at the unsaved speed, and stops on a second press", async () => {
    const panel = openPanel();
    fireEvent.change(panel.getByRole("slider", { name: "Tốc độ giọng (x)" }), { target: { value: "1.2" } });
    fireEvent.click(panel.getByRole("button", { name: "Nghe thử tốc độ giọng" }));
    expect(FakeAudio.urls).toEqual(["/api/voices/preview?voice_id=voice-1&speed=1.2"]);
    const stop = await panel.findByRole("button", { name: "Dừng nghe tốc độ giọng" });
    fireEvent.click(stop);
    await waitFor(() => expect(panel.getByRole("button", { name: "Nghe thử tốc độ giọng" })).toBeTruthy());
    expect(FakeAudio.paused).toBe(1);
  });

  it("normal speed asks for the plain preview", () => {
    const panel = openPanel();
    fireEvent.click(panel.getByRole("button", { name: "Nghe thử tốc độ giọng" }));
    expect(FakeAudio.urls).toEqual(["/api/voices/preview?voice_id=voice-1"]);
  });

  it("shows the value, and resets to 1x", () => {
    const panel = openPanel();
    const slider = panel.getByRole("slider", { name: "Tốc độ giọng (x)" }) as HTMLInputElement;
    expect(slider.type).toBe("range");
    expect(panel.getByText("1.00x")).toBeTruthy();
    expect(panel.queryByRole("button", { name: "Về 1x" })).toBeNull();
    fireEvent.change(slider, { target: { value: "0.85" } });
    expect(panel.getByText("0.85x")).toBeTruthy();
    expect(slider.getAttribute("aria-valuetext")).toBe("0.85x");
    fireEvent.click(panel.getByRole("button", { name: "Về 1x" }));
    expect(slider.value).toBe("1");
    expect(panel.getByText("1.00x")).toBeTruthy();
  });

  it("stops the clip when the speed changes", async () => {
    const panel = openPanel();
    fireEvent.click(panel.getByRole("button", { name: "Nghe thử tốc độ giọng" }));
    await panel.findByRole("button", { name: "Dừng nghe tốc độ giọng" });
    fireEvent.change(panel.getByRole("slider", { name: "Tốc độ giọng (x)" }), { target: { value: "0.9" } });
    expect(FakeAudio.paused).toBe(1);
  });
});
