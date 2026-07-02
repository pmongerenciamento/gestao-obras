import type { Config } from "tailwindcss";

const config: Config = {
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        pmon: {
          black: "#0D0D0D",
          yellow: "#F5C400",
          white: "#FFFFFF",
        },
      },
    },
  },
  plugins: [],
};

export default config;
