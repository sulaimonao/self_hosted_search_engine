import { defineConfig } from "vitest/config";
import path from "node:path";
import react from "@vitejs/plugin-react-swc";

export default defineConfig({
  root: __dirname,
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: ["./vitest.setup.ts"],
    globals: true,
    // Only include tests from the frontend `src` and local `tests` folder.
    include: ["src/**/*.{test,spec}.{ts,tsx,js,jsx}", "tests/**/*.spec.ts"],
    // Exclude top-level repo e2e and node_modules
    exclude: ["../**", "**/node_modules/**", "**/tests/e2e/**", "**/e2e/**"],
  },
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "src"),
    },
  },
});
