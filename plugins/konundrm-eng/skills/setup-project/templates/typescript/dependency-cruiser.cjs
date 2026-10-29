// Konundrm architecture rules. Keep only the layer rules for folders that exist today.
// Each comment says how to fix a violation: `npm run arch` prints it (--output-type err-long),
// so a person or an agent reading the error knows the remedy, not only the rule.
/** @type {import('dependency-cruiser').IConfiguration} */
module.exports = {
  forbidden: [
    {
      name: "no-circular",
      comment:
        "Cycle: move the piece both modules need into a third module they both import, " +
        "or invert one dependency behind an interface (Standards → Design).",
      severity: "error",
      from: {},
      to: { circular: true },
    },
    {
      name: "domain-depends-on-nothing-outer",
      comment:
        "The domain imported an outer layer. Define the interface the domain needs inside " +
        "src/domain and implement it in src/infrastructure; pass it in from the entry point.",
      severity: "error",
      from: { path: "^src/domain" },
      to: { path: "^src/(application|infrastructure|entrypoints|ui)" },
    },
    {
      name: "application-depends-inward",
      comment:
        "A use case imported infrastructure or an entry point. Depend on a domain or " +
        "application interface instead, and wire the implementation at the entry point.",
      severity: "error",
      from: { path: "^src/application" },
      to: { path: "^src/(infrastructure|entrypoints|ui)" },
    },
    {
      name: "production-does-not-import-tests",
      comment: "Production code imported a test file. Move the shared helper into src/.",
      severity: "error",
      from: { pathNot: "(\\.(test|spec)\\.[cm]?[jt]sx?$)|(__tests__)" },
      to: { path: "(\\.(test|spec)\\.[cm]?[jt]sx?$)|(__tests__)" },
    },
  ],
  options: {
    doNotFollow: { path: "node_modules" },
    tsPreCompilationDeps: true,
    tsConfig: { fileName: "tsconfig.json" },
  },
};
