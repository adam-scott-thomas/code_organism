# Code Organism

[![tests](https://github.com/adam-scott-thomas/code_organism/actions/workflows/test.yml/badge.svg)](https://github.com/adam-scott-thomas/code_organism/actions/workflows/test.yml)
[![python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-blue)](https://www.python.org/)
[![license](https://img.shields.io/badge/license-Apache%202.0-blue)](LICENSE)
[![code style: ruff](https://img.shields.io/badge/code%20style-ruff-261230)](https://github.com/astral-sh/ruff)

> **See the soul of software.** A code intelligence engine that treats your codebase like a living thing — parses it, measures its vital signs, detects its cancers, and renders it in 3D.

Static analyzers hand you a JSON blob. Linters yell at you line-by-line. Code Organism gives you a **spatial, health-scored, interactively navigable** view of what you actually built — across eight languages, backed by a persistent graph database, with malware detection and runtime tracing wired in.

---

## What it does

| | |
|---|---|
| **Parses 8 languages** | Python (native AST), JavaScript, TypeScript, Java, Go, Rust, C, C++ via tree-sitter — one dispatcher, unified node model |
| **Scores health per node** | McCabe cyclomatic, cognitive complexity, Halstead volume/effort/bugs, maintainability index → collapsed into a biological state: `HEALTHY` → `STRESSED` → `INFLAMED` → `NECROTIC` → `CANCEROUS` |
| **Detects malware patterns** | 30+ dangerous-import signatures (C2 channels, crypto mining, ransomware) + 11 behavioral regex patterns, scored on a 4-tier severity scale with remediation notes |
| **Flags 12 anti-patterns** | God class, deep nesting, long function, bare except, star imports, circular imports, long parameter list, and friends |
| **Persists to a graph DB** | KuzuDB schema with health columns, community memberships, and process flows — query with Cypher, no re-parsing |
| **Detects communities** | Leiden algorithm via igraph — finds cohesive functional areas (12K-LOC project → ~26 meaningful clusters, not 500 microscopic ones) |
| **Traces execution** | `sys.settrace` instrumentation captures every call/return/exception with nanosecond timestamps and local variables, saves to `.corg` recording format |
| **Renders in 3D** | Four WebGL modes: force-directed, GPU-instanced (1000+ nodes), solar-system hierarchical navigator, and a playback renderer with 0.01x–100x speed control |
| **Serves as an MCP tool** | Plug straight into Claude Code / any MCP-compatible agent and ask "what does this function depend on?" in plain English |

---

## Quickstart

```bash
# Install
git clone https://github.com/adam-scott-thomas/code_organism.git
cd code_organism
pip install -e .

# Visualize any codebase (opens browser)
python -m Code_Organism /path/to/your/project

# Just the numbers
python -m Code_Organism --stats /path/to/your/project

# Scan for malware
python -m Code_Organism --malware-scan suspicious_script.py

# Giant codebase? GPU-instanced renderer handles 1000+ nodes
python -m Code_Organism --instanced /path/to/monorepo
```

---

## CLI subcommands

The `cli.py` entry point exposes the engine as composable subcommands with a JSON contract (`--output json` everywhere; stdout = data, stderr = logs, exit 0 = success):

```bash
python cli.py analyze      <path> --output json    # parse → nodes, edges, stats
python cli.py health       <path> --output json    # per-node health scores
python cli.py index        <path> --db graph.kuzu  # persist to KuzuDB
python cli.py impact       <path> --target foo --output json   # blast radius
python cli.py communities  <path> --output json    # Leiden clustering
python cli.py query        --db graph.kuzu "MATCH (f:Function) RETURN f LIMIT 10"
python cli.py impact-graph --db graph.kuzu --target foo
```

`query` and `impact-graph` hit the persisted KuzuDB directly — no re-parsing on every call.

---

## The health model

Every function, class, and module gets a composite health score in `[0.0, 1.0]`, then bucketed:

```
CC=5,  depth=2,  LOC=30    →  0.95  HEALTHY      clean, well-structured
CC=12, depth=4,  LOC=120   →  0.70  STRESSED     rising complexity, still readable
CC=22, depth=6,  LOC=250   →  0.45  INFLAMED     complexity hot-spot, refactor candidate
CC=40, depth=8,  LOC=500   →  0.15  CANCEROUS    obfuscated or out of control
(unreached by any call graph edge)  →  0.00  NECROTIC   dead code, remove it
```

The biology metaphor isn't decorative — it maps cleanly onto how code actually decays. Healthy code has short paths. Stressed code has deepening nests. Cancerous code hides: bare excepts, dynamic imports, exec chains. Necrotic code is the function nobody calls anymore but nobody dares delete.

---

## Malware detection

```bash
python -m Code_Organism --malware-scan target.py
```

Pattern categories:
- **Code injection** — `exec`, `eval`, `compile` on non-literal input
- **Obfuscation** — base64 of decoded blobs, `__import__` chains, dotted-name assembly
- **C2 channels** — hardcoded IP:port in socket calls, suspicious DNS lookups, Telegram/Discord API fingerprints
- **Self-modification** — writes to `__file__`, `sys.modules` mutation
- **Resource exhaustion** — crypto-miner imports (`pycryptodome` + network + loop), fork bombs
- **Privilege escalation** — Windows registry writes, `os.setuid`, service-install patterns

Each marker carries severity (LOW/MEDIUM/HIGH/CRITICAL), confidence (0.0–1.0), file:line location, and a remediation note.

---

## Architecture

```
                       ┌──────────────────────┐
        source tree ─▶ │  parser/dispatcher   │ ─ picks tree-sitter or native AST per language
                       └──────────┬───────────┘
                                  ▼
                       ┌──────────────────────┐
                       │  model/organism      │ ─ 13 node types, 5 edge types
                       └──────────┬───────────┘
                                  ▼
         ┌───────────────┬────────┴────────┬─────────────────┐
         ▼               ▼                 ▼                 ▼
  health/complexity  health/malware  analysis/communities  analysis/impact
  health/patterns                    analysis/processes    (blast radius)
         │               │                 │                 │
         └───────────────┴────────┬────────┴─────────────────┘
                                  ▼
                       ┌──────────────────────┐
                       │  graph/ (KuzuDB)     │ ─ persistent, queryable
                       └──────────┬───────────┘
                                  ▼
         ┌───────────────────────┬┴────────────────────────┐
         ▼                       ▼                         ▼
   renderer/graph_3d     renderer/solar_system    renderer/playback_renderer
   renderer/graph_3d_instanced                    (+ tracer/ → .corg files)
         │                                                  │
         └──────────────────── browser (Three.js) ──────────┘
```

---

## MCP server

Expose the whole engine as tools for Claude, Cursor, or any MCP client:

```bash
python -m Code_Organism.mcp_server
```

### One-line install for common MCP clients

**Claude Code** — add it once with the CLI:
```bash
claude mcp add code-organism -- python -m Code_Organism.mcp_server
```

**Claude Desktop** — append to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):
```json
{
  "mcpServers": {
    "code-organism": {
      "command": "python",
      "args": ["-m", "Code_Organism.mcp_server"]
    }
  }
}
```

**Cursor** / **Continue** — same JSON shape under `mcpServers`. Drop into the IDE's MCP settings.

**Docker** — run the MCP server container; default `CMD` already serves it:
```bash
docker run -i --rm code-organism
```

Your AI agent can now call `analyze`, `health`, `impact`, `communities`, and `query` directly — on any project you point it at.

---

## Dynamic tracing & playback

```python
from Code_Organism import Organism

org = Organism.from_directory("my_project/")

# Record execution with sys.settrace — every call, return, exception,
# with nanosecond timestamps and captured locals
with org.trace(output="session.corg.gz"):
    import my_project
    my_project.main()

# Replay later in the browser, with scrub controls
# (0.01x–100x, binary-search seeking, 17 keyboard shortcuts)
```

```bash
python -m Code_Organism --playback session.corg.gz
```

The playback renderer streams a recorded run through the same force-directed scene, so you can watch the bloodstream of a real execution light up the graph.

---

## Why this exists

The toolchain for understanding a codebase peaks at the level of a single file. Call graphs, when they exist, are flat 2D diagrams that collapse at scale. Complexity metrics are tables of numbers detached from structure. Malware scanners operate on bytes, not semantics. None of them talk to each other.

Code Organism is a single engine that answers:

- What does this project actually look like, shaped in space?
- Which parts of it are sick, and how sick?
- What's the blast radius of changing *this* function?
- Which functions are dead? Which are hot? Which are suspicious?
- How did this execution actually flow?

All queryable, all persistent, all scriptable, all visual.

---

## Status

- **v2.0** — 148 tests passing, 8-language parser, KuzuDB persistence, MCP server live
- 12K LOC engine, ~26 communities detected on self-analysis
- Tree-sitter for everything non-Python; native Python `ast` for the richer Python node model

---

## License

Apache 2.0. See [LICENSE](LICENSE).

## Author

Adam Thomas — Ghost Logic Tech Company. Part of the [Ghost Logic](https://github.com/GhostLogicTech) forensic intelligence stack.
