import { formatPct, renderOps } from "./format";

describe("formatPct", () => {
  it("uses Vietnamese decimal comma and one decimal", () => {
    expect(formatPct(0.2222)).toBe("22,2%");
    expect(formatPct(0)).toBe("0%");
    expect(formatPct(1)).toBe("100%");
  });
  it("returns dash for missing values", () => {
    expect(formatPct(null)).toBe("—");
    expect(formatPct(undefined)).toBe("—");
  });
});

describe("renderOps", () => {
  it("maps ops to hypothesis-side segments", () => {
    const segs = renderOps([
      { op: "equal", ref: "mua", hyp: "mua" },
      { op: "sub", ref: "sữa", hyp: "sửa" },
      { op: "del", ref: "tươi", hyp: null },
      { op: "ins", ref: null, hyp: "nhé" },
    ]);
    expect(segs).toEqual([
      { text: "mua", kind: "equal" },
      { text: "sửa", kind: "sub", title: "đúng: sữa" },
      { text: "tươi", kind: "del", title: "thiếu từ" },
      { text: "nhé", kind: "ins", title: "thừa từ" },
    ]);
  });
});
