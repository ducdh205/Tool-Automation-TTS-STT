/** Small stroke icons (24×24 grid) so the UI uses one visual language instead of mixed emoji / unicode glyphs. */
const PATHS = {
  upload: "M12 15V3m-5 5 5-5 5 5M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4",
  download: "M12 3v12m-5-5 5 5 5-5M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4",
  play: "M7 4.5v15l12-7.5z",
  check: "M4.5 12.5 9.5 17.5 19.5 6.5",
  refresh: "M20 11a8 8 0 0 0-14.6-4.5L4 8m0-4v4h4M4 13a8 8 0 0 0 14.6 4.5L20 16m0 4v-4h-4",
  stop: "M6 6h12v12H6z",
  settings: "M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6zM19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z",
  chevron: "m6 9 6 6 6-6",
  power: "M12 3v9M6.3 6.3a8 8 0 1 0 11.4 0",
  x: "M6 6l12 12M18 6 6 18",
  info: "M12 22a10 10 0 1 0 0-20 10 10 0 0 0 0 20zM12 16v-4m0-4h.01",
  search: "M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16zm10 2-4.3-4.3",
  sun: "M12 17a5 5 0 1 0 0-10 5 5 0 0 0 0 10zM12 1v2m0 18v2M4.2 4.2l1.4 1.4m12.8 12.8 1.4 1.4M1 12h2m18 0h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4",
  moon: "M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z",
  monitor: "M4 4h16v12H4zM8 20h8m-4-4v4",
  back: "M15 5 8 12l7 7",
  home: "M12 4a8 8 0 1 0 0 16 8 8 0 0 0 0-16z",
  recents: "M6 6h12v12H6z",
  volDown: "M11 5 6 9H2v6h4l5 4zM15.5 8.5a5 5 0 0 1 0 7",
  volUp: "M11 5 6 9H2v6h4l5 4zM15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14",
  pencil: "M17 3a2.8 2.8 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5z",
  pin: "M12 17v5M9 10.8V5h6v5.8l3 3.2v2H6v-2z",
  backspace: "M21 4H8l-7 8 7 8h13a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zM18 9l-6 6m0-6 6 6",
} as const;

export type IconName = keyof typeof PATHS;
const FILLED: ReadonlySet<IconName> = new Set(["play", "stop"]);

export function Icon({ name, size = 15 }: { name: IconName; size?: number }) {
  const filled = FILLED.has(name);
  return (
    <svg className="icon" width={size} height={size} viewBox="0 0 24 24" aria-hidden="true" focusable="false"
      fill={filled ? "currentColor" : "none"} stroke="currentColor" strokeWidth={filled ? 0 : 2}
      strokeLinecap="round" strokeLinejoin="round">
      <path d={PATHS[name]} />
    </svg>
  );
}
