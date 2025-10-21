# Diagnostics

The repository ships with a preventive diagnostics suite under `tools/diag/`. It
runs quickly, relies on static analysis by default, and produces machine-readable
artifacts that are uploaded from CI and can be consumed by editor tooling.

## CLI

```bash
python3 tools/e2e_diag.py [--smoke] [--watch] [--fail-on=high|medium|low] \
  [--only=R1,R2] [--skip=R3] [--baseline diagnostics/baseline.json] \
  [--format text|md|json|sarif]
```

Key flags:

- `--smoke`: enable optional runtime checks (Electron binary presence,
  backend health probe).
- `--watch`: rerun diagnostics when tracked files change.
- `--fail-on`: control which severities cause exit code `2`.
- `--only` / `--skip`: filter rule execution.
- `--baseline`: ignore historical findings stored in JSON format.
- `--format`: choose the stdout rendering while artifacts are always written to
  `diagnostics/run_latest/`.

## Artifacts

Each run overwrites `diagnostics/run_latest/` with:

- `checks.json`: SARIF-inspired JSON summary including schema version, counts,
  and filtered findings.
- `summary.txt` / `summary.md`: human-readable snapshots.
- `checks.sarif`: SARIF v2.1.0 for IDE integration.

Artifacts embed the diagnostics schema version (`1.0.0`) for forward
compatibility.

## Rule catalog

Rules are organized into focused modules under `tools/diag/` and are registered
via decorators. The initial catalog covers:

| Rule | Area | Summary |
| ---- | ---- | ------- |
| R1–R3 | Browser shell | Detect unsafe iframe navigation and enforce webview usage. |
| R4–R7 | Electron preferences | Ensure hardened `webPreferences` defaults. |
| R9 | Headers | Preserve client hints and Accept-Language in custom hooks. |
| R10 | Proxy | Flag absolute proxy fetches to third-party origins. |
| R11 | Scripts | Verify desktop scripts and dev/build port consistency. |
| R12 | Next.js | Detect restrictive headers or missing `images.domains`. |
| R13 | Python backend | Check dependency alignment and debug toggles. |
| R14–R16 | Security baseline | Ensure env docs and safe Electron sandbox flags. |
| S1–S2 | Smoke | Optional runtime availability checks. |
| META_GLOBS | Meta | Remind maintainers to extend scan globs when new file types appear. |

Additions should follow the same pattern (`@register(...)`) so they auto-load
via `tools/diag/__init__.py`.

## Suppressions

- File-level suppressions can be expressed inline with comments such as
  `// diag: disable=R1`.
- Repository-wide suppressions live in `tools/diag/SUPPRESSED_RULES.yml`. Each
  entry documents the rule ID, optional path glob, and reason.

## Baselines

Store the output of `diagnostics/run_latest/checks.json` as
`diagnostics/baseline.json` to suppress known issues. The engine tracks findings
via deterministic fingerprints to surface only new deltas.

## Adding a new rule pack

1. Create `tools/diag/checks_<topic>.py`.
2. Implement functions decorated with `@register(...)` returning iterables of
   `Finding` objects.
3. Import the module from `tools/diag/__init__.py`.
4. Add targeted tests under `tools/diag/tests/` with fixtures or inline
   snippets.
5. Document noteworthy behaviour in this file if the rule has unusual
   requirements.
