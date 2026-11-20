import { fireEvent, render, screen } from "@testing-library/react";
import { ExportZipDialog } from "./ExportZipDialog";
import { formatSize } from "../format";

test("formatSize uses binary units and a decimal comma", () => {
  expect(formatSize(1_200_000_000)).toBe("1,1 GB");
  expect(formatSize(350_000_000)).toBe("334 MB");
  expect(formatSize(300_000)).toBe("293 KB");
});

describe("ExportZipDialog", () => {
  it("defaults to failed-only; 'selected' is disabled without a selection", () => {
    const onExport = vi.fn().mockResolvedValue(undefined);
    render(<ExportZipDialog totalCount={4000} failedCount={12} selectedCount={0} onClose={() => {}} onExport={onExport} />);
    expect((screen.getByLabelText(/Chỉ case Sai \/ Lỗi thao tác \(12\)/) as HTMLInputElement).checked).toBe(true);
    expect((screen.getByLabelText(/Các case đang chọn/) as HTMLInputElement).disabled).toBe(true);
    expect(screen.getByText(/~1,1 GB/)).toBeTruthy();
    expect(screen.getByText("Ảnh chụp, kết quả và log luôn có cho mọi case.")).toBeTruthy();
    fireEvent.click(screen.getByText("Xuất zip"));
    expect(onExport).toHaveBeenCalledWith("failed");
  });

  it("exports the chosen option and shows progress while the download runs", async () => {
    let finish: () => void = () => {};
    const onExport = vi.fn(() => new Promise<void>((r) => { finish = r; }));
    render(<ExportZipDialog totalCount={10} failedCount={2} selectedCount={3} onClose={() => {}} onExport={onExport} />);
    fireEvent.click(screen.getByLabelText(/Các case đang chọn \(3\)/));
    fireEvent.click(screen.getByText("Xuất zip"));
    expect(onExport).toHaveBeenCalledWith("selected");
    expect(await screen.findByText("Đang tạo zip…")).toBeTruthy();
    finish();
  });
});
