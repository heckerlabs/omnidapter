import { defineConfig } from "vite";
import { resolve } from "path";

export default defineConfig({
    test: {
        environment: "jsdom",
    },
    build: {
        lib: {
            entry: {
                index: resolve(__dirname, "src/index.ts"),
                react: resolve(__dirname, "src/react.ts"),
            },
            formats: ["es"],
            fileName: (_, entryName) => `${entryName}.js`,
        },
        rollupOptions: {
            external: ["react"],
        },
        minify: "esbuild",
        target: "es2020",
    },
});
