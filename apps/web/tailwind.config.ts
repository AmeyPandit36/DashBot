import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./features/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        canvas: "rgb(var(--canvas) / <alpha-value>)",
        surface: "rgb(var(--surface) / <alpha-value>)",
        elevated: "rgb(var(--elevated) / <alpha-value>)",
        ink: "rgb(var(--ink) / <alpha-value>)",
        muted: "rgb(var(--muted) / <alpha-value>)",
        faint: "rgb(var(--faint) / <alpha-value>)",
        line: "rgb(var(--line) / <alpha-value>)",
        brand: {
          DEFAULT: "#4F6BFF",
          soft: "#EEF1FF",
          600: "#3D57E8",
          700: "#2F45C7",
        },
        violet: "#8B5CF6",
        cyan: "#06B6D4",
        teal: "#14B8A6",
        magenta: "#D946EF",
        success: "#10B981",
        warning: "#F59E0B",
        danger: "#F43F5E",
      },
      fontFamily: {
        sans: ["InterVariable", "Inter", "system-ui", "-apple-system", "Segoe UI", "sans-serif"],
        display: ["SoraVariable", "Sora", "InterVariable", "system-ui", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
      },
      borderRadius: {
        xl: "0.875rem",
        "2xl": "1.125rem",
        "3xl": "1.5rem",
      },
      boxShadow: {
        glass: "0 1px 1px rgba(255,255,255,0.45) inset, 0 18px 40px -24px rgba(21,27,50,0.35)",
        card: "0 1px 2px rgba(21,27,50,0.04), 0 12px 32px -20px rgba(21,27,50,0.25)",
        float: "0 30px 80px -40px rgba(21,27,50,0.45)",
        glow: "0 0 0 1px rgba(79,107,255,0.25), 0 18px 60px -30px rgba(79,107,255,0.65)",
      },
      keyframes: {
        "fade-up": {
          "0%": { opacity: "0", transform: "translateY(10px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "fade-in": { "0%": { opacity: "0" }, "100%": { opacity: "1" } },
        shimmer: {
          "0%": { backgroundPosition: "-700px 0" },
          "100%": { backgroundPosition: "700px 0" },
        },
        float: {
          "0%,100%": { transform: "translateY(0px)" },
          "50%": { transform: "translateY(-8px)" },
        },
        pulseRing: {
          "0%": { boxShadow: "0 0 0 0 rgba(79,107,255,0.45)" },
          "70%": { boxShadow: "0 0 0 12px rgba(79,107,255,0)" },
          "100%": { boxShadow: "0 0 0 0 rgba(79,107,255,0)" },
        },
      },
      animation: {
        "fade-up": "fade-up 0.5s cubic-bezier(0.22, 1, 0.36, 1) both",
        "fade-in": "fade-in 0.4s ease both",
        shimmer: "shimmer 1.6s linear infinite",
        float: "float 7s ease-in-out infinite",
        "pulse-ring": "pulseRing 2s ease-out infinite",
      },
      backgroundImage: {
        "brand-gradient": "linear-gradient(120deg, #4F6BFF 0%, #8B5CF6 45%, #06B6D4 100%)",
        "aurora": "radial-gradient(60% 50% at 15% 10%, rgba(79,107,255,0.20) 0%, transparent 60%), radial-gradient(50% 45% at 85% 5%, rgba(139,92,246,0.18) 0%, transparent 60%), radial-gradient(45% 40% at 60% 90%, rgba(6,182,212,0.14) 0%, transparent 60%)",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};

export default config;
