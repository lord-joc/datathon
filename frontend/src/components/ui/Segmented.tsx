import { useId } from "react";

interface Option<T extends string | number> {
  value: T;
  label: string;
}

interface SegmentedProps<T extends string | number> {
  label: string;
  hideLabel?: boolean;
  options: readonly Option<T>[];
  value: T;
  onChange: (value: T) => void;
  disabled?: boolean;
  size?: "md" | "sm";
}

/** Radio group styled as a segmented control; arrow keys move between options natively. */
export function Segmented<T extends string | number>({
  label,
  hideLabel = false,
  options,
  value,
  onChange,
  disabled = false,
  size = "md",
}: SegmentedProps<T>) {
  const name = useId();
  return (
    <fieldset disabled={disabled} className="grid gap-2">
      <legend className={hideLabel ? "sr-only" : "mb-2 text-sm font-medium"}>{label}</legend>
      <div
        className="grid rounded-lg border border-border bg-bg p-1"
        style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}
      >
        {options.map((o) => {
          const checked = o.value === value;
          return (
            <label
              key={String(o.value)}
              className={[
                "flex min-h-touch cursor-pointer items-center justify-center rounded-md px-2 text-center transition-colors has-[:focus-visible]:shadow-[var(--focus-ring)]",
                size === "sm" ? "text-xs" : "text-sm",
                checked
                  ? "bg-accent/10 font-semibold text-accent-strong"
                  : "text-muted hover:text-text",
                disabled ? "cursor-not-allowed opacity-60" : "",
              ].join(" ")}
            >
              <input
                type="radio"
                name={name}
                className="sr-only"
                checked={checked}
                onChange={() => onChange(o.value)}
              />
              {o.label}
            </label>
          );
        })}
      </div>
    </fieldset>
  );
}
