import { render, screen, fireEvent } from "@testing-library/react";
import { ItemTable } from "./ItemTable";
import type { Item } from "../api";

function makeItem(i: number, over: Partial<Item> = {}): Item {
  return {
    id: i + 1, audio_set_id: 1, sheet: "Sheet A", tc_id: `TC-${i}`, turn: "1", feature: "", priority: "",
    region: "BAC-HN", speaker: "👤 Người dùng", expected: "", source_row: 5 + i,
    text_raw: `câu ${i}`, text_tts: `câu ${i}`, skip_reason: null, enabled: 1, status: "Chờ",
    audio_path: null, attempts: 0, ref_text: null, wer: null, cer: null, ops: [], error: null, verify: "Chưa",
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

  it("toggles enabled via the power button", () => {
    const onPatch = vi.fn();
    render(<ItemTable items={[makeItem(0)]} onPatch={onPatch} />);
    fireEvent.click(screen.getByTitle("Bật/tắt câu này"));
    expect(onPatch).toHaveBeenCalledWith(1, { enabled: false });
  });
});

describe("selection", () => {
  const items = [makeItem(0), makeItem(1), makeItem(2, { enabled: 0 })];
  const selectable = (it: Item) => !!it.enabled;

  it("row checkbox reports the row index and the shift key", () => {
    const onRowSelect = vi.fn();
    render(<ItemTable items={items} onPatch={() => {}} selected={new Set()} isSelectable={selectable}
      onRowSelect={onRowSelect} onToggleAll={() => {}} />);
    fireEvent.click(screen.getByLabelText("Chọn TC-1"), { shiftKey: true });
    expect(onRowSelect).toHaveBeenCalledWith(1, true);
    expect((screen.getByLabelText("Chọn TC-2") as HTMLInputElement).disabled).toBe(true);
  });

  it("header checkbox is checked / indeterminate from the selectable visible rows", () => {
    const onToggleAll = vi.fn();
    const { rerender } = render(<ItemTable items={items} onPatch={() => {}} selected={new Set([1])}
      isSelectable={selectable} onRowSelect={() => {}} onToggleAll={onToggleAll} />);
    expect((screen.getByLabelText("Chọn TC-0") as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText("Chọn TC-1") as HTMLInputElement).checked).toBe(false);
    const all = screen.getByLabelText("Chọn tất cả") as HTMLInputElement;
    expect(all.checked).toBe(false);
    expect(all.indeterminate).toBe(true);
    fireEvent.click(all);
    expect(onToggleAll).toHaveBeenCalled();
    rerender(<ItemTable items={items} onPatch={() => {}} selected={new Set([1, 2])}
      isSelectable={selectable} onRowSelect={() => {}} onToggleAll={onToggleAll} />);
    expect((screen.getByLabelText("Chọn tất cả") as HTMLInputElement).checked).toBe(true);
  });

  it("regenerate button only for rows with audio", () => {
    const onRegenerate = vi.fn();
    render(<ItemTable items={[makeItem(0, { audio_path: "a.wav", status: "Audio không đạt" }), makeItem(1)]}
      onPatch={() => {}} onRegenerate={onRegenerate} />);
    const buttons = screen.getAllByTitle("Sinh lại audio");
    expect(buttons).toHaveLength(1);
    fireEvent.click(buttons[0]);
    expect(onRegenerate).toHaveBeenCalledWith(1);
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

describe("app mode (block 2)", () => {
  it("shows the app's text, WER and verdict instead of the reference STT", () => {
    const item = makeItem(0, { status: "Đạt", ref_text: "mua sữa", wer: 0, cer: 0 });
    const app = new Map([[1, {
      id: 50, app_run_id: 7, item_id: 1, status: "Sai" as const, app_text: "mua sửa", wer: 0.5, cer: 0.1,
      ops: [{ op: "equal" as const, ref: "mua", hyp: "mua" }, { op: "sub" as const, ref: "sữa", hyp: "sửa" }],
      error: null, log: null,
    }]]);
    const { container } = render(<ItemTable items={[item]} onPatch={() => {}} app={app} />);
    expect(screen.getByText("Text app")).toBeTruthy();
    expect(container.querySelector(".op-sub")?.textContent).toBe("sửa");
    expect(screen.getByText("50%")).toBeTruthy();
    expect(screen.getByText("Sai")).toBeTruthy();
  });
  it("counts the attempts of a case run again and lists them in the tooltip", () => {
    const item = makeItem(0, { status: "Đạt" });
    const app = new Map([[1, {
      id: 50, app_run_id: 7, item_id: 1, status: "Đúng" as const, app_text: "mua sữa", wer: 0, cer: 0,
      ops: [], error: null, log: null,
      history: [{ status: "Sai" as const, app_text: "mua sửa", wer: 0.5, cer: 0.1, error: null, updated_at: null }],
    }]]);
    render(<ItemTable items={[item]} onPatch={() => {}} app={app} />);
    const badge = screen.getByText("Đúng ·2x");
    expect(badge.getAttribute("title")).toBe('Lần 2 (hiện tại): Đúng\nLần 1: Sai — "mua sửa"');
  });
});

describe("app mode layout", () => {
  it("has no actions column, so the status column keeps its width", () => {
    const { container } = render(<ItemTable items={[makeItem(0, { status: "Đạt" })]} onPatch={() => {}} app={new Map()} />);
    expect(container.querySelector(".table")?.classList.contains("app")).toBe(true);
    expect(container.querySelector(".row-actions")).toBeNull();
    expect(container.querySelector(".row.head")?.children.length).toBe(7); // + Verify, no actions
  });
});

describe("compact columns", () => {
  it("folds the source text into a marker and shows the sheet column only when asked", () => {
    const item = makeItem(0, { text_raw: "Bật quạt 2", text_tts: "bật quạt hai" });
    const { container, rerender } = render(<ItemTable items={[item]} onPatch={() => {}} />);
    expect(screen.getByLabelText("Câu gốc: Bật quạt 2")).toBeTruthy();
    expect(screen.queryByText("Sheet")).toBeNull();
    rerender(<ItemTable items={[item]} onPatch={() => {}} showSheet />);
    expect(screen.getByText("Sheet")).toBeTruthy();
    expect(container.querySelector(".row.head")?.children.length).toBe(8);
  });

  it("shows WER with the CER beside it", () => {
    const item = makeItem(0, { status: "Audio không đạt", ref_text: "bật quát", wer: 0.5, cer: 0.125 });
    render(<ItemTable items={[item]} onPatch={() => {}} />);
    expect(screen.getByText("50%")).toBeTruthy();
    expect(screen.getByText("12,5%")).toBeTruthy();
  });

  it("keeps the sheet text visible when a row has no reading text", () => {
    render(<ItemTable items={[makeItem(0, { text_raw: "[hệ thống]", text_tts: null, enabled: 0 })]} onPatch={() => {}} />);
    expect(screen.getByText("[hệ thống]")).toBeTruthy();
  });
});

describe("app mode is read-only (review2 #6)", () => {
  it("does not open the editor on double click", () => {
    const item = makeItem(0, { status: "Đạt" });
    render(<ItemTable items={[item]} onPatch={() => {}} app={new Map()} />);
    fireEvent.doubleClick(screen.getByText("câu 0", { selector: ".cell-tts span" }));
    expect(screen.queryByDisplayValue("câu 0")).toBeNull();
  });

  it("shows the verify result of each row in step 2", () => {
    const rows = [
      makeItem(0, { audio_path: "a.wav", status: "Đạt", verify: "Đạt" }),
      makeItem(1, { audio_path: "b.wav", status: "Audio không đạt", verify: "Không đạt" }),
      makeItem(2, { audio_path: "c.wav", status: "Đã sinh audio", verify: "Chưa" }),
    ];
    render(<ItemTable items={rows} onPatch={() => {}} app={new Map()} />);
    expect(screen.getByText("Verify")).toBeTruthy();
    expect(screen.getByTitle("Verify audio: Đạt").className).toContain("st-pass");
    expect(screen.getByTitle("Verify audio: Không đạt").className).toContain("st-fail");
    expect(screen.getByTitle("Verify audio: Chưa").className).toContain("st-pending");
  });
});
