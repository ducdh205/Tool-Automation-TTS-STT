import { fireEvent, render, screen } from "@testing-library/react";
import { Sidebar } from "./Sidebar";

describe("Sidebar steps", () => {
  const base = { onSection: () => {}, health: null, sets: [], currentSetId: null, onSelectSet: () => {} };

  it("has two steps; step 2 is disabled until a row passed", () => {
    render(<Sidebar {...base} section="step1" step2Ready={false} />);
    expect(screen.getByText("Bước 1 — Audio")).toBeTruthy();
    const step2 = screen.getByText("Bước 2 — Test app").closest("button")!;
    expect(step2.disabled).toBe(true);
    expect(step2.title).toBe("Cần sinh audio ở Bước 1 trước");
    expect(screen.queryByText("Báo cáo")).toBeNull();
  });

  it("switches step and offers the theme switch", () => {
    const onSection = vi.fn();
    render(<Sidebar {...base} onSection={onSection} section="step1" step2Ready />);
    fireEvent.click(screen.getByText("Bước 2 — Test app"));
    expect(onSection).toHaveBeenCalledWith("step2");
    expect(screen.getByTitle("Đổi giao diện sáng / tối")).toBeTruthy();
  });
});

describe("Sidebar audio sets", () => {
  const set = { id: 3, name: "E2E Climate Sync", source_file: "f.xlsx", sheets: ["S1"], voice: null,
    created_at: "", summary: { "Đạt": 1, "Chờ": 260 } };
  const base = { section: "step1" as const, step2Ready: true, onSection: () => {}, health: null,
    sets: [set], currentSetId: 3, onSelectSet: () => {} };

  it("deletes a set after the user confirms", () => {
    const onDeleteSet = vi.fn();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<Sidebar {...base} onDeleteSet={onDeleteSet} />);
    fireEvent.click(screen.getByRole("button", { name: "Xóa bộ E2E Climate Sync" }));
    expect(confirm.mock.calls[0][0]).toContain("E2E Climate Sync");
    expect(confirm.mock.calls[0][0]).toContain("261 câu");
    expect(onDeleteSet).toHaveBeenCalledWith(3);
  });

  it("keeps the set when the user cancels", () => {
    const onDeleteSet = vi.fn();
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<Sidebar {...base} onDeleteSet={onDeleteSet} />);
    fireEvent.click(screen.getByRole("button", { name: "Xóa bộ E2E Climate Sync" }));
    expect(onDeleteSet).not.toHaveBeenCalled();
  });

  it("locks deletion while a job runs", () => {
    render(<Sidebar {...base} onDeleteSet={() => {}} deleteLocked="Đang chạy job" />);
    const del = screen.getByRole("button", { name: "Xóa bộ E2E Climate Sync" }) as HTMLButtonElement;
    expect(del.disabled).toBe(true);
    expect(del.title).toBe("Đang chạy job");
  });
});

describe("Sidebar clear all data", () => {
  const set = { id: 3, name: "Bộ A", source_file: "f.xlsx", sheets: ["S1"], voice: null,
    created_at: "", summary: { "Chờ": 2 } };
  const base = { section: "step1" as const, step2Ready: true, onSection: () => {}, health: null,
    sets: [set, { ...set, id: 4, name: "Bộ B" }], currentSetId: 3, onSelectSet: () => {} };

  it("clears everything after the user confirms", () => {
    const onClearAll = vi.fn();
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<Sidebar {...base} onClearAll={onClearAll} />);
    fireEvent.click(screen.getByRole("button", { name: "Xóa toàn bộ dữ liệu" }));
    expect(confirm.mock.calls[0][0]).toContain("2 bộ audio");
    expect(confirm.mock.calls[0][0]).toContain("Cài đặt và hồ sơ app được giữ lại");
    expect(onClearAll).toHaveBeenCalledTimes(1);
  });

  it("does nothing when the user cancels", () => {
    const onClearAll = vi.fn();
    vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<Sidebar {...base} onClearAll={onClearAll} />);
    fireEvent.click(screen.getByRole("button", { name: "Xóa toàn bộ dữ liệu" }));
    expect(onClearAll).not.toHaveBeenCalled();
  });

  it("is locked while a job runs and hidden without a handler", () => {
    const { unmount } = render(<Sidebar {...base} onClearAll={() => {}} deleteLocked="Đang chạy job" />);
    const btn = screen.getByRole("button", { name: "Xóa toàn bộ dữ liệu" }) as HTMLButtonElement;
    expect(btn.disabled).toBe(true);
    expect(btn.title).toBe("Đang chạy job");
    unmount();
    render(<Sidebar {...base} />);
    expect(screen.queryByRole("button", { name: "Xóa toàn bộ dữ liệu" })).toBeNull();
  });
});
