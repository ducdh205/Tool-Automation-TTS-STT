import { useState } from "react";
import { applyTheme, loadTheme, nextTheme, type ThemeMode } from "../theme";

const LABEL: Record<ThemeMode, string> = { system: "◐ Theo hệ thống", light: "☀ Sáng", dark: "☾ Tối" };

export function ThemeSwitch() {
  const [mode, setMode] = useState<ThemeMode>(loadTheme);
  return (
    <button
      className="nav-item small-btn"
      title="Đổi giao diện sáng / tối"
      onClick={() => {
        const next = nextTheme(mode);
        applyTheme(next);
        setMode(next);
      }}
    >
      {LABEL[mode]}
    </button>
  );
}
