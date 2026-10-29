// Konundrm mutation testing for TypeScript (Standards → Verification by risk).
// Locally and nightly the run only reports. On pull requests labelled risk:high, CI mutates the
// changed lines only and sets STRYKER_BREAK=100, so a surviving mutant there fails the build.
// An equivalent mutant is disabled on its line with the reason:
//   // Stryker disable next-line <Mutator>: <why no test can tell it apart>
/** @type {import('@stryker-mutator/api/core').PartialStrykerOptions} */
const config = {
  testRunner: "vitest",
  coverageAnalysis: "perTest",
  mutate: ["src/**/*.ts", "src/**/*.tsx", "!src/**/*.test.*", "!src/**/*.spec.*", "!src/**/__tests__/**"],
  reporters: ["clear-text", "html"],
  // Stryker needs all three thresholds together; break: null never fails the run.
  thresholds: {
    high: 80,
    low: 60,
    break: process.env.STRYKER_BREAK ? Number(process.env.STRYKER_BREAK) : null,
  },
};

export default config;
