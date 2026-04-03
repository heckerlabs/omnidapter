import path from "path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      // Import SDK TypeScript source directly — no pre-build required
      "@omnidapter/connect-sdk": path.resolve(
        __dirname,
        "../../packages/connect-sdk/src/index.ts"
      ),
    },
  },
});
