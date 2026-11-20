import { classifyEvent } from "./events";
import type { ProgressEvent } from "./api";

const ev = (over: Partial<ProgressEvent>): ProgressEvent =>
  ({ job_id: "j", kind: "item", done: 1, total: 2, item: null, message: null, ...over });

describe("classifyEvent", () => {
  it("separates block1 items from app results", () => {
    expect(classifyEvent(ev({ item: { id: 1, audio_set_id: 3 } as never }))).toBe("block1-item");
    expect(classifyEvent(ev({ item: { id: 1, app_run_id: 4, item_id: 9 } as never }))).toBe("app-item");
  });
  it("log and progress are not terminal", () => {
    expect(classifyEvent(ev({ kind: "log", message: "Bấm mic" }))).toBe("log");
    expect(classifyEvent(ev({ kind: "progress" }))).toBe("progress");
  });
  it("done / error / cancelled are terminal", () => {
    for (const k of ["done", "error", "cancelled"] as const) expect(classifyEvent(ev({ kind: k }))).toBe("terminal");
  });
});
