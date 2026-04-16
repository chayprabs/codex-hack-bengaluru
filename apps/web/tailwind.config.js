/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}", "./lib/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#081018",
        midnight: "#0f1723",
        mist: "#ebf3ff",
        signal: "#5eead4",
        ember: "#fb7185",
      },
      boxShadow: {
        halo: "0 30px 80px rgba(8, 16, 24, 0.18)",
      },
      backgroundImage: {
        "hero-grid":
          "linear-gradient(rgba(147, 197, 253, 0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(147, 197, 253, 0.1) 1px, transparent 1px)",
      },
      fontFamily: {
        sans: ["Segoe UI Variable Text", "Trebuchet MS", "Segoe UI", "sans-serif"],
      },
    },
  },
  plugins: [],
};
