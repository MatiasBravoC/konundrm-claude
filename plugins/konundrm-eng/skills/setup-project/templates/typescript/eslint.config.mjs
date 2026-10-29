// Konundrm quality gates for TypeScript (ESLint flat config). Merge with the project's config.
import js from "@eslint/js";
import jsdoc from "eslint-plugin-jsdoc";
import tseslint from "typescript-eslint";

export default [
  { ignores: ["dist/", "build/", "coverage/", "reports/", "node_modules/"] },
  // Standards → Gate integrity: an eslint-disable that no longer silences anything is an error.
  { linterOptions: { reportUnusedDisableDirectives: "error" } },
  js.configs.recommended,
  ...tseslint.configs.strictTypeChecked,
  jsdoc.configs["flat/recommended-typescript"],
  {
    languageOptions: {
      parserOptions: { projectService: true, tsconfigRootDir: import.meta.dirname },
    },
    rules: {
      // Standards → Design: complexity limits.
      complexity: ["error", 10],
      "max-depth": ["warn", 3],
      "max-params": ["warn", 4],
      // Standards → Security: no code built from strings (strictTypeChecked covers no-implied-eval).
      "no-eval": "error",
      "no-new-func": "error",
      // Standards → Documentation: the public surface is documented.
      "jsdoc/require-jsdoc": [
        "error",
        {
          publicOnly: true,
          require: { FunctionDeclaration: true, ClassDeclaration: true, MethodDefinition: true },
        },
      ],
    },
  },
  {
    // Test names state the behavior; doc-comments are optional in tests.
    files: ["**/*.test.*", "**/*.spec.*", "**/__tests__/**", "tests/**", "e2e/**"],
    rules: { "jsdoc/require-jsdoc": "off" },
  },
  {
    files: ["**/*.{js,mjs,cjs}"],
    ...tseslint.configs.disableTypeChecked,
  },
];
