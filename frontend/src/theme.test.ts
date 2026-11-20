import { applyTheme, loadTheme, nextTheme, THEME_KEY, type ThemeMode } from "./theme";

afterEach(() => {
  vi.restoreAllMocks();
  localStorage.clear();
  document.documentElement.removeAttribute("data-theme");
});

test("dark sets the attribute and persists, system removes it", () => {
  applyTheme("dark");
  expect(document.documentElement.dataset.theme).toBe("dark");
  expect(localStorage.getItem(THEME_KEY)).toBe("dark");
  expect(loadTheme()).toBe("dark");
  applyTheme("system");
  expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  expect(loadTheme()).toBe("system");
});

test("cycles system -> light -> dark -> system", () => {
  expect((["system", "light", "dark"] as ThemeMode[]).map(nextTheme)).toEqual(["light", "dark", "system"]);
});

test("unknown stored value falls back to system", () => {
  localStorage.setItem(THEME_KEY, "purple");
  expect(loadTheme()).toBe("system");
});

test("storage that throws does not break the page", () => {
  vi.spyOn(localStorage, "getItem").mockImplementation(() => { throw new Error("blocked"); });
  vi.spyOn(localStorage, "setItem").mockImplementation(() => { throw new Error("blocked"); });
  expect(loadTheme()).toBe("system");
  expect(() => applyTheme("light")).not.toThrow();
  expect(document.documentElement.dataset.theme).toBe("light");
});
