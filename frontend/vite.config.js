import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  optimizeDeps: {
    exclude: ["pyodide"],
  },
  server: {
    port: 5173,
    proxy: {
      // Optional: call backend as /api/* from the browser
      "/api": {
        // Override when another app uses 8000: VITE_PROXY_TARGET=http://127.0.0.1:8010 npm run dev
        target: process.env.VITE_PROXY_TARGET ?? "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
