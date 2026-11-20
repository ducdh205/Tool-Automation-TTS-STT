import { render, screen, fireEvent } from "@testing-library/react";
import { ItemTable } from "./ItemTable";
import type { Item } from "../api";

function makeItem(i: number, over: Partial<Item> = {}): Item {
  return {
    id: i + 1, audio_set_id: 1, sheet: "Sheet A", tc_id: `TC-${i}`, turn: "1", feature: "", priority: "",
    region: "BAC-HN", speaker: "👤 Người dùng", expected: "", source_row: 5 + i,
    text_raw: `câu ${i}`, text_tts: `câu ${i}`, skip_reason: null, enabled: 1, status: "Chờ",
    audio_path: null, attempts: 0, ref_text: null, wer: null, cer: null, ops: [], error: null,
    ...over,
  };
}

describe("ItemTable", () => {
  it("virtualizes 4000 rows", () => {
    const items = Array.from({ length: 4000 }, (_, i) => makeItem(i));
    const { container } = render(<ItemTable items={items} onPatch={() => {}} />);
    const rows = container.querySelectorAll("[data-row]");
    expect(rows.length).toBeGreaterThan(0);
    expect(rows.length).toBeLessThan(100);
  });

  it("highlights substituted words in the STT text", () => {
    const items = [makeItem(0, {
      status: "Audio không đạt", ref_text: "mua sửa", wer: 0.5, cer: 0.1,
      ops: [{ op: "equal", ref: "mua", hyp: "mua" }, { op: "sub", ref: "sữa", hyp: "sửa" }],
    })];
    const { container } = render(<ItemTable items={items} onPatch={() => {}} />);
    const sub = container.querySelector(".op-sub");
    expect(sub?.textContent).toBe("sửa");
    expect(screen.getByText("50%")).toBeTruthy();
  });

  it("shows the skip reason for skipped rows", () => {
    const items = [makeItem(0, { status: "Không áp dụng", text_tts: null, enabled: 0, skip_reason: "Dòng hệ thống" })];
    render(<ItemTable items={items} onPatch={() => {}} />);
    expect(screen.getByTitle("Dòng hệ thống")).toBeTruthy();
  });

  it("saves edited text on Enter", () => {
    const onPatch = vi.fn();
    render(<ItemTable items={[makeItem(0)]} onPatch={onPatch} />);
    fireEvent.doubleClick(screen.getByText("câu 0", { selector: ".cell-tts span" }));
    const input = screen.getByDisplayValue("câu 0");
    fireEvent.change(input, { target: { value: "câu mới" } });
    fireEvent.keyDown(input, { key: "Enter" });
    expect(onPatch).toHaveBeenCalledWith(1, { text_tts: "câu mới" });
  });

  it("toggles enabled via checkbox", () => {
    const onPatch = vi.fn();
    render(<ItemTable items={[makeItem(0)]} onPatch={onPatch} />);
    fireEvent.click(screen.getByRole("checkbox"));
    expect(onPatch).toHaveBeenCalledWith(1, { enabled: false });
  });
});

describe("audio playback (review #8)", () => {
  it("uses the audio file name as cache-buster", () => {
    const srcs: string[] = [];
    (globalThis as unknown as { Audio: unknown }).Audio = class {
      constructor(src: string) { srcs.push(src); }
      play() { return Promise.resolve(); }
    };
    const item = makeItem(0, { audio_path: String.raw`E:\data\audio\a1b2c3d4e5f60718.wav`, attempts: 1, status: "Đạt" });
    render(<ItemTable items={[item]} onPatch={() => {}} />);
    fireEvent.click(screen.getByTitle("Nghe audio"));
    expect(srcs[0]).toBe("/api/items/1/audio?v=a1b2c3d4e5f60718.wav");
  });
});
