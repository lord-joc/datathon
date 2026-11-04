import type { ButtonHTMLAttributes } from "react";

type Variant = "primary" | "ghost";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
}

const VARIANTS: Record<Variant, string> = {
  primary:
    "bg-accent text-on-accent hover:bg-accent-strong disabled:bg-surface-2 disabled:text-subtle",
  ghost: "border border-border text-text hover:bg-surface-2 disabled:text-subtle",
};

export function Button({
  variant = "primary",
  className = "",
  type = "button",
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={[
        "inline-flex min-h-touch items-center justify-center gap-2 rounded-lg px-4 text-sm font-semibold transition-colors disabled:cursor-not-allowed",
        VARIANTS[variant],
        className,
      ].join(" ")}
      {...rest}
    />
  );
}
