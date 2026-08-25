import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  darkMode: ["class", '[data-theme="dark"]'],
  theme: {
    extend: {
      fontFamily: {
        display: ['"Chakra Petch"', "sans-serif"],
        body: ['"IBM Plex Sans"', "system-ui", "sans-serif"],
        mono: ['"IBM Plex Mono"', "monospace"],
      },
      colors: {
        // surfaces / ink map to CSS variables in theme/tokens.css
        bg: "var(--bg)",
        surface: "var(--surface)",
        "surface-2": "var(--surface-2)",
        panel: "var(--panel)",
        ink: "var(--ink)",
        "ink-soft": "var(--ink-soft)",
        "ink-faint": "var(--ink-faint)",
        line: "var(--line)",
        accent: "var(--accent)",
        "accent-ink": "var(--accent-ink)",
        manager: "var(--manager)",
        "st-idle": "var(--st-idle)",
        "st-work": "var(--st-work)",
        "st-approval": "var(--st-approval)",
        "st-review": "var(--st-review)",
        "st-done": "var(--st-done)",
        "st-error": "var(--st-error)",
      },
      boxShadow: {
        panel: "var(--shadow-panel)",
      },
    },
  },
  plugins: [],
} satisfies Config;
