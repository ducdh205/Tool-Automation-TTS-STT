import { useEffect, useId, useRef, useState, type ReactNode } from "react";

interface Props {
  /** Trigger button content. */
  label: ReactNode;
  /** Accessible name for the panel (and for the trigger when `label` is only an icon). */
  panelLabel: string;
  iconOnly?: boolean;
  buttonClassName?: string;
  className?: string;
  disabled?: boolean;
  /** Panel edge that lines up with the trigger: "right" for triggers near the right edge of the screen. */
  align?: "left" | "right";
  /** Children get `open` so they can pause work (e.g. audio preview) while hidden, and `close` for menu items. */
  children: (open: boolean, close: () => void) => ReactNode;
}

/** A button that toggles a floating panel; closes on outside click, Escape, or when disabled. */
export function Popover({
  label, panelLabel, iconOnly, buttonClassName = "btn", className = "", disabled, align = "left", children,
}: Props) {
  const [open, setOpen] = useState(false);
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const id = useId();

  useEffect(() => {
    if (disabled) setOpen(false);
  }, [disabled]);

  useEffect(() => {
    if (!open) return;
    const onPointer = (e: PointerEvent) => {
      if (!root.current?.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      setOpen(false);
      trigger.current?.focus();
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  return (
    <div className={`popover-anchor ${className}`} ref={root}>
      <button ref={trigger} type="button" className={buttonClassName} disabled={disabled}
        aria-expanded={open} aria-controls={id} aria-label={iconOnly ? panelLabel : undefined}
        title={iconOnly ? panelLabel : undefined} onClick={() => setOpen((o) => !o)}>
        {label}
      </button>
      <div id={id} role="dialog" aria-label={panelLabel} className={`popover ${align === "right" ? "align-right" : ""}`} hidden={!open}>
        {children(open, () => setOpen(false))}
      </div>
    </div>
  );
}
