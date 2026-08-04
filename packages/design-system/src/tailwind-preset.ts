import type { Config } from "tailwindcss";

/**
 * Tailwind preset exposing the Round-6 tokens as theme values.
 * Tokens themselves live in `./tokens.css` (CSS custom properties);
 * this preset wires them to Tailwind classnames.
 */
const preset = {
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)"],
        mono: ["var(--font-mono)"],
      },
      colors: {
        surface: {
          canvas: "var(--surface-canvas)",
          card: "var(--surface-card)",
          raised: "var(--surface-raised)",
          sunken: "var(--surface-sunken)",
          overlay: "var(--surface-overlay)",
        },
        ink: {
          primary: "var(--ink-primary)",
          secondary: "var(--ink-secondary)",
          tertiary: "var(--ink-tertiary)",
          "on-accent": "var(--ink-on-accent)",
          disabled: "var(--ink-disabled)",
        },
        border: {
          subtle: "var(--border-subtle)",
          DEFAULT: "var(--border-default)",
          strong: "var(--border-strong)",
          focus: "var(--border-focus)",
        },
        brand: {
          50: "var(--brand-50)",
          100: "var(--brand-100)",
          300: "var(--brand-300)",
          500: "var(--brand-500)",
          600: "var(--brand-600)",
          700: "var(--brand-700)",
        },
        status: {
          "success-bg": "var(--status-success-bg)",
          "success-fg": "var(--status-success-fg)",
          "success-border": "var(--status-success-border)",
          "warning-bg": "var(--status-warning-bg)",
          "warning-fg": "var(--status-warning-fg)",
          "warning-border": "var(--status-warning-border)",
          "danger-bg": "var(--status-danger-bg)",
          "danger-fg": "var(--status-danger-fg)",
          "danger-border": "var(--status-danger-border)",
          "info-bg": "var(--status-info-bg)",
          "info-fg": "var(--status-info-fg)",
          "info-border": "var(--status-info-border)",
          "neutral-bg": "var(--status-neutral-bg)",
          "neutral-fg": "var(--status-neutral-fg)",
          "neutral-border": "var(--status-neutral-border)",
        },
      },
      borderRadius: {
        xs: "var(--radius-xs)",
        sm: "var(--radius-sm)",
        md: "var(--radius-md)",
        lg: "var(--radius-lg)",
        xl: "var(--radius-xl)",
        pill: "var(--radius-pill)",
      },
      boxShadow: {
        sm: "var(--shadow-sm)",
        md: "var(--shadow-md)",
        lg: "var(--shadow-lg)",
      },
      transitionDuration: {
        fast: "var(--motion-duration-fast)",
        DEFAULT: "var(--motion-duration)",
      },
      transitionTimingFunction: {
        DEFAULT: "var(--motion-ease)",
      },
    },
  },
} satisfies Partial<Config>;

export default preset;
