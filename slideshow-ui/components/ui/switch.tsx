"use client";

import { cn } from "@/lib/utils";

export function Switch({
  checked = false,
  onCheckedChange,
  disabled = false,
  className,
  id,
  "aria-label": ariaLabel,
}) {
  return (
    <button
      type="button"
      role="switch"
      id={id}
      aria-checked={checked}
      aria-label={ariaLabel}
      disabled={disabled}
      onClick={() => onCheckedChange?.(!checked)}
      className={cn(
        "toggle-track shrink-0",
        checked ? "toggle-track-on" : "toggle-track-off",
        disabled && "opacity-50 cursor-not-allowed",
        className,
      )}
    >
      <span className="toggle-thumb" />
    </button>
  );
}
