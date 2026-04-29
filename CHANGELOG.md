# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- `bind` keyword on all four renderers (`OrganismRenderer`, `InstancedOrganismRenderer`, `SolarSystemRenderer`, `PlaybackRenderer`) — defaults to `127.0.0.1`, set to `"0.0.0.0"` to expose on LAN.
- GitHub Actions CI: pytest matrix on Python 3.10 / 3.11 / 3.12 on every push and pull request.
- `# SPDX-License-Identifier: Apache-2.0` header on every source file.

### Fixed
- Renderer HTTP servers no longer bind to `0.0.0.0` by default. Previous behaviour silently exposed the local visualization session to anyone on the LAN.
- Removed `Access-Control-Allow-Origin: *` from the instanced and solar-system renderer API endpoints — same-origin only now.
- Replaced all 14 uses of `datetime.utcnow()` (deprecated since 3.12) with `datetime.now(timezone.utc)`. Eliminates 2,257 deprecation warnings during the test suite.

### Removed
- 45 `__pycache__/*.pyc` files mistakenly tracked in git despite `__pycache__/` being in `.gitignore`.

## [2.0.0] — 2026-04

### Added
- Tree-sitter parser dispatcher covering JavaScript, TypeScript, Java, Go, Rust, C, and C++ in addition to native-AST Python.
- KuzuDB graph persistence with health columns, community memberships, and process flows. Re-queryable via Cypher without re-parsing.
- Leiden community detection via igraph.
- McCabe / cognitive / Halstead / maintainability metrics combined into a single biological health score: `HEALTHY` → `STRESSED` → `INFLAMED` → `NECROTIC` → `CANCEROUS`.
- Malware detector: 30+ dangerous-import signatures plus 11 behavioural regex patterns, scored on a 4-tier severity scale.
- 12 anti-pattern detectors (god class, deep nesting, long function, bare except, star imports, circular imports, ...).
- `sys.settrace` instrumentation that records calls / returns / exceptions with nanosecond timestamps and locals into `.corg` recording files (gzip + JSON).
- Four WebGL renderers — force-directed, GPU-instanced (1000+ nodes), solar-system hierarchical navigator, and playback renderer with 0.01x–100x speed control.
- MCP server exposing `analyze`, `health`, `impact`, `communities`, `query` to any MCP-compatible agent.
- `cli.py` with a JSON output contract for every subcommand (`analyze`, `health`, `index`, `impact`, `communities`, `query`, `impact-graph`).

[Unreleased]: https://github.com/adam-scott-thomas/code_organism/compare/v2.0.0...HEAD
[2.0.0]: https://github.com/adam-scott-thomas/code_organism/releases/tag/v2.0.0
