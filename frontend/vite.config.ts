import { fileURLToPath, URL } from "node:url";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  server: {
    port: 5173,
    strictPort: true,
    // In development the API is reached through Caddy on :8080 (docker compose); the API itself
    // has no published port. Same-origin in production.
    proxy: { "/api": { target: "http://localhost:8080", changeOrigin: false } },
  },
  build: {
    target: "es2020",
    sourcemap: false,
    // Never inline assets as data: URIs; the CSP only allows fonts and images from self.
    assetsInlineLimit: 0,
    cssCodeSplit: true,
    rollupOptions: {
      output: {
        manualChunks: {
          react: ["react", "react-dom", "react-router"],
          query: ["@tanstack/react-query"],
        },
      },
    },
  },
  test: {
    environment: "jsdom",
    // Playwright specs in tests/e2e run against a live stack, not in Vitest.
    include: ["src/**/*.test.{ts,tsx}"],
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: false,
  },
});
