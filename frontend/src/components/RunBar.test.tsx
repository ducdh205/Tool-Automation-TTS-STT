import { fireEvent, render, screen } from "@testing-library/react";
import { RunBar } from "./RunBar";

function props(over: Partial<Parameters<typeof RunBar>[0]> = {}) {
  return {
    mode: "step1" as const, hasSet: true, job: null, summary: { "Chờ": 3 }, filter: "all" as const, search: "",
    onFilter: () => {}, onSearch: () => {}, onImport: () => {}, onGenerate: vi.fn(), onVerify: vi.fn(),
    onRegenerate: vi.fn(), onStop: () => {}, onReport: () => {}, rejectWarn: 0.1, selectedCount: 0,
    onClearSelection: vi.fn(), ...over,
  };
}

describe("RunBar", () => {
  it("labels say 'all' without a selection", () => {
    render(<RunBar {...props()} />);
    expect(screen.getByText("Sinh audio (tất cả)")).toBeTruthy();
    expect(screen.getByText("Verify (tất cả)")).toBeTruthy();
    expect(screen.getByText("Sinh lại (tất cả không đạt)")).toBeTruthy();
    expect(screen.queryByText(/Đang chọn/)).toBeNull();
  });

  it("labels and the selection line follow the selection", () => {
    const p = props({ selectedCount: 12 });
    render(<RunBar {...p} />);
    fireEvent.click(screen.getByText("Verify (12)"));
    expect(p.onVerify).toHaveBeenCalled();
    fireEvent.click(screen.getByText("Sinh audio (12)"));
    expect(p.onGenerate).toHaveBeenCalled();
    fireEvent.click(screen.getByText("Sinh lại (12)"));
    expect(p.onRegenerate).toHaveBeenCalled();
    expect(screen.getByText(/Đang chọn 12 case/)).toBeTruthy();
    fireEvent.click(screen.getByText("Bỏ chọn"));
    expect(p.onClearSelection).toHaveBeenCalled();
  });

  it("disables actions while a job runs", () => {
    render(<RunBar {...props({ job: { id: "j", name: "x", done: 1, total: 3 } })} />);
    expect((screen.getByText("Sinh audio (tất cả)") as HTMLButtonElement).disabled).toBe(true);
    expect((screen.getByText("Dừng") as HTMLButtonElement).disabled).toBe(false);
  });

  it("step 2 shows filters and progress but no Block 1 buttons", () => {
    render(<RunBar {...props({ mode: "step2", selectedCount: 2 })} />);
    expect(screen.queryByText(/Sinh audio/)).toBeNull();
    expect(screen.queryByText("Nạp file")).toBeNull();
    expect(screen.getByPlaceholderText("Tìm câu, TC_ID…")).toBeTruthy();
    expect(screen.getByText(/Đang chọn 2 case/)).toBeTruthy();
  });
});
