import { clickRow, emptySelection, prune, toggleAllVisible } from "./selection";

const ids = [10, 11, 12, 13];
const sorted = (s: { ids: ReadonlySet<number> }) => [...s.ids].sort((a, b) => a - b);

test("click toggles one row and sets the anchor", () => {
  const s = clickRow(emptySelection, ids, 1, false);
  expect(sorted(s)).toEqual([11]);
  expect(s.anchor).toBe(1);
  expect(sorted(clickRow(s, ids, 1, false))).toEqual([]);
});

test("shift-click adds the range from the anchor, in either direction", () => {
  let s = clickRow(emptySelection, ids, 1, false);
  s = clickRow(s, ids, 3, true);
  expect(sorted(s)).toEqual([11, 12, 13]);
  expect(s.anchor).toBe(1);
  expect(sorted(clickRow(s, ids, 2, false))).toEqual([11, 13]);
  const back = clickRow(clickRow(emptySelection, ids, 3, false), ids, 0, true);
  expect(sorted(back)).toEqual([10, 11, 12, 13]);
});

test("shift-click without an anchor behaves like a click", () => {
  expect(sorted(clickRow(emptySelection, ids, 2, true))).toEqual([12]);
});

test("toggle all visible adds them, then removes only them", () => {
  const outside = { ids: new Set([99]), anchor: null };
  const s = toggleAllVisible(outside, [1, 2]);
  expect(sorted(s)).toEqual([1, 2, 99]);
  expect(sorted(toggleAllVisible(s, [1, 2]))).toEqual([99]);
});

test("prune keeps only allowed ids", () => {
  const s = { ids: new Set([1, 2, 3]), anchor: 2 };
  expect(sorted(prune(s, new Set([2, 3, 4])))).toEqual([2, 3]);
});
