// jsdom has no ResizeObserver (used by the virtualized table).
class RO {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver: typeof RO }).ResizeObserver = RO;

// Recent Node versions expose an experimental global `localStorage` that is undefined without
// --localstorage-file and shadows jsdom's: give tests a working in-memory one.
if (typeof globalThis.localStorage === "undefined" || globalThis.localStorage === null) {
  const data = new Map<string, string>();
  const mem = {
    get length() { return data.size; },
    clear: () => data.clear(),
    getItem: (k: string) => (data.has(k) ? data.get(k)! : null),
    key: (i: number) => [...data.keys()][i] ?? null,
    removeItem: (k: string) => { data.delete(k); },
    setItem: (k: string, v: string) => { data.set(k, String(v)); },
  };
  Object.defineProperty(globalThis, "localStorage", { value: mem, configurable: true });
}
