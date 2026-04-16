import path from "path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
    plugins: [react()],
    server: { port: 5125 },
    resolve: {
        alias: {
            // Import SDK TypeScript source directly — no pre-build required
            "@omnidapter/connect": path.resolve(
                __dirname,
                "../../packages/connect/src/index.ts"
            ),
        },
    },
});
