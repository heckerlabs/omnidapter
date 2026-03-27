import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
  },
  base: "/connect/",
  server: {
    proxy: {
      "/connect/providers": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
      "/connect/connections": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
});
