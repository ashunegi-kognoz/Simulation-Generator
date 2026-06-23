/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Measured "operations console" palette — deliberately not the AI defaults.
        canvas: "#EEF1F5", // cool pale slate (not cream)
        ink: "#0E1620", // deep blue-black
        muted: "#5A6675",
        faint: "#8A95A3",
        line: "#D7DEE7",
        panel: "#FFFFFF",
        petrol: { DEFAULT: "#0B6E63", hover: "#095B52", soft: "#E1F0EE" },
        amber: { DEFAULT: "#C77F0A", soft: "#FBEFD8" }, // budget not balanced
        coral: { DEFAULT: "#C4453C", soft: "#FAE3E1" }, // over budget / errors
        grass: { DEFAULT: "#14855E", soft: "#DCF0E7" }, // balanced
        // Posture colors are revealed ONLY in the debrief / analytics.
        protect: "#2F6BD6",
        enable: "#15A06A",
        hybrid: "#7C58D6",
        defer: "#C77F0A",
      },
      fontFamily: {
        display: ['"Space Grotesk"', "system-ui", "sans-serif"],
        sans: ['"Inter"', "system-ui", "sans-serif"],
        mono: ['"JetBrains Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
      },
      borderRadius: { xl: "14px", "2xl": "20px" },
      boxShadow: {
        panel: "0 1px 2px rgba(14,22,32,0.04), 0 8px 24px rgba(14,22,32,0.06)",
      },
    },
  },
  plugins: [],
};
