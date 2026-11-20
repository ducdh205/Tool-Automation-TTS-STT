import { fireEvent, render, screen } from "@testing-library/react";
import { STATUSES } from "../api";
import { RunBar } from "./RunBar";

function props(over: Partial<Parameters<typeof RunBar>[0]> = {}) {
  return {
    mode: "step1" as const, hasSet: true, job: null, statuses: STATUSES, summary: { "Chờ": 3 }, total: 3,
    filter: "all", search: "", onFilter: vi.fn(), onSearch: () => {}, onImport: () => {}, onGenerate: vi.fn(),
    onVerify: vi.fn(), onRegenerate: vi.fn(), onStop: vi.fn(), onReport: vi.fn(), selectedCount: 0,
    onClearSelection: vi.fn(), ...over,
  };
}

describe("RunBar", () => {
  it("labels say 'all' without a selection", () => {
    render(<RunBar {...props()} />);
    expect(screen.getByText("Sinh audio (tất cả)")).toBeTruthy();
    expect(screen.getByText("Verify (tất cả)")).toBeTruthy();
    expect(screen.getByText("Sinh lại (tất cả không đạt)")).toBeTruthy();
    expect(screen.queryByText(/Đã chọn/)).toBeNull();
  });

  it("labels and the selection chip follow the selection", () => {
    const p = props({ selectedCount: 12 });
    render(<RunBar {...p} />);
    fireEvent.click(screen.getByText("Verify (12)"));
    expect(p.onVerify).toHaveBeenCalled();
    fireEvent.click(screen.getByText("Sinh audio (12)"));
    expect(p.onGenerate).toHaveBeenCalled();
    fireEvent.click(screen.getByText("Sinh lại (12)"));
    expect(p.onRegenerate).toHaveBeenCalled();
    expect(screen.getByText(/Đã chọn 12/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Bỏ chọn" }));
    expect(p.onClearSelection).toHaveBeenCalled();
  });

  it("shows progress and Stop only while a job runs", () => {
    const { rerender } = render(<RunBar {...props()} />);
    expect(screen.queryByRole("status")).toBeNull();
    expect(screen.queryByText("Dừng")).toBeNull();
    const p = props({ job: { id: "j", name: "x", done: 1, total: 3 } });
    rerender(<RunBar {...p} />);
    expect((screen.getByText("Sinh audio (tất cả)") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByRole("status").textContent).toContain("1/3");
    fireEvent.click(screen.getByText("Dừng"));
    expect(p.onStop).toHaveBeenCalled();
  });

  it("hides empty status chips but keeps the active one", () => {
    const { rerender } = render(<RunBar {...props({ summary: { "Chờ": 2, "Đạt": 1 } })} />);
    expect(screen.getByRole("button", { name: /^Đạt/ })).toBeTruthy();
    expect(screen.queryByRole("button", { name: /^Lỗi/ })).toBeNull();
    rerender(<RunBar {...props({ summary: { "Chờ": 2 }, filter: "Lỗi" })} />);
    expect(screen.getByRole("button", { name: /^Lỗi/ }).className).toContain("active");
  });

  it("exports through the menu", () => {
    const p = props();
    render(<RunBar {...p} />);
    fireEvent.click(screen.getByRole("button", { name: "Xuất" }));
    fireEvent.click(screen.getByRole("button", { name: "CSV" }));
    expect(p.onReport).toHaveBeenCalledWith("csv");
    expect(screen.queryByRole("button", { name: "CSV" })).toBeNull();
  });

  it("step 2 shows its own actions and app verdict chips, no Block 1 buttons", () => {
    render(<RunBar {...props({
      mode: "step2", selectedCount: 2, statuses: ["Chờ", "Đúng", "Sai", "Lỗi thao tác"], summary: { "Đúng": 4, "Sai": 1 },
      appActions: <button>Chạy trên app (2)</button>,
    })} />);
    expect(screen.queryByText(/Sinh audio/)).toBeNull();
    expect(screen.queryByText("Nạp file")).toBeNull();
    expect(screen.getByText("Chạy trên app (2)")).toBeTruthy();
    expect(screen.getByRole("button", { name: /^Sai/ })).toBeTruthy();
    expect(screen.getByPlaceholderText("Tìm câu, TC_ID…")).toBeTruthy();
    expect(screen.getByText(/Đã chọn 2/)).toBeTruthy();
  });
});
