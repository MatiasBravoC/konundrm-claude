// Conventional Commits: "<type>(<scope>): <summary>", at most 72 characters, no emoji prefix.
export default {
  extends: ["@commitlint/config-conventional"],
  rules: {
    "header-max-length": [2, "always", 72],
    "type-enum": [
      2,
      "always",
      ["feat", "fix", "refactor", "test", "docs", "style", "perf", "chore", "build", "ci", "revert"],
    ],
    "subject-case": [0],
  },
};
