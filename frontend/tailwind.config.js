/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: "class",
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // McKinsey Executive Consulting Palette
        mckinsey: {
          navy: "#051C2C",        // Midnight Navy - primary branding & authoritative headings
          blue: "#002B49",        // Deep McKinsey Blue - primary buttons & left accent bars
          cobalt: "#005A9C",      // Signature Cobalt - active stepper, progress fill, kickers
          lightBlue: "#E8F1F8",   // Soft cobalt tint
          sage: "#0D5E4D",        // Forest Sage - passed QA, approved, delivered deck
          sageBg: "#EDF7F4",      // Sage badge ground
          sageBorder: "#B4DFD4",  // Sage border
          ochre: "#8D5B00",       // Warm Ochre - human review gate, pending action
          ochreBg: "#FFF8EC",     // Ochre badge ground
          ochreBorder: "#F5D6A0", // Ochre border
          crimson: "#941B1B",     // Muted Crimson - risks, critical alerts, errors
          crimsonBg: "#FDF2F2",   // Crimson badge ground
          crimsonBorder: "#F5C2C2",// Crimson border
          ground: "#F7F9FB",      // Warm porcelain canvas ground
          card: "#FFFFFF",        // Pristine white card surface
          border: "#E2E6EB",      // 1px hairline card borders
          borderLight: "#ECEFF2", // Subtle divider lines
          textPrimary: "#121820", // High-contrast primary text
          textSecondary: "#4A5568", // Legible secondary text
          textMuted: "#718096",   // Kicker and metadata text
        },
        // Slate - neutral surfaces & text
        slate: {
          50: "#f8fafc",
          100: "#f1f5f9",
          200: "#e2e8f0",
          300: "#cbd5e1",
          400: "#94a3b8",
          500: "#64748b",
          600: "#475569",
          700: "#334155",
          800: "#1e293b",
          900: "#0f172a",
          950: "#020617",
        },
        // Brand blue (updated with McKinsey shades)
        brand: {
          50: "#eff6ff",
          100: "#e8f1f8",
          200: "#bfdbfe",
          300: "#93c5fd",
          400: "#60a5fa",
          500: "#005A9C",
          600: "#002B49",
          700: "#051C2C",
          800: "#1e40af",
          900: "#051C2C",
          950: "#020617",
        },
        // Success / Status
        success: {
          50: "#edf7f4",
          100: "#d1fae5",
          200: "#b4dfd4",
          300: "#6ee7b7",
          400: "#34d399",
          500: "#0D5E4D",
          600: "#0D5E4D",
          700: "#047857",
          800: "#065f46",
          900: "#064e3b",
          950: "#022c22",
        },
      },
      fontFamily: {
        serif: ["Georgia", "Cambria", "'Times New Roman'", "Times", "serif"],
        sans: ["var(--font-inter)", "-apple-system", "BlinkMacSystemFont", "'Segoe UI'", "Roboto", "sans-serif"],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Monaco", "Consolas", "'Liberation Mono'", "'Courier New'", "monospace"],
      },
    },
  },
  plugins: [],
};
