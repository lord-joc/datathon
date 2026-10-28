import type { Config } from "tailwindcss";

// All colours come from CSS variables in src/styles/tokens.css (master prompt §7.2).
const v = (name: string) => `rgb(var(--${name}) / <alpha-value>)`;

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        bg: v("bg"),
        surface: v("surface"),
        "surface-2": v("surface-2"),
        border: v("border"),
        text: v("text"),
        muted: v("text-muted"),
        subtle: v("text-subtle"),
        accent: v("accent"),
        "accent-strong": v("accent-strong"),
        warn: v("warn"),
        danger: v("danger"),
        ok: v("ok"),
      },
      fontFamily: {
        display: ["'Fraunces Variable'", "Georgia", "serif"],
        sans: ["Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        mono: ["'JetBrains Mono'", "ui-monospace", "Menlo", "monospace"],
      },
      fontSize: {
        xs: ["12px", "16px"],
        sm: ["14px", "20px"],
        base: ["16px", "24px"],
        lg: ["18px", "26px"],
        xl: ["22px", "28px"],
        "2xl": ["28px", "34px"],
        "3xl": ["36px", "42px"],
        "4xl": ["48px", "52px"],
      },
      borderRadius: { card: "12px" },
      minHeight: { touch: "44px" },
      minWidth: { touch: "44px" },
    },
  },
  plugins: [],
} satisfies Config;
