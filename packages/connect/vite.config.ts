import { defineConfig } from "vite";

export default defineConfig({
  test: {
    environment: "jsdom",
  },
  build: {
    lib: {
      entry: "src/index.ts",
      name: "OmnidapterConnect",
      fileName: (format) => `omnidapter-connect.${format}.js`,
      formats: ["es", "umd"],
    },
    rollupOptions: {
      external: [],
      output: {
        globals: {},
      },
    },
    minify: "terser",
    target: "es2020",
  },
});
