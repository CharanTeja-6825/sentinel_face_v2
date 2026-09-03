/** @type {import('tailwindcss').Config} */
//
// Direction C, locked — see design/ROUND-2-CONTEXT.md.
//
// Two voices: `font-sans` (the default) IS the mono, because most of what this
// interface says is machine speech; `font-display` carries human statements.
//
export default {
  darkMode: ["class"],
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Azeret Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
        mono: ["Azeret Mono", "ui-monospace", "SFMono-Regular", "Menlo", "monospace"],
        display: ["Clash Display", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      // One scale, declared once. Every page previously invented its own heading
      // size — text-3xl on three pages, text-2xl on a fourth, CardTitle overridden
      // to text-base at seven call sites. Redefining the steps here fixes the scale
      // globally instead of at every use.
      fontSize: {
        xs:   ["0.75rem",   { lineHeight: "1.6" }],
        sm:   ["0.8125rem", { lineHeight: "1.7" }],
        base: ["0.875rem",  { lineHeight: "1.7" }],
        lg:   ["1rem",      { lineHeight: "1.55" }],
        xl:   ["1.25rem",   { lineHeight: "1.3",  letterSpacing: "-0.02em" }],
        "2xl":["1.75rem",   { lineHeight: "1.12", letterSpacing: "-0.028em" }],
        "3xl":["2.5rem",    { lineHeight: "0.98", letterSpacing: "-0.035em" }],
        "4xl":["3.5rem",    { lineHeight: "0.94", letterSpacing: "-0.04em" }],
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "var(--radius)",
        sm: "var(--radius)",
      },
      colors: {
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
          light: "hsl(var(--accent-light))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        success: {
          DEFAULT: "hsl(var(--success))",
          foreground: "hsl(var(--success-foreground))",
        },
        warning: {
          DEFAULT: "hsl(var(--warning))",
          foreground: "hsl(var(--warning-foreground))",
        },
        // The four message classes under their own names, so new code reads in the
        // locked direction's vocabulary rather than in shadcn's. Same values as the
        // legacy tokens above — aliases, not a fifth colour.
        accepted: "hsl(var(--foreground))",
        refuse: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        instruct: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
          wash: "hsl(var(--accent-light))",
        },
        measure: {
          DEFAULT: "hsl(var(--warning))",
          foreground: "hsl(var(--warning-foreground))",
        },
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
      },
      // C has one flat canvas and no shapes. Separation is hairlines and density.
      // Defined as `none` rather than deleted so the eleven existing `shadow-card`
      // call sites cannot reintroduce a raised surface.
      boxShadow: {
        card: "none",
        lift: "none",
      },
    },
  },
  plugins: [require("tailwindcss-animate")],
};
