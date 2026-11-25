import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { ImportDialog } from "./ImportDialog";
import { api, type SheetPreview } from "../api";

vi.mock("../api", async (orig) => {
  const real = await orig<typeof import("../api")>();
  return { ...real, api: { inspect: vi.fn(), preview: vi.fn(), createSet: vi.fn() } };
});

const mocked = api as unknown as { inspect: ReturnType<typeof vi.fn>; preview: ReturnType<typeof vi.fn>; createSet: ReturnType<typeof vi.fn> };

const PV: SheetPreview = {
  columns: ["TC_ID", "Câu nói (utterance)", "Vùng miền"],
  rows: [["TC-1", "Bật đèn", "BAC-HN"]],
  row_count: 37,
  suggestions: { id_col: "TC_ID", text_col: "Câu nói (utterance)", region_col: "Vùng miền" },
};

async function open(preview: SheetPreview = PV, sheets = ["S1", "S2"]) {
  mocked.inspect.mockResolvedValue({ file_id: "f", sheets });
  mocked.preview.mockResolvedValue(preview);
  const onClose = vi.fn();
  const onCreated = vi.fn().mockResolvedValue(undefined);
  const { container } = render(<ImportDialog onClose={onClose} onCreated={onCreated} />);
  const input = container.querySelector('input[type="file"]') as HTMLInputElement;
  fireEvent.change(input, { target: { files: [new File(["x"], "mini.xlsx")] } });
  await screen.findByText("37");
  return { onClose, onCreated };
}

const createBtn = () => screen.getByText("Tạo bộ audio") as HTMLButtonElement;

beforeEach(() => { vi.clearAllMocks(); });

describe("ImportDialog", () => {
  it("prefills mapping from suggestions and creates with the mapping", async () => {
    mocked.createSet.mockResolvedValue({ id: 7 });
    const { onClose, onCreated } = await open();
    fireEvent.click(createBtn());
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(7));
    expect(mocked.createSet).toHaveBeenCalledWith({
      file_id: "f", sheets: ["S1"], name: "mini",
      mapping: {
        header_row: 1, text_col: "Câu nói (utterance)", id_col: "TC_ID", region_col: "Vùng miền",
        region_value: null, expected_col: null, turn_col: null,
      },
    });
    await waitFor(() => expect(onClose).toHaveBeenCalled());
  });

  it("create is disabled until a text column is mapped", async () => {
    await open({ ...PV, suggestions: {} });
    expect(createBtn().disabled).toBe(true);
    fireEvent.change(screen.getByLabelText("Câu lệnh *"), { target: { value: "Câu nói (utterance)" } });
    expect(createBtn().disabled).toBe(false);
  });

  it("changing header row re-fetches the preview", async () => {
    await open();
    fireEvent.change(screen.getByLabelText("Dòng tiêu đề"), { target: { value: "4" } });
    await waitFor(() =>
      expect(mocked.preview).toHaveBeenLastCalledWith({ file_id: "f", sheet: "S1", header_row: 4 }));
  });

  it("sends a fixed region value instead of a region column", async () => {
    mocked.createSet.mockResolvedValue({ id: 1 });
    await open();
    fireEvent.change(screen.getByLabelText("Vùng miền"), { target: { value: "__fixed__" } });
    fireEvent.change(screen.getByLabelText("Giá trị vùng miền cố định"), { target: { value: "BAC-HN" } });
    fireEvent.click(createBtn());
    await waitFor(() => expect(mocked.createSet).toHaveBeenCalled());
    const m = mocked.createSet.mock.calls[0][0].mapping;
    expect(m.region_col).toBeNull();
    expect(m.region_value).toBe("BAC-HN");
  });

  it("keep-open unticks imported sheets and stays open", async () => {
    mocked.createSet.mockResolvedValue({ id: 3 });
    const { onClose, onCreated } = await open();
    fireEvent.click(screen.getByLabelText(/Giữ cửa sổ này/));
    fireEvent.click(createBtn());
    await waitFor(() => expect(onCreated).toHaveBeenCalledWith(3));
    await waitFor(() => expect((screen.getByLabelText("S1") as HTMLInputElement).checked).toBe(false));
    expect(onClose).not.toHaveBeenCalled();
    expect(createBtn().disabled).toBe(true);
  });

  it("ignores stale preview responses", async () => {
    let resolveFirst: (v: SheetPreview) => void = () => {};
    mocked.inspect.mockResolvedValue({ file_id: "f", sheets: ["S1", "S2"] });
    mocked.preview
      .mockImplementationOnce(() => new Promise<SheetPreview>((r) => { resolveFirst = r; }))
      .mockResolvedValue({ ...PV, row_count: 5 });
    const { container } = render(<ImportDialog onClose={() => {}} onCreated={async () => {}} />);
    fireEvent.change(container.querySelector('input[type="file"]') as HTMLInputElement,
      { target: { files: [new File(["x"], "a.xlsx")] } });
    await screen.findByLabelText("Sheet");
    fireEvent.change(screen.getByLabelText("Sheet"), { target: { value: "S2" } });
    await screen.findByText("5");
    await act(async () => { resolveFirst({ ...PV, row_count: 99 }); });
    expect(screen.queryByText("99")).toBeNull();
    expect(screen.getByText("5")).toBeTruthy();
  });
  it("keeps the fixed region value when the preview reloads", async () => {
    await open();
    fireEvent.change(screen.getByLabelText("Vùng miền"), { target: { value: "__fixed__" } });
    fireEvent.change(screen.getByLabelText("Giá trị vùng miền cố định"), { target: { value: "BAC-HN" } });
    fireEvent.change(screen.getByLabelText("Dòng tiêu đề"), { target: { value: "2" } });
    await waitFor(() => expect(mocked.preview).toHaveBeenLastCalledWith({ file_id: "f", sheet: "S1", header_row: 2 }));
    await waitFor(() => expect(createBtn().disabled).toBe(false));
    expect((screen.getByLabelText("Vùng miền") as HTMLSelectElement).value).toBe("__fixed__");
    expect(screen.getByLabelText("Giá trị vùng miền cố định")).toBeTruthy();
  });

  it("sends sheet names with trailing spaces unchanged", async () => {
    await open(PV, ["Data ", "B"]);
    fireEvent.change(screen.getByLabelText("Sheet"), { target: { value: "B" } });
    fireEvent.change(screen.getByLabelText("Sheet"), { target: { value: "Data " } });
    await waitFor(() => expect(mocked.preview).toHaveBeenLastCalledWith({ file_id: "f", sheet: "Data ", header_row: 1 }));
  });
});
