import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(import.meta.dirname, "src") } },
  server: {
    port: 5173,
    fs: { allow: [".."] }, // mock mode reads ../fixtures/scenarios
    proxy: { "/api": "http://127.0.0.1:7777" },
  },
  build: {
    outDir: "../src/runway/server/static",
    emptyOutDir: true,
    chunkSizeWarningLimit: 700,
  },
  test: { environment: "jsdom", include: ["src/**/*.test.ts", "src/**/*.test.tsx"] },
});
