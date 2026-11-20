import { useState } from "react";
import { applyTheme, loadTheme, nextTheme, type ThemeMode } from "../theme";
import { Icon, type IconName } from "./Icon";

const ICON: Record<ThemeMode, IconName> = { system: "monitor", light: "sun", dark: "moon" };
const LABEL: Record<ThemeMode, string> = { system: "Theo hệ thống", light: "Sáng", dark: "Tối" };

export function ThemeSwitch() {
  const [mode, setMode] = useState<ThemeMode>(loadTheme);
  return (
    <button
      className="icon-btn theme-btn"
      title="Đổi giao diện sáng / tối"
      aria-label={`Giao diện: ${LABEL[mode]}`}
      onClick={() => {
        const next = nextTheme(mode);
        applyTheme(next);
        setMode(next);
      }}
    >
      <Icon name={ICON[mode]} />
    </button>
  );
}
