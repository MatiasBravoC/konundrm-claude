import { defineConfig } from "vitest/config";

export default defineConfig({
  test: {
    coverage: {
      provider: "v8",
      include: ["src/**"],
      exclude: ["**/*.test.*", "**/*.spec.*", "**/__tests__/**"],
      // cobertura feeds diff-cover in CI (80 % on changed lines).
      reporter: ["text", "cobertura"],
      // Set to today's totals (rounded down) and raise them over time.
      thresholds: { branches: 0, lines: 0 },
    },
  },
});
