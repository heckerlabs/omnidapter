import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  const target = env.VITE_API_URL || "http://localhost:8000";

  return {
    plugins: [react()],
    server: {
      proxy: { "/connect": { target, changeOrigin: true } },
    },
  };
});
