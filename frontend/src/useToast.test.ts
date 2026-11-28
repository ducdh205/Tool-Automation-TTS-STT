import { act, renderHook } from "@testing-library/react";
import { TOAST_MS, useToast } from "./useToast";

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

it("hides the toast after its time", () => {
  const { result } = renderHook(() => useToast());
  act(() => result.current.notify("a"));
  expect(result.current.toast).toEqual({ text: "a", kind: "info" });
  act(() => vi.advanceTimersByTime(TOAST_MS));
  expect(result.current.toast).toBeNull();
});

it("a newer toast keeps its full time (the older timer does not hide it)", () => {
  const { result } = renderHook(() => useToast());
  act(() => result.current.notify("a"));
  act(() => vi.advanceTimersByTime(TOAST_MS - 1000));
  act(() => result.current.notify("b", "error"));
  act(() => vi.advanceTimersByTime(1500));
  expect(result.current.toast).toEqual({ text: "b", kind: "error" });
  act(() => vi.advanceTimersByTime(TOAST_MS));
  expect(result.current.toast).toBeNull();
});
