import type { Config } from "tailwindcss";

export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        heading: ["'Noto Serif SC'", "'STSong'", "serif"],
        body: ["'Space Grotesk'", "'Microsoft YaHei'", "sans-serif"]
      },
      colors: {
        ink: {
          50: "#f8f4eb",
          100: "#f2e9d6",
          200: "#dbc7a1",
          300: "#be9e72",
          700: "#503922",
          900: "#20140b"
        },
        bronze: "#c76f2d",
        danger: "#8f1f1f",
        safe: "#1d6f43"
      },
      boxShadow: {
        panel: "0 16px 42px rgba(32,20,11,0.18)",
        glowDanger: "0 0 45px rgba(200, 38, 38, 0.35)",
        glowSafe: "0 0 45px rgba(36, 143, 79, 0.28)"
      },
      backgroundImage: {
        parchment: "radial-gradient(circle at 20% 10%, rgba(255,245,225,0.86), rgba(231,211,171,0.78) 45%, rgba(193,159,112,0.72) 90%)"
      }
    }
  },
  plugins: []
} satisfies Config;
