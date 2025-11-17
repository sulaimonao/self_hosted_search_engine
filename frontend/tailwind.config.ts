import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./src/**/*.{ts,tsx,mdx}",
    "./src/app/**/*.{ts,tsx,mdx}",
    "./src/components/**/*.{ts,tsx,mdx}",
    "./src/lib/**/*.{ts,tsx,mdx}",
    "./src/hooks/**/*.{ts,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        app: {
          bg: "var(--bg-app)",
          subtle: "var(--bg-subtle)",
          elevated: "var(--bg-elevated)",
          card: "var(--bg-card)",
          "card-subtle": "var(--bg-card-subtle)",
          "card-hover": "var(--bg-card-hover)",
          input: "var(--bg-input)",
        },
        ai: {
          panel: "var(--bg-ai-panel)",
          border: "var(--border-ai-panel)",
        },
        fg: {
          DEFAULT: "var(--fg-default)",
          muted: "var(--fg-muted)",
          subtle: "var(--fg-subtle)",
          "on-accent": "var(--fg-on-accent)",
        },
        border: {
          subtle: "var(--border-subtle)",
          strong: "var(--border-strong)",
        },
        accent: {
          DEFAULT: "var(--accent)",
          soft: "var(--accent-soft)",
          strong: "var(--accent-strong)",
        },
        state: {
          success: "var(--success)",
          warning: "var(--warning)",
          danger: "var(--danger)",
          info: "var(--info)",
        },
      },
      borderRadius: {
        xs: "var(--radius-xs)",
        md: "var(--radius-md)",
        xl: "var(--radius-xl)",
      },
      boxShadow: {
        soft: "var(--shadow-soft)",
        subtle: "var(--shadow-subtle)",
      },
      transitionTimingFunction: {
        DEFAULT: "var(--ease-default)",
        default: "var(--ease-default)",
      },
      transitionDuration: {
        fast: "var(--duration-fast)",
        normal: "var(--duration-normal)",
      },
    },
  },
  plugins: [],
};

export default config;
