# Code_Organism Engine Upgrade — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform Code_Organism from a Python-only visualization tool into the canonical code analysis engine with persistent graph storage, multi-language parsing, community/process detection, and impact analysis — absorbing GitNexus's core capabilities while keeping Code_Organism's unique health diagnostics and visualization.

**Architecture:** Code_Organism becomes a Python package that parses code (Python via `ast`, all other languages via `tree-sitter`), stores the results in a persistent KuzuDB graph, and exposes all analysis through a JSON CLI contract. GitNexus (Node.js) becomes a thin MCP adapter that calls Code_Organism's CLI. The graph stores health scores, malware flags, complexity metrics, community assignments, and execution flow data — something neither tool could do alone.

**Tech Stack:** Python 3.12, tree-sitter (py-tree-sitter 0.25+), KuzuDB 0.11.3 (archived but functional — migration path: RyuGraph fork), python-igraph (Leiden community detection), existing stdlib for health/malware/tracing.

**Risk — KuzuDB archived:** The KuzuDB project was archived October 2025. Version 0.11.3 is the final release. It works, has Python wheels, and is the same engine GitNexus uses. If it becomes a problem, RyuGraph (community fork) is a drop-in replacement. The schema and Cypher queries will be identical.

---

## File Structure

### New files to create:

```
Code_Organism/
├── graph/
│   ├── __init__.py              # Package init
│   ├── store.py                 # KuzuDB adapter — open/close/load/query
│   ├── schema.py                # Table definitions (nodes, edges, communities, processes)
│   └── search.py                # BM25 text search via KuzuDB FTS
├── analysis/
│   ├── __init__.py              # Package init
│   ├── communities.py           # Leiden community detection via igraph
│   ├── processes.py             # Execution flow detection (BFS from entry points)
│   └── impact.py                # Blast radius / impact analysis
├── parser/
│   ├── tree_sitter_parser.py    # Multi-language parser using tree-sitter
│   └── dispatcher.py            # Routes files to ast_walker (Python) or tree-sitter (others)
├── tests/
│   ├── __init__.py
│   ├── conftest.py              # Shared fixtures (sample code, temp dirs)
│   ├── test_json_cli.py         # Phase 1 tests
│   ├── test_graph_store.py      # Phase 2 tests
│   ├── test_graph_schema.py     # Phase 2 tests
│   ├── test_tree_sitter.py      # Phase 3 tests
│   ├── test_dispatcher.py       # Phase 3 tests
│   ├── test_communities.py      # Phase 4 tests
│   ├── test_processes.py        # Phase 4 tests
│   ├── test_impact.py           # Phase 5 tests
│   └── test_search.py           # Phase 5 tests
```

### Existing files to modify:

```
Code_Organism/
├── cli.py                       # Add --output json, new subcommands (query, impact, communities)
├── pyproject.toml               # Add dependencies (kuzu, tree-sitter, igraph)
├── __init__.py                  # Export new modules
├── model/organism.py            # Add save_to_graph() / load_from_graph() methods
├── parser/ast_walker.py         # No changes (keep as-is, it's the Python-specific parser)
```

---

## Chunk 1: Foundation — JSON CLI + Test Infrastructure

### Task 1: Test infrastructure

**Files:**
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add pytest to dev dependencies and install the package**

```toml
[project.optional-dependencies]
dev = ["pytest>=8.0"]
```

Run: `cd D:/lost_marbles/Code_Organism && pip install -e ".[dev]"`

This must happen before any tests — both subprocess tests (`python -m Code_Organism`) and direct import tests (`from Code_Organism.graph.store import ...`) require the package to be installed.

- [ ] **Step 2: Create tests/__init__.py**

Empty file.

- [ ] **Step 3: Create tests/conftest.py with shared fixtures**

```python
"""Shared test fixtures for Code_Organism tests."""
import tempfile
import shutil
from pathlib import Path

import pytest


@pytest.fixture
def tmp_dir(tmp_path):
    """Alias for pytest's built-in tmp_path fixture."""
    return tmp_path


@pytest.fixture
def sample_python_file(tmp_dir):
    """A simple Python file for parsing tests."""
    p = tmp_dir / "sample.py"
    p.write_text('''\
"""Sample module for testing."""

import os
from pathlib import Path


TIMEOUT = 30


class FileProcessor:
    """Processes files."""

    def __init__(self, root: Path):
        self.root = root
        self._cache: dict = {}

    def process(self, filename: str) -> dict:
        """Process a single file."""
        path = self.root / filename
        if not path.exists():
            raise FileNotFoundError(filename)
        content = path.read_text()
        self._cache[filename] = content
        return {"name": filename, "size": len(content)}

    @property
    def cached_count(self) -> int:
        return len(self._cache)


def helper(x: int, y: int) -> int:
    """Add two numbers."""
    if x < 0:
        x = 0
    return x + y
''')
    return p


@pytest.fixture
def sample_js_file(tmp_dir):
    """A simple JavaScript file for tree-sitter tests."""
    p = tmp_dir / "sample.js"
    p.write_text('''\
import { readFile } from 'fs/promises';

const TIMEOUT = 30;

class FileProcessor {
    constructor(root) {
        this.root = root;
        this._cache = {};
    }

    async process(filename) {
        const content = await readFile(`${this.root}/${filename}`, 'utf8');
        this._cache[filename] = content;
        return { name: filename, size: content.length };
    }

    get cachedCount() {
        return Object.keys(this._cache).length;
    }
}

function helper(x, y) {
    if (x < 0) x = 0;
    return x + y;
}

export { FileProcessor, helper };
''')
    return p


@pytest.fixture
def sample_project(tmp_dir, sample_python_file):
    """A small multi-file Python project."""
    # Already has sample.py from sample_python_file
    (tmp_dir / "utils.py").write_text('''\
"""Utility functions."""

def validate(value: str) -> bool:
    return len(value) > 0

def format_output(data: dict) -> str:
    return str(data)
''')
    (tmp_dir / "main.py").write_text('''\
"""Entry point."""
from sample import FileProcessor, helper
from utils import validate, format_output

def main():
    proc = FileProcessor(".")
    result = proc.process("test.txt")
    if validate(result["name"]):
        print(format_output(result))
    total = helper(1, 2)
    return total
''')
    return tmp_dir
```

- [ ] **Step 4: Verify pytest runs (no tests yet, should report 0)**

Run: `cd D:/lost_marbles/Code_Organism && python -m pytest tests/ -v`
Expected: `no tests ran` or `0 passed`

- [ ] **Step 5: Commit**

```bash
git add tests/ pyproject.toml
git commit -m "feat: add test infrastructure with shared fixtures"
```

---

### Task 2: JSON output for existing CLI

**Files:**
- Create: `tests/test_json_cli.py`
- Modify: `cli.py`

- [ ] **Step 1: Write failing tests for JSON output**

```python
"""Tests for JSON CLI output mode."""
import json
import subprocess
import sys
from pathlib import Path

import pytest


def run_cli(*args, cwd=None):
    """Run Code_Organism CLI and return stdout, stderr, returncode."""
    result = subprocess.run(
        [sys.executable, "-m", "Code_Organism", *args],
        capture_output=True, text=True, cwd=cwd, timeout=30,
    )
    return result.stdout, result.stderr, result.returncode


class TestJsonOutput:
    def test_analyze_json_single_file(self, sample_python_file):
        stdout, stderr, rc = run_cli(
            str(sample_python_file), "--stats", "--output", "json"
        )
        assert rc == 0, f"CLI failed: {stderr}"
        data = json.loads(stdout)
        assert "nodes" in data
        assert "edges" in data
        assert "stats" in data
        assert data["stats"]["total_functions"] > 0

    def test_analyze_json_directory(self, sample_project):
        stdout, stderr, rc = run_cli(
            str(sample_project), "--stats", "--output", "json"
        )
        assert rc == 0, f"CLI failed: {stderr}"
        data = json.loads(stdout)
        assert data["stats"]["total_modules"] >= 2

    def test_health_json(self, sample_python_file):
        stdout, stderr, rc = run_cli(
            str(sample_python_file), "--complexity", "--output", "json"
        )
        assert rc == 0, f"CLI failed: {stderr}"
        data = json.loads(stdout)
        assert "complexity" in data
        for entry in data["complexity"]:
            assert "name" in entry
            assert "cyclomatic" in entry
            assert "cognitive" in entry

    def test_malware_json(self, sample_python_file):
        stdout, stderr, rc = run_cli(
            str(sample_python_file), "--malware-scan", "--output", "json"
        )
        assert rc == 0, f"CLI failed: {stderr}"
        data = json.loads(stdout)
        assert "overall_risk" in data  # Field name matches MalwareAnalysisResult.overall_risk
        assert "markers" in data

    def test_json_output_is_valid_json(self, sample_python_file):
        """Ensure no stray print statements corrupt JSON output."""
        stdout, _, rc = run_cli(
            str(sample_python_file), "--stats", "--output", "json"
        )
        assert rc == 0
        # Should parse cleanly — no extra text before/after
        data = json.loads(stdout.strip())
        assert isinstance(data, dict)

    def test_default_output_unchanged(self, sample_python_file):
        """Without --output json, behavior should not change."""
        stdout, _, rc = run_cli(str(sample_python_file), "--stats")
        assert rc == 0
        # Should NOT be JSON (should be human-readable text)
        with pytest.raises(json.JSONDecodeError):
            json.loads(stdout)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:/lost_marbles/Code_Organism && python -m pytest tests/test_json_cli.py -v`
Expected: FAIL — `--output` flag not recognized

- [ ] **Step 3: Add --output json flag to cli.py**

In `cli.py`, add the `--output` argument to the argument parser:

```python
parser.add_argument("--output", choices=["text", "json"], default="text",
                    help="Output format (default: text)")
```

Then modify each output path (`--stats`, `--complexity`, `--malware-scan`) to check `args.output == "json"` and emit `json.dumps(data)` to stdout instead of formatted text. When `--output json`, suppress all other print statements (browser launch messages, progress output) by redirecting them to stderr.

Key implementation details:
- `--stats --output json`: Build organism normally, then output `{"nodes": [...], "edges": [...], "stats": organism.stats.__dict__}` where nodes and edges are serialized via `to_dict()`.
- `--complexity --output json`: Run ComplexityAnalyzer, output `{"complexity": [{"name": ..., "cyclomatic": ..., "cognitive": ..., "halstead": ..., "maintainability": ...}, ...]}`.
- `--malware-scan --output json`: Run MalwareAnalyzer, output `{"risk_score": float, "is_likely_malware": bool, "markers": [{"pattern": ..., "severity": ..., "confidence": ..., "location": ...}, ...]}`.
- All non-JSON output (progress messages, server URLs) goes to stderr when `--output json`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd D:/lost_marbles/Code_Organism && python -m pytest tests/test_json_cli.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add cli.py tests/test_json_cli.py
git commit -m "feat: add --output json flag to CLI for machine-readable output"
```

---

### Task 3: New CLI subcommands (analyze, health, query)

**Files:**
- Modify: `cli.py`
- Modify: `tests/test_json_cli.py`

- [ ] **Step 1: Write failing tests for new subcommands**

Add to `tests/test_json_cli.py`:

```python
class TestSubcommands:
    def test_analyze_subcommand(self, sample_project):
        stdout, stderr, rc = run_cli("analyze", str(sample_project), "--output", "json")
        assert rc == 0, f"CLI failed: {stderr}"
        data = json.loads(stdout)
        assert "nodes" in data
        assert "stats" in data

    def test_health_subcommand(self, sample_python_file):
        stdout, stderr, rc = run_cli("health", str(sample_python_file), "--output", "json")
        assert rc == 0, f"CLI failed: {stderr}"
        data = json.loads(stdout)
        assert "health_summary" in data
        assert "nodes" in data
        for node in data["nodes"]:
            assert "health_status" in node
            assert "health_score" in node

    def test_version(self):
        stdout, _, rc = run_cli("--version")
        assert rc == 0
        assert "code-organism" in stdout.lower() or "code_organism" in stdout.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:/lost_marbles/Code_Organism && python -m pytest tests/test_json_cli.py::TestSubcommands -v`
Expected: FAIL — subcommands not recognized

- [ ] **Step 3: Refactor cli.py to use subcommands**

Restructure `cli.py` to use `argparse` subparsers:

The approach: detect whether the first argument is a known subcommand or a path. If it's a path (or looks like a flag), delegate to the existing `main()` logic renamed to `_legacy_main()`.

```python
SUBCOMMANDS = {"analyze", "health", "index", "impact", "communities"}

def main():
    # Check if first arg is a subcommand or a legacy invocation
    if len(sys.argv) > 1 and sys.argv[1] not in SUBCOMMANDS and not sys.argv[1].startswith("--version"):
        # Legacy mode: first arg is a file/directory path
        return _legacy_main()

    parser = argparse.ArgumentParser(prog="code-organism", description="Code_Organism analysis engine")
    parser.add_argument("--version", action="version", version="code-organism 2.0.0")
    subparsers = parser.add_subparsers(dest="command")

    # analyze — parse and build organism
    p_analyze = subparsers.add_parser("analyze", help="Analyze a codebase")
    p_analyze.add_argument("path", help="File or directory to analyze")
    p_analyze.add_argument("--output", choices=["text", "json"], default="text")
    p_analyze.add_argument("--pattern", default="**/*.py")

    # health — health diagnostics
    p_health = subparsers.add_parser("health", help="Health diagnostics")
    p_health.add_argument("path", help="File or directory")
    p_health.add_argument("--output", choices=["text", "json"], default="text")

    args = parser.parse_args()
    if args.command == "analyze":
        cmd_analyze(args)
    elif args.command == "health":
        cmd_health(args)
    else:
        parser.print_help()

def _legacy_main():
    """The existing main() function, renamed. Handles all legacy flags
    (--stats, --export, --playback, --malware-scan, --complexity, --instanced,
    --solar, --port, --pattern, --max-level, --output).
    Preserves full backward compatibility."""
    # ... move the entire existing main() body here unchanged,
    # but add --output argument to the existing argparse parser
```

This avoids the subparser conflict: legacy args are never registered on the subcommand parser because legacy invocations are detected before argparse runs.

- [ ] **Step 4: Run tests to verify all pass (new + old)**

Run: `cd D:/lost_marbles/Code_Organism && python -m pytest tests/test_json_cli.py -v`
Expected: All tests PASS (both TestJsonOutput and TestSubcommands)

- [ ] **Step 5: Commit**

```bash
git add cli.py tests/test_json_cli.py
git commit -m "feat: add analyze/health subcommands with backward-compatible legacy mode"
```

---

## Chunk 2: KuzuDB Persistent Graph Storage

### Task 4: Install dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add kuzu dependency to pyproject.toml**

```toml
[project]
dependencies = [
    "kuzu==0.11.3",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]
```

- [ ] **Step 2: Install**

Run: `cd D:/lost_marbles/Code_Organism && pip install -e ".[dev]"`
Expected: kuzu installs successfully

- [ ] **Step 3: Verify kuzu works**

Run: `python -c "import kuzu; print(kuzu.__version__)"`
Expected: `0.11.3`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add kuzu for persistent graph storage"
```

---

### Task 5: Graph schema definition

**Files:**
- Create: `graph/__init__.py`
- Create: `graph/schema.py`
- Create: `tests/test_graph_schema.py`

- [ ] **Step 1: Write failing tests for schema creation**

```python
"""Tests for graph schema definition."""
import kuzu
import pytest


class TestGraphSchema:
    def test_create_schema(self, tmp_dir):
        from Code_Organism.graph.schema import create_schema

        db = kuzu.Database(str(tmp_dir / "test.db"))
        conn = kuzu.Connection(db)
        create_schema(conn)

        # Verify node tables exist — show_tables() returns (id, name, type, ...)
        result = conn.execute("CALL show_tables() RETURN name")
        tables = []
        while result.has_next():
            tables.append(result.get_next()[0])

        assert "Module" in tables
        assert "Class" in tables
        assert "Function" in tables
        assert "Method" in tables

    def test_schema_has_health_columns(self, tmp_dir):
        from Code_Organism.graph.schema import create_schema

        db = kuzu.Database(str(tmp_dir / "test.db"))
        conn = kuzu.Connection(db)
        create_schema(conn)

        # Insert a function with health data
        conn.execute("""
            CREATE (f:Function {
                uid: 'test_func_1',
                name: 'my_func',
                filePath: 'test.py',
                startLine: 1,
                endLine: 10,
                health_status: 'HEALTHY',
                health_score: 0.95,
                cyclomatic_complexity: 3,
                cognitive_complexity: 2,
                maintainability_index: 85.0,
                halstead_difficulty: 120.5,
                lines_of_code: 10
            })
        """)

        result = conn.execute("MATCH (f:Function {uid: 'test_func_1'}) RETURN f.health_status, f.health_score")
        row = result.get_next()
        assert row[0] == "HEALTHY"
        assert row[1] == 0.95

    def test_schema_is_idempotent(self, tmp_dir):
        """Creating schema twice should not error."""
        from Code_Organism.graph.schema import create_schema

        db = kuzu.Database(str(tmp_dir / "test.db"))
        conn = kuzu.Connection(db)
        create_schema(conn)
        create_schema(conn)  # Should not raise
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:/lost_marbles/Code_Organism && python -m pytest tests/test_graph_schema.py -v`
Expected: FAIL — `graph` module not found

- [ ] **Step 3: Create graph/__init__.py**

Empty file.

- [ ] **Step 4: Create graph/schema.py**

```python
"""KuzuDB schema for Code_Organism graph.

Defines node tables (Module, Class, Function, Method, Variable, External)
and a single CodeRelation edge table. Extends GitNexus's schema with
health diagnostics columns (health_status, health_score, complexity metrics).
"""
import kuzu

# Columns shared by all code node types
_COMMON_COLUMNS = """
    uid STRING,
    name STRING,
    filePath STRING,
    startLine INT64,
    endLine INT64,
    docstring STRING,
    source_code STRING,
    health_status STRING,
    health_score DOUBLE,
    cyclomatic_complexity INT64,
    cognitive_complexity INT64,
    maintainability_index DOUBLE,
    halstead_difficulty DOUBLE,
    lines_of_code INT64,
    PRIMARY KEY (uid)
"""

# Node tables — one per major code element type
NODE_TABLES = {
    "Module":   _COMMON_COLUMNS,
    "Package":  _COMMON_COLUMNS,
    "Class":    _COMMON_COLUMNS + ", bases STRING",  # comma-separated base classes
    "Function": _COMMON_COLUMNS + ", signature STRING, is_async BOOLEAN",
    "Method":   _COMMON_COLUMNS + ", signature STRING, is_async BOOLEAN, is_property BOOLEAN",
    "Variable": "uid STRING, name STRING, filePath STRING, startLine INT64, endLine INT64, PRIMARY KEY (uid)",
    "External": "uid STRING, name STRING, kind STRING, PRIMARY KEY (uid)",
    "Community": "uid STRING, name STRING, keywords STRING, cohesion DOUBLE, symbolCount INT64, PRIMARY KEY (uid)",
    "Process":  "uid STRING, name STRING, entryPointId STRING, stepCount INT64, processType STRING, PRIMARY KEY (uid)",
}

# Single edge table for all relationships (no GROUP keyword — deprecated in kuzu 0.8+)
# Includes all FROM/TO combinations that real codebases produce
EDGE_TABLE_DDL = """
CREATE REL TABLE CodeRelation (
    FROM Module TO Module,
    FROM Module TO Class,
    FROM Module TO Function,
    FROM Module TO Method,
    FROM Module TO Variable,
    FROM Module TO External,
    FROM Package TO Module,
    FROM Package TO Package,
    FROM Class TO Class,
    FROM Class TO Method,
    FROM Class TO Function,
    FROM Class TO Variable,
    FROM Function TO Function,
    FROM Function TO Class,
    FROM Function TO Method,
    FROM Function TO Variable,
    FROM Function TO External,
    FROM Method TO Function,
    FROM Method TO Method,
    FROM Method TO Class,
    FROM Method TO Variable,
    FROM Method TO External,
    type STRING,
    weight DOUBLE DEFAULT 1.0,
    confidence DOUBLE DEFAULT 1.0
)
"""


def create_schema(conn: kuzu.Connection) -> None:
    """Create all node and edge tables. Idempotent — skips existing tables."""
    existing = set()
    try:
        result = conn.execute("CALL show_tables() RETURN name")
        while result.has_next():
            existing.add(result.get_next()[0])
    except Exception:
        pass

    for table_name, columns in NODE_TABLES.items():
        if table_name not in existing:
            conn.execute(f"CREATE NODE TABLE {table_name} ({columns})")

    if "CodeRelation" not in existing:
        conn.execute(EDGE_TABLE_DDL)
```

Note: The exact DDL for the REL TABLE GROUP may need adjustment based on KuzuDB 0.11.3's syntax. The implementation should test against the actual API and adapt. The key point is: one edge table with a `type` column, not separate tables per relationship.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd D:/lost_marbles/Code_Organism && python -m pytest tests/test_graph_schema.py -v`
Expected: All 3 tests PASS

- [ ] **Step 6: Commit**

```bash
git add graph/ tests/test_graph_schema.py
git commit -m "feat: add KuzuDB graph schema with health diagnostic columns"
```

---

### Task 6: Graph store (open/save/load)

**Files:**
- Create: `graph/store.py`
- Create: `tests/test_graph_store.py`

- [ ] **Step 1: Write failing tests for graph store**

```python
"""Tests for graph store — persisting organisms to KuzuDB."""
import pytest


class TestGraphStore:
    def test_open_creates_db(self, tmp_dir):
        from Code_Organism.graph.store import GraphStore

        store = GraphStore(tmp_dir / ".code_organism")
        store.open()
        assert (tmp_dir / ".code_organism").exists()
        store.close()

    def test_save_organism(self, tmp_dir, sample_python_file):
        from Code_Organism import Organism
        from Code_Organism.graph.store import GraphStore

        org = Organism.from_file(str(sample_python_file))
        org.analyze_health()

        store = GraphStore(tmp_dir / ".code_organism")
        store.open()
        store.save(org)

        # Verify data persisted
        count = store.count_nodes()
        assert count > 0
        store.close()

    def test_roundtrip_health(self, tmp_dir, sample_python_file):
        from Code_Organism import Organism
        from Code_Organism.graph.store import GraphStore

        org = Organism.from_file(str(sample_python_file))
        org.analyze_health()

        store = GraphStore(tmp_dir / ".code_organism")
        store.open()
        store.save(org)

        # Query health data back
        results = store.query("MATCH (f:Function) RETURN f.name, f.health_status, f.health_score")
        assert len(results) > 0
        for row in results:
            assert row["health_status"] in ("HEALTHY", "STRESSED", "INFLAMED", "NECROTIC", "CANCEROUS")
            assert 0.0 <= row["health_score"] <= 1.0
        store.close()

    def test_context_manager(self, tmp_dir):
        from Code_Organism.graph.store import GraphStore

        with GraphStore(tmp_dir / ".code_organism") as store:
            assert store._conn is not None
        # Should be closed after context exit

    def test_save_preserves_edges(self, tmp_dir, sample_project):
        from Code_Organism import Organism
        from Code_Organism.graph.store import GraphStore

        org = Organism.from_directory(str(sample_project))

        with GraphStore(tmp_dir / ".code_organism") as store:
            store.save(org)
            edges = store.query(
                "MATCH ()-[r:CodeRelation]->() RETURN r.type, count(*) AS cnt"
            )
            assert len(edges) > 0  # Should have import/call edges
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:/lost_marbles/Code_Organism && python -m pytest tests/test_graph_store.py -v`
Expected: FAIL — `graph.store` not found

- [ ] **Step 3: Implement graph/store.py**

```python
"""Persistent graph storage via KuzuDB.

Provides GraphStore — open a database, save an Organism's nodes/edges,
query with Cypher, and get results back as dicts.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import kuzu

from Code_Organism.graph.schema import create_schema
from Code_Organism.model.nodes import NodeType, HealthStatus


class GraphStore:
    """KuzuDB-backed persistent storage for Code_Organism graphs."""

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        self._db: Optional[kuzu.Database] = None
        self._conn: Optional[kuzu.Connection] = None

    def open(self) -> None:
        self.db_path.mkdir(parents=True, exist_ok=True)
        self._db = kuzu.Database(str(self.db_path))
        self._conn = kuzu.Connection(self._db)
        create_schema(self._conn)

    def close(self) -> None:
        self._conn = None
        self._db = None

    def __enter__(self) -> GraphStore:
        self.open()
        return self

    def __exit__(self, *args) -> None:
        self.close()

    def save(self, organism) -> None:
        """Persist an Organism's nodes and edges to the graph."""
        # Clear existing data
        self._clear()

        # Map NodeType to table name
        type_map = {
            NodeType.MODULE: "Module",
            NodeType.PACKAGE: "Package",
            NodeType.CLASS: "Class",
            NodeType.FUNCTION: "Function",
            NodeType.METHOD: "Method",
            NodeType.VARIABLE: "Variable",
            NodeType.PARAMETER: "Variable",
            NodeType.ATTRIBUTE: "Variable",
            NodeType.EXTERNAL_MODULE: "External",
            NodeType.BUILTIN: "External",
        }

        # Insert nodes
        for node in organism.nodes.values():
            table = type_map.get(node.node_type)
            if table is None:
                continue
            self._insert_node(table, node)

        # Insert edges
        for edge in organism.edges.values():
            self._insert_edge(edge, organism)

    def _insert_node(self, table: str, node) -> None:
        """Insert a single node into the appropriate table."""
        metrics = node.metrics
        health_score = metrics.health_score() if metrics else 0.0
        health_status = node.health.value if node.health else "UNKNOWN"

        if table in ("Module", "Package", "Class", "Function", "Method"):
            params = {
                "uid": node.id,
                "name": node.name,
                "filePath": str(node.position.file) if node.position and hasattr(node.position, 'file') else "",
                "startLine": node.position.line if node.position else 0,
                "endLine": node.position.end_line if node.position and node.position.end_line is not None else 0,
                "docstring": node.docstring or "",
                "source_code": (node.source_code or "")[:2000],  # Truncate large sources
                "health_status": health_status,
                "health_score": health_score,
                "cyclomatic_complexity": metrics.cyclomatic_complexity if metrics else 0,
                "cognitive_complexity": metrics.cognitive_complexity if metrics else 0,
                "maintainability_index": metrics.maintainability_index if metrics else 0.0,
                "halstead_difficulty": metrics.halstead_difficulty if metrics and metrics.halstead_difficulty is not None else 0.0,
                "lines_of_code": metrics.lines_of_code if metrics else 0,
            }
            cols = ", ".join(f"{k}: ${k}" for k in params)
            self._conn.execute(f"CREATE (:{table} {{{cols}}})", parameters=params)

        elif table == "Variable":
            self._conn.execute(
                f"CREATE (:Variable {{uid: $uid, name: $name, filePath: $fp, startLine: $sl, endLine: $el}})",
                parameters={"uid": node.id, "name": node.name, "fp": "", "sl": 0, "el": 0},
            )

        elif table == "External":
            self._conn.execute(
                f"CREATE (:External {{uid: $uid, name: $name, kind: $kind}})",
                parameters={"uid": node.id, "name": node.name, "kind": node.node_type.value},
            )

    def _insert_edge(self, edge, organism) -> None:
        """Insert an edge as a CodeRelation."""
        src = organism.nodes.get(edge.source_id)
        tgt = organism.nodes.get(edge.target_id)
        if not src or not tgt:
            return

        # Determine table names for source and target
        type_map = {
            NodeType.MODULE: "Module", NodeType.PACKAGE: "Package",
            NodeType.CLASS: "Class", NodeType.FUNCTION: "Function",
            NodeType.METHOD: "Method", NodeType.VARIABLE: "Variable",
            NodeType.EXTERNAL_MODULE: "External", NodeType.BUILTIN: "External",
        }
        src_table = type_map.get(src.node_type)
        tgt_table = type_map.get(tgt.node_type)
        if not src_table or not tgt_table:
            return

        try:
            self._conn.execute(
                f"""
                MATCH (a:{src_table} {{uid: $src}}), (b:{tgt_table} {{uid: $tgt}})
                CREATE (a)-[:CodeRelation {{type: $type, weight: $weight}}]->(b)
                """,
                parameters={
                    "src": edge.source_id,
                    "tgt": edge.target_id,
                    "type": edge.edge_type.upper(),
                    "weight": edge.weight,
                },
            )
        except Exception as e:
            import sys
            print(f"Warning: skipped edge {edge.source_id}->{edge.target_id}: {e}", file=sys.stderr)

    def _clear(self) -> None:
        """Remove all data (not schema)."""
        for table in ("Community", "Process", "Module", "Package", "Class",
                      "Function", "Method", "Variable", "External"):
            try:
                self._conn.execute(f"MATCH (n:{table}) DETACH DELETE n")
            except Exception:
                pass

    def count_nodes(self) -> int:
        """Count total nodes across all tables."""
        total = 0
        for table in ("Module", "Package", "Class", "Function", "Method", "Variable", "External"):
            try:
                result = self._conn.execute(f"MATCH (n:{table}) RETURN count(n)")
                if result.has_next():
                    total += result.get_next()[0]
            except Exception:
                pass
        return total

    def query(self, cypher: str, parameters: dict | None = None) -> list[dict]:
        """Execute a Cypher query and return results as list of dicts."""
        result = self._conn.execute(cypher, parameters=parameters or {})
        columns = result.get_column_names()
        rows = []
        while result.has_next():
            row = result.get_next()
            rows.append(dict(zip(columns, row)))
        return rows
```

Note: The exact Cypher parameter syntax and `create_schema` idempotency behavior depend on KuzuDB 0.11.3's API. The implementation should be adapted during development based on actual API behavior. The key contract is: `GraphStore.save(organism)` persists all nodes with health data, and `GraphStore.query(cypher)` returns results as dicts.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd D:/lost_marbles/Code_Organism && python -m pytest tests/test_graph_store.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add graph/store.py tests/test_graph_store.py
git commit -m "feat: add KuzuDB graph store with organism persistence and health data"
```

---

### Task 7: CLI `index` subcommand (persist to graph)

**Files:**
- Modify: `cli.py`
- Modify: `tests/test_json_cli.py`

- [ ] **Step 1: Write failing test for index subcommand**

Add to `tests/test_json_cli.py`:

```python
class TestIndexSubcommand:
    def test_index_creates_db(self, sample_project, tmp_dir):
        db_path = tmp_dir / ".code_organism"
        stdout, stderr, rc = run_cli(
            "index", str(sample_project), "--db", str(db_path), "--output", "json"
        )
        assert rc == 0, f"CLI failed: {stderr}"
        assert db_path.exists()
        data = json.loads(stdout)
        assert data["nodes_indexed"] > 0
        assert data["edges_indexed"] > 0

    def test_index_stores_health(self, sample_project, tmp_dir):
        db_path = tmp_dir / ".code_organism"
        run_cli("index", str(sample_project), "--db", str(db_path))

        # Query the db directly
        import kuzu
        db = kuzu.Database(str(db_path))
        conn = kuzu.Connection(db)
        result = conn.execute("MATCH (f:Function) RETURN f.name, f.health_status")
        rows = []
        while result.has_next():
            rows.append(result.get_next())
        assert len(rows) > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd D:/lost_marbles/Code_Organism && python -m pytest tests/test_json_cli.py::TestIndexSubcommand -v`
Expected: FAIL — `index` subcommand not recognized

- [ ] **Step 3: Add `index` subcommand to cli.py**

```python
# In the subparser setup:
p_index = subparsers.add_parser("index", help="Analyze and persist to graph database")
p_index.add_argument("path", help="File or directory to analyze")
p_index.add_argument("--db", default=".code_organism", help="Database path (default: .code_organism in target dir)")
p_index.add_argument("--output", choices=["text", "json"], default="text")
p_index.add_argument("--pattern", default="**/*.py")

# Handler:
def cmd_index(args):
    from Code_Organism.graph.store import GraphStore

    path = Path(args.path)
    if path.is_file():
        org = Organism.from_file(str(path))
    else:
        org = Organism.from_directory(str(path), pattern=args.pattern)

    org.analyze_health()

    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = (path if path.is_dir() else path.parent) / args.db

    with GraphStore(db_path) as store:
        store.save(org)
        node_count = store.count_nodes()

    edge_count = len(org.edges)
    if args.output == "json":
        import json
        print(json.dumps({
            "nodes_indexed": node_count,
            "edges_indexed": edge_count,
            "db_path": str(db_path),
            "stats": {k: v for k, v in org.stats.__dict__.items() if not k.startswith("_")},
        }))
    else:
        print(f"Indexed {node_count} nodes, {edge_count} edges → {db_path}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd D:/lost_marbles/Code_Organism && python -m pytest tests/test_json_cli.py::TestIndexSubcommand -v`
Expected: All 2 tests PASS

- [ ] **Step 5: Commit**

```bash
git add cli.py tests/test_json_cli.py
git commit -m "feat: add 'index' subcommand to persist organisms to KuzuDB"
```

---

### Task 7b: Export new modules from __init__.py

**Files:**
- Modify: `__init__.py`

- [ ] **Step 1: Add graph and analysis exports**

Add to `__init__.py`:

```python
from .graph.store import GraphStore
from .analysis.communities import detect_communities
from .analysis.processes import detect_processes
from .analysis.impact import analyze_impact
```

- [ ] **Step 2: Commit**

```bash
git add __init__.py
git commit -m "feat: export GraphStore and analysis modules from package root"
```

---

## Chunk 3: Multi-Language Parsing via tree-sitter

### Task 8: Install tree-sitter dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add tree-sitter dependencies**

```toml
[project]
dependencies = [
    "kuzu==0.11.3",
    "tree-sitter>=0.25.0",
    "tree-sitter-python>=0.25.0",
    "tree-sitter-javascript>=0.25.0",
    "tree-sitter-typescript>=0.23.0",
    "tree-sitter-java>=0.23.0",
    "tree-sitter-go>=0.25.0",
    "tree-sitter-rust>=0.24.0",
    "tree-sitter-c>=0.24.0",
    "tree-sitter-cpp>=0.23.0",
]
```

- [ ] **Step 2: Install**

Run: `cd D:/lost_marbles/Code_Organism && pip install -e ".[dev]"`

- [ ] **Step 3: Verify tree-sitter works**

Run: `python -c "import tree_sitter; import tree_sitter_python; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add tree-sitter with 8 language grammars"
```

---

### Task 9: Tree-sitter parser

**Files:**
- Create: `parser/tree_sitter_parser.py`
- Create: `tests/test_tree_sitter.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for tree-sitter multi-language parser."""
import pytest


class TestTreeSitterParser:
    def test_parse_javascript(self, sample_js_file):
        from Code_Organism.parser.tree_sitter_parser import TreeSitterParser

        parser = TreeSitterParser()
        nodes, edges = parser.parse_file(str(sample_js_file))

        names = {n.name for n in nodes}
        assert "FileProcessor" in names   # class
        assert "helper" in names           # function
        assert "process" in names          # method

    def test_parse_returns_organism_nodes(self, sample_js_file):
        from Code_Organism.parser.tree_sitter_parser import TreeSitterParser
        from Code_Organism.model.nodes import OrganismNode, NodeType

        parser = TreeSitterParser()
        nodes, edges = parser.parse_file(str(sample_js_file))

        for node in nodes:
            assert isinstance(node, OrganismNode)
            assert node.id  # Has an ID
            assert node.name  # Has a name
            assert node.node_type in NodeType  # Valid type

    def test_detects_calls(self, tmp_dir):
        from Code_Organism.parser.tree_sitter_parser import TreeSitterParser

        src = tmp_dir / "caller.js"
        src.write_text('function foo() { bar(); baz(1, 2); }\nfunction bar() {}\nfunction baz(a, b) {}')

        parser = TreeSitterParser()
        nodes, edges = parser.parse_file(str(src))

        call_edges = [e for e in edges if e.edge_type == "call"]
        assert len(call_edges) >= 2  # foo->bar, foo->baz

    def test_unsupported_language_returns_empty(self, tmp_dir):
        from Code_Organism.parser.tree_sitter_parser import TreeSitterParser

        src = tmp_dir / "data.csv"
        src.write_text("a,b,c\n1,2,3")

        parser = TreeSitterParser()
        nodes, edges = parser.parse_file(str(src))
        assert nodes == []
        assert edges == []

    def test_parse_rust(self, tmp_dir):
        from Code_Organism.parser.tree_sitter_parser import TreeSitterParser

        src = tmp_dir / "lib.rs"
        src.write_text('''\
struct Config {
    timeout: u64,
    retries: i32,
}

impl Config {
    fn new() -> Self {
        Config { timeout: 30, retries: 3 }
    }
}

fn process(cfg: &Config) -> bool {
    cfg.timeout > 0
}
''')
        parser = TreeSitterParser()
        nodes, edges = parser.parse_file(str(src))
        names = {n.name for n in nodes}
        assert "Config" in names
        assert "new" in names or "Config::new" in names
        assert "process" in names
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:/lost_marbles/Code_Organism && python -m pytest tests/test_tree_sitter.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement parser/tree_sitter_parser.py**

The parser should:
1. Detect language from file extension
2. Load the appropriate tree-sitter grammar
3. Parse the file into a tree-sitter AST
4. Walk the AST extracting functions, classes, methods, structs, enums, imports, calls
5. Return `(list[OrganismNode], list[Edge])` — the same format as `ast_walker.py`

Language detection map:
```python
LANGUAGE_MAP = {
    ".py": ("python", "tree_sitter_python"),
    ".js": ("javascript", "tree_sitter_javascript"),
    ".jsx": ("javascript", "tree_sitter_javascript"),
    ".ts": ("typescript", "tree_sitter_typescript"),
    ".tsx": ("typescript", "tree_sitter_typescript"),
    ".java": ("java", "tree_sitter_java"),
    ".go": ("go", "tree_sitter_go"),
    ".rs": ("rust", "tree_sitter_rust"),
    ".c": ("c", "tree_sitter_c"),
    ".h": ("c", "tree_sitter_c"),
    ".cpp": ("cpp", "tree_sitter_cpp"),
    ".cc": ("cpp", "tree_sitter_cpp"),
    ".hpp": ("cpp", "tree_sitter_cpp"),
}
```

For each language, define tree-sitter query patterns that extract:
- Function/method declarations → `NodeType.FUNCTION` or `NodeType.METHOD`
- Class/struct/trait declarations → `NodeType.CLASS`
- Import statements → `NodeType.IMPORT` + import edges
- Call expressions → call edges

The key class:
```python
class TreeSitterParser:
    def __init__(self):
        self._parsers: dict[str, Parser] = {}  # Lazy-loaded per language

    def parse_file(self, filepath: str) -> tuple[list[OrganismNode], list[Edge]]:
        ext = Path(filepath).suffix
        if ext not in LANGUAGE_MAP:
            return [], []
        lang_name, module_name = LANGUAGE_MAP[ext]
        parser = self._get_parser(lang_name, module_name)
        source = Path(filepath).read_bytes()
        tree = parser.parse(source)
        return self._extract(tree, filepath, lang_name, source)
```

Implementation note: Start with function/class extraction only. Call/import resolution is secondary and can be added incrementally. The test expectations should match what's implemented.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd D:/lost_marbles/Code_Organism && python -m pytest tests/test_tree_sitter.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add parser/tree_sitter_parser.py tests/test_tree_sitter.py
git commit -m "feat: add tree-sitter parser supporting 8 languages"
```

---

### Task 10: Parser dispatcher

**Files:**
- Create: `parser/dispatcher.py`
- Create: `tests/test_dispatcher.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for parser dispatcher — routes files to correct parser."""
import pytest


class TestDispatcher:
    def test_python_uses_ast_walker(self, sample_python_file):
        from Code_Organism.parser.dispatcher import parse_file

        nodes, edges = parse_file(str(sample_python_file))
        # Should have richer Python-specific features from ast_walker
        class_nodes = [n for n in nodes if n.name == "FileProcessor"]
        assert len(class_nodes) == 1

    def test_javascript_uses_tree_sitter(self, sample_js_file):
        from Code_Organism.parser.dispatcher import parse_file

        nodes, edges = parse_file(str(sample_js_file))
        names = {n.name for n in nodes}
        assert "FileProcessor" in names

    def test_unknown_extension_returns_empty(self, tmp_dir):
        from Code_Organism.parser.dispatcher import parse_file

        f = tmp_dir / "data.xyz"
        f.write_text("not code")
        nodes, edges = parse_file(str(f))
        assert nodes == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:/lost_marbles/Code_Organism && python -m pytest tests/test_dispatcher.py -v`

- [ ] **Step 3: Implement parser/dispatcher.py**

```python
"""Routes files to the appropriate parser.

Python files → ast_walker (richer, native)
All other supported languages → tree_sitter_parser
Unsupported → empty result
"""
from __future__ import annotations

from pathlib import Path

from Code_Organism.model.nodes import OrganismNode, Edge


def parse_file(filepath: str) -> tuple[list[OrganismNode], list[Edge]]:
    """Parse a file using the best available parser for its language."""
    ext = Path(filepath).suffix.lower()

    if ext == ".py":
        from Code_Organism.parser.ast_walker import CodeAnatomist, WalkContext
        import ast

        source = Path(filepath).read_text(encoding="utf-8", errors="replace")
        try:
            tree = ast.parse(source, filename=filepath)
        except SyntaxError:
            return [], []

        ctx = WalkContext(filepath=filepath, source=source)
        anatomist = CodeAnatomist(ctx)
        anatomist.visit(tree)
        return anatomist.nodes, anatomist.edges

    # Try tree-sitter for other languages
    from Code_Organism.parser.tree_sitter_parser import TreeSitterParser, LANGUAGE_MAP
    if ext in LANGUAGE_MAP:
        parser = TreeSitterParser()
        return parser.parse_file(filepath)

    return [], []
```

- [ ] **Step 4: Run tests**

Run: `cd D:/lost_marbles/Code_Organism && python -m pytest tests/test_dispatcher.py -v`
Expected: All 3 PASS

- [ ] **Step 5: Update Organism.from_directory to use dispatcher**

In `model/organism.py`, modify `from_directory` to use `parser.dispatcher.parse_file` instead of directly calling `ast_walker`. This makes `Organism.from_directory` automatically handle mixed-language projects.

The pattern filter (`--pattern`) should default to a broader set when tree-sitter is available: `**/*.{py,js,ts,jsx,tsx,java,go,rs,c,cpp,h,hpp,cc}`.

- [ ] **Step 6: Run all tests**

Run: `cd D:/lost_marbles/Code_Organism && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add parser/dispatcher.py tests/test_dispatcher.py model/organism.py
git commit -m "feat: add parser dispatcher — Python via ast, all others via tree-sitter"
```

---

## Chunk 4: Community Detection + Process/Flow Tracing

### Task 11: Install igraph

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add igraph dependency**

```toml
dependencies = [
    "kuzu==0.11.3",
    "tree-sitter>=0.25.0",
    # ... tree-sitter grammars ...
    "igraph>=1.0.0",
]
```

- [ ] **Step 2: Install and verify**

Run: `pip install -e ".[dev]" && python -c "import igraph; print(igraph.__version__)"`

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "deps: add igraph for Leiden community detection"
```

---

### Task 12: Community detection

**Files:**
- Create: `analysis/__init__.py`
- Create: `analysis/communities.py`
- Create: `tests/test_communities.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for Leiden community detection."""
import pytest


class TestCommunityDetection:
    def test_detects_communities(self, sample_project):
        from Code_Organism import Organism
        from Code_Organism.analysis.communities import detect_communities

        org = Organism.from_directory(str(sample_project))
        communities = detect_communities(org)

        assert len(communities) >= 1
        for comm in communities:
            assert "id" in comm
            assert "name" in comm
            assert "members" in comm
            assert "cohesion" in comm
            assert len(comm["members"]) > 0

    def test_all_nodes_assigned(self, sample_project):
        from Code_Organism import Organism
        from Code_Organism.analysis.communities import detect_communities

        org = Organism.from_directory(str(sample_project))
        communities = detect_communities(org)

        assigned = set()
        for comm in communities:
            assigned.update(comm["members"])

        # Every function/class/method should be in a community
        code_nodes = {n.id for n in org.nodes.values()
                      if n.node_type.value in ("function", "class", "method")}
        # Allow some nodes to be unassigned (isolated), but most should be covered
        assert len(assigned & code_nodes) > 0

    def test_returns_empty_for_single_file(self, sample_python_file):
        from Code_Organism import Organism
        from Code_Organism.analysis.communities import detect_communities

        org = Organism.from_file(str(sample_python_file))
        communities = detect_communities(org)
        # Single file may produce 1 community or empty — should not crash
        assert isinstance(communities, list)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:/lost_marbles/Code_Organism && python -m pytest tests/test_communities.py -v`

- [ ] **Step 3: Implement analysis/communities.py**

```python
"""Leiden community detection using igraph.

Takes an Organism's call/import graph, builds an igraph.Graph,
runs community_leiden(), and returns community assignments with
auto-generated labels and cohesion scores.
"""
from __future__ import annotations

from collections import Counter

import igraph as ig

from Code_Organism.model.nodes import NodeType


# Node types that participate in community detection
_STRUCTURAL_TYPES = {NodeType.FUNCTION, NodeType.CLASS, NodeType.METHOD, NodeType.MODULE}

# Edge types used for clustering
_CLUSTER_EDGE_TYPES = {"call", "import", "reference"}


def detect_communities(organism, resolution: float = 1.0) -> list[dict]:
    """Detect functional communities in the organism's code graph.

    Returns list of dicts:
        {"id": str, "name": str, "members": [node_id, ...], "cohesion": float, "keywords": [str, ...]}
    """
    # Filter to structural nodes
    structural = {nid: node for nid, node in organism.nodes.items()
                  if node.node_type in _STRUCTURAL_TYPES}

    if len(structural) < 3:
        # Too few nodes for meaningful communities
        if structural:
            return [{
                "id": "community_0",
                "name": _generate_label(list(structural.values())),
                "members": list(structural.keys()),
                "cohesion": 1.0,
                "keywords": [n.name for n in structural.values()][:5],
            }]
        return []

    # Build igraph
    node_ids = list(structural.keys())
    id_to_idx = {nid: i for i, nid in enumerate(node_ids)}

    g = ig.Graph(n=len(node_ids), directed=False)

    for edge in organism.edges.values():
        if edge.edge_type not in _CLUSTER_EDGE_TYPES:
            continue
        src_idx = id_to_idx.get(edge.source_id)
        tgt_idx = id_to_idx.get(edge.target_id)
        if src_idx is not None and tgt_idx is not None and src_idx != tgt_idx:
            g.add_edge(src_idx, tgt_idx)

    # Run Leiden
    partition = g.community_leiden(
        objective_function="modularity",
        resolution=resolution,
        n_iterations=2,
    )

    # Build community list
    communities = []
    for comm_idx, member_indices in enumerate(partition):
        member_ids = [node_ids[i] for i in member_indices]
        member_nodes = [structural[mid] for mid in member_ids]

        # Cohesion: internal edges / possible edges
        subgraph = g.subgraph(member_indices)
        possible = len(member_indices) * (len(member_indices) - 1) / 2
        cohesion = subgraph.ecount() / possible if possible > 0 else 0.0

        communities.append({
            "id": f"community_{comm_idx}",
            "name": _generate_label(member_nodes),
            "members": member_ids,
            "cohesion": round(cohesion, 3),
            "keywords": _extract_keywords(member_nodes),
        })

    return communities


def _generate_label(nodes) -> str:
    """Auto-generate a community name from member names."""
    names = [n.name for n in nodes]
    # Use most common name prefix or module
    if not names:
        return "Unknown"
    # Simple heuristic: use the longest common prefix or most common word
    counter = Counter()
    for name in names:
        parts = name.replace("_", " ").split()
        counter.update(parts)

    top = counter.most_common(2)
    return "_".join(w for w, _ in top) if top else names[0]


def _extract_keywords(nodes, limit: int = 5) -> list[str]:
    """Extract keyword names from community members."""
    return [n.name for n in nodes[:limit]]
```

- [ ] **Step 4: Run tests**

Run: `cd D:/lost_marbles/Code_Organism && python -m pytest tests/test_communities.py -v`
Expected: All 3 PASS

- [ ] **Step 5: Commit**

```bash
git add analysis/ tests/test_communities.py
git commit -m "feat: add Leiden community detection via igraph"
```

---

### Task 13: Process/execution flow detection

**Files:**
- Create: `analysis/processes.py`
- Create: `tests/test_processes.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for execution flow detection."""
import pytest


class TestProcessDetection:
    def test_detects_flows(self, sample_project):
        from Code_Organism import Organism
        from Code_Organism.analysis.processes import detect_processes

        org = Organism.from_directory(str(sample_project))
        processes = detect_processes(org)

        assert len(processes) >= 1
        for proc in processes:
            assert "id" in proc
            assert "name" in proc
            assert "entry_point" in proc
            assert "steps" in proc
            assert len(proc["steps"]) >= 2  # Min 2 steps

    def test_steps_are_ordered(self, sample_project):
        from Code_Organism import Organism
        from Code_Organism.analysis.processes import detect_processes

        org = Organism.from_directory(str(sample_project))
        processes = detect_processes(org)

        for proc in processes:
            # Each step should reference a valid node
            for step in proc["steps"]:
                assert step["node_id"] in org.nodes

    def test_empty_organism(self):
        from Code_Organism import Organism
        from Code_Organism.analysis.processes import detect_processes

        org = Organism("empty")
        processes = detect_processes(org)
        assert processes == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:/lost_marbles/Code_Organism && python -m pytest tests/test_processes.py -v`

- [ ] **Step 3: Implement analysis/processes.py**

Port from GitNexus's `process-processor.js` (~400 LOC JS → ~200 LOC Python):

1. Find entry points: functions with no internal callers (score by call count, filter test files)
2. BFS from each entry point via call edges, max depth 10, max branch factor 4
3. Deduplicate: remove traces that are subsets of longer traces
4. Limit to 75 processes, prioritize longer traces
5. Auto-generate labels from step function names

```python
"""Execution flow detection — finds multi-step processes through the call graph.

Ported from GitNexus process-processor.js. Finds entry points (functions
with no internal callers), then BFS-traces execution flows through
call edges to produce ordered step lists.
"""
from __future__ import annotations

from collections import deque

from Code_Organism.model.nodes import NodeType

_CODE_TYPES = {NodeType.FUNCTION, NodeType.METHOD}
_MAX_PROCESSES = 75
_MIN_STEPS = 3
_MAX_DEPTH = 10
_MAX_BRANCH = 4


def detect_processes(organism) -> list[dict]:
    """Detect execution flows through the organism's call graph."""
    # Build call adjacency
    callees: dict[str, list[str]] = {}
    callers: dict[str, set[str]] = {}

    for edge in organism.edges.values():
        if edge.edge_type != "call":
            continue
        src, tgt = edge.source_id, edge.target_id
        if src in organism.nodes and tgt in organism.nodes:
            callees.setdefault(src, []).append(tgt)
            callers.setdefault(tgt, set()).add(src)

    # Find entry points: code nodes with no internal callers
    code_nodes = {nid for nid, n in organism.nodes.items() if n.node_type in _CODE_TYPES}
    entry_points = []
    for nid in code_nodes:
        internal_callers = callers.get(nid, set()) & code_nodes
        if not internal_callers and nid in callees:
            # Score by number of callees (prefer nodes that call many things)
            score = len(callees.get(nid, []))
            entry_points.append((nid, score))

    # Sort by score descending
    entry_points.sort(key=lambda x: -x[1])

    # BFS from each entry point
    raw_traces = []
    for entry_id, _ in entry_points:
        trace = _bfs_trace(entry_id, callees, code_nodes)
        if len(trace) >= _MIN_STEPS:
            raw_traces.append(trace)

    # Deduplicate: remove subset traces
    traces = _deduplicate(raw_traces)

    # Limit and format
    traces = traces[:_MAX_PROCESSES]

    processes = []
    for i, trace in enumerate(traces):
        entry_node = organism.nodes[trace[0]]
        steps = [{"step": j + 1, "node_id": nid, "name": organism.nodes[nid].name}
                 for j, nid in enumerate(trace)]
        processes.append({
            "id": f"process_{i}",
            "name": _generate_name(trace, organism),
            "entry_point": trace[0],
            "terminal": trace[-1],
            "steps": steps,
            "step_count": len(steps),
        })

    return processes


def _bfs_trace(start: str, callees: dict, code_nodes: set) -> list[str]:
    """BFS from start, collecting ordered call trace."""
    visited = set()
    trace = []
    queue = deque([(start, 0)])

    while queue:
        node_id, depth = queue.popleft()
        if node_id in visited or depth > _MAX_DEPTH:
            continue
        if node_id not in code_nodes:
            continue
        visited.add(node_id)
        trace.append(node_id)

        children = callees.get(node_id, [])[:_MAX_BRANCH]
        for child in children:
            if child not in visited:
                queue.append((child, depth + 1))

    return trace


def _deduplicate(traces: list[list[str]]) -> list[list[str]]:
    """Remove traces that are subsets of longer traces."""
    # Sort longest first
    traces.sort(key=len, reverse=True)
    result = []
    seen_sets = []

    for trace in traces:
        trace_set = set(trace)
        is_subset = any(trace_set <= s for s in seen_sets)
        if not is_subset:
            result.append(trace)
            seen_sets.append(trace_set)

    return result


def _generate_name(trace: list[str], organism) -> str:
    """Auto-generate a process name from the trace."""
    if not trace:
        return "Unknown"
    entry = organism.nodes[trace[0]].name
    terminal = organism.nodes[trace[-1]].name
    if entry == terminal:
        return entry
    return f"{entry}→{terminal}"
```

- [ ] **Step 4: Run tests**

Run: `cd D:/lost_marbles/Code_Organism && python -m pytest tests/test_processes.py -v`
Expected: All 3 PASS

- [ ] **Step 5: Commit**

```bash
git add analysis/processes.py tests/test_processes.py
git commit -m "feat: add execution flow detection (ported from GitNexus)"
```

---

## Chunk 5: Impact Analysis + Search + GitNexus Rewiring

### Task 14: Impact analysis

**Files:**
- Create: `analysis/impact.py`
- Create: `tests/test_impact.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for impact/blast radius analysis."""
import pytest


class TestImpactAnalysis:
    def test_upstream_impact(self, sample_project):
        from Code_Organism import Organism
        from Code_Organism.analysis.impact import analyze_impact

        org = Organism.from_directory(str(sample_project))

        # helper is called by main — main should be in upstream impact
        helper_nodes = org.find_nodes("helper")
        assert len(helper_nodes) > 0
        helper_id = helper_nodes[0].id

        impact = analyze_impact(org, helper_id, direction="upstream", max_depth=3)
        assert "depth_1" in impact
        assert isinstance(impact["depth_1"], list)

    def test_downstream_impact(self, sample_project):
        from Code_Organism import Organism
        from Code_Organism.analysis.impact import analyze_impact

        org = Organism.from_directory(str(sample_project))
        main_nodes = org.find_nodes("main")
        assert len(main_nodes) > 0

        impact = analyze_impact(org, main_nodes[0].id, direction="downstream", max_depth=2)
        assert "depth_1" in impact

    def test_nonexistent_node(self, sample_project):
        from Code_Organism import Organism
        from Code_Organism.analysis.impact import analyze_impact

        org = Organism.from_directory(str(sample_project))
        impact = analyze_impact(org, "nonexistent_id", direction="upstream")
        assert impact["depth_1"] == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd D:/lost_marbles/Code_Organism && python -m pytest tests/test_impact.py -v`

- [ ] **Step 3: Implement analysis/impact.py**

BFS traversal on the call/import graph in the specified direction:
- `upstream`: follow edges backward (who calls/imports this?)
- `downstream`: follow edges forward (what does this call/import?)
- Return results grouped by depth (d=1, d=2, d=3)
- Each result includes node name, file path, edge type, confidence

```python
"""Blast radius / impact analysis.

Given a target symbol, finds all symbols affected at depth 1, 2, 3
by traversing call/import edges upstream or downstream.
"""
from __future__ import annotations

from collections import deque


def analyze_impact(
    organism,
    target_id: str,
    direction: str = "upstream",
    max_depth: int = 3,
) -> dict:
    """Analyze the impact of changing a symbol.

    Args:
        organism: The Organism to analyze
        target_id: Node ID of the target symbol
        direction: "upstream" (who depends on this) or "downstream" (what this depends on)
        max_depth: Maximum traversal depth (1-3)

    Returns:
        {"depth_1": [...], "depth_2": [...], "depth_3": [...]}
        Each entry: {"node_id": str, "name": str, "file": str, "edge_type": str}
    """
    if target_id not in organism.nodes:
        return {f"depth_{d}": [] for d in range(1, max_depth + 1)}

    # Build adjacency in the right direction
    adj: dict[str, list[tuple[str, str]]] = {}  # node_id -> [(neighbor_id, edge_type)]

    for edge in organism.edges.values():
        if direction == "upstream":
            # Who points TO the target? Follow edges backward.
            adj.setdefault(edge.target_id, []).append((edge.source_id, edge.edge_type))
        else:
            # What does the target point TO? Follow edges forward.
            adj.setdefault(edge.source_id, []).append((edge.target_id, edge.edge_type))

    # BFS by depth
    result = {}
    visited = {target_id}
    current_level = [target_id]

    for depth in range(1, max_depth + 1):
        next_level = []
        depth_results = []

        for node_id in current_level:
            for neighbor_id, edge_type in adj.get(node_id, []):
                if neighbor_id not in visited:
                    visited.add(neighbor_id)
                    next_level.append(neighbor_id)
                    node = organism.nodes.get(neighbor_id)
                    if node:
                        depth_results.append({
                            "node_id": neighbor_id,
                            "name": node.name,
                            "file": str(node.position.file) if node.position and hasattr(node.position, "file") else "",
                            "edge_type": edge_type,
                        })

        result[f"depth_{depth}"] = depth_results
        current_level = next_level

    return result
```

- [ ] **Step 4: Run tests**

Run: `cd D:/lost_marbles/Code_Organism && python -m pytest tests/test_impact.py -v`
Expected: All 3 PASS

- [ ] **Step 5: Add `impact` and `communities` CLI subcommands**

Add to `cli.py`:

```python
# impact subcommand
p_impact = subparsers.add_parser("impact", help="Blast radius analysis")
p_impact.add_argument("path", help="File or directory")
p_impact.add_argument("--target", required=True, help="Symbol name to analyze")
p_impact.add_argument("--direction", choices=["upstream", "downstream"], default="upstream")
p_impact.add_argument("--depth", type=int, default=3)
p_impact.add_argument("--output", choices=["text", "json"], default="text")

# communities subcommand
p_communities = subparsers.add_parser("communities", help="Detect functional communities")
p_communities.add_argument("path", help="File or directory")
p_communities.add_argument("--output", choices=["text", "json"], default="text")
```

- [ ] **Step 6: Run all tests**

Run: `cd D:/lost_marbles/Code_Organism && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add analysis/impact.py tests/test_impact.py cli.py
git commit -m "feat: add impact analysis and communities/impact CLI subcommands"
```

---

### Task 15: Wire communities + processes into `index` command

**Files:**
- Modify: `graph/store.py`
- Modify: `cli.py`

- [ ] **Step 1: Add community/process storage to GraphStore.save()**

Extend `GraphStore.save()` to also:
1. Run `detect_communities(organism)` and insert Community nodes
2. Run `detect_processes(organism)` and insert Process nodes + STEP_IN_PROCESS edges

- [ ] **Step 2: Update `cmd_index` to report community/process counts**

Add to the index JSON output:
```json
{"nodes_indexed": N, "edges_indexed": N, "communities": N, "processes": N}
```

- [ ] **Step 3: Run all tests**

Run: `cd D:/lost_marbles/Code_Organism && python -m pytest tests/ -v`
Expected: All PASS

- [ ] **Step 4: Commit**

```bash
git add graph/store.py cli.py
git commit -m "feat: index command now stores communities and processes in graph"
```

---

### Task 16: Update GitNexus to call Code_Organism

**Files:**
- Modify: `D:/lost_marbles/GitNexus/CLAUDE.md`

This task is documentation-only. Update the GitNexus CLAUDE.md to document the new contract:

```markdown
## Integration with Code_Organism

GitNexus MCP tools should delegate analysis to Code_Organism's CLI:

### Commands available:
- `python -m Code_Organism analyze <path> --output json` — parse and return nodes/edges/stats
- `python -m Code_Organism index <path> --db <path>` — parse, analyze health, persist to KuzuDB
- `python -m Code_Organism health <path> --output json` — health diagnostics
- `python -m Code_Organism impact <path> --target <name> --output json` — blast radius
- `python -m Code_Organism communities <path> --output json` — community detection

### Contract:
- All commands accept `--output json` for machine-readable output
- JSON goes to stdout, logs/progress to stderr
- Exit code 0 = success
- The `index` command creates a `.code_organism/` database in the target directory
```

- [ ] **Step 1: Update GitNexus CLAUDE.md**

- [ ] **Step 2: Commit**

```bash
cd D:/lost_marbles/GitNexus && git init && git add -A && git commit -m "docs: add Code_Organism integration contract"
```

---

### Task 17: Commit all uncommitted Code_Organism work

Before this plan's work began, Code_Organism had uncommitted changes (v2 parser, deserialization, Barnes-Hut layout). These should be committed first as a separate commit to preserve the history.

- [ ] **Step 1: Stage and commit existing uncommitted work**

```bash
cd D:/lost_marbles/Code_Organism
git add model/organism.py parser/ast_walker.py renderer/graph_3d.py
git commit -m "feat: v2 parser enhancements, JSON deserialization, server-side layout"
```

- [ ] **Step 2: Stage and commit new untracked files**

```bash
git add .gitignore pyproject.toml tools/ artifacts/ Code_Organism_Brief.md AUDIT.md
git commit -m "chore: add pyproject.toml, tooling, documentation, gitignore"
```

**IMPORTANT:** Task 17 should be executed FIRST, before any other tasks in this plan. The task numbering reflects logical ordering of the design, but execution order is: Task 17 → Task 1 → Task 2 → ... → Task 16.

---

## Execution Order

1. **Task 17** — Commit existing uncommitted work (preserve history)
2. **Task 1** — Test infrastructure + install package
3. **Task 2** — JSON CLI output
4. **Task 3** — CLI subcommands
5. **Task 4** — Install kuzu
6. **Task 5** — Graph schema
7. **Task 6** — Graph store
8. **Task 7** — `index` CLI subcommand
9. **Task 7b** — Export new modules from __init__.py
10. **Task 8** — Install tree-sitter
11. **Task 9** — Tree-sitter parser
12. **Task 10** — Parser dispatcher
13. **Task 11** — Install igraph
14. **Task 12** — Community detection
15. **Task 13** — Process/flow detection
16. **Task 14** — Impact analysis + CLI subcommands
17. **Task 15** — Wire communities/processes into index
18. **Task 16** — Update GitNexus documentation

## What This Does NOT Cover (Future Work)

- **MCP server in Code_Organism** — If we decide to move MCP from GitNexus to Python (Python MCP SDK exists), that's a separate plan.
- **BM25/semantic search** — KuzuDB has FTS, but wiring it up is Phase 5+ work.
- **Rewiring GitNexus MCP tools** — Actually modifying GitNexus's Node.js code to call Code_Organism instead of its own pipeline. This requires modifying the npm package source, which we don't control. Alternative: fork or replace.
- **Runtime tracing integration with graph** — Storing trace data in KuzuDB for queryable execution history.
- **Visualization of graph data** — Using Code_Organism's 3D renderers to visualize the persistent graph (not just in-memory organisms).

---

## Success Criteria

After completing all tasks:

1. `python -m Code_Organism analyze . --output json` returns valid JSON with nodes, edges, stats
2. `python -m Code_Organism index .` creates a `.code_organism/` KuzuDB database with health data
3. `python -m Code_Organism health . --output json` returns per-node health scores
4. `python -m Code_Organism impact . --target MyClass --output json` returns blast radius at depth 1/2/3
5. `python -m Code_Organism communities . --output json` returns Leiden community assignments
6. Tree-sitter parses JS/TS/Java/Go/Rust/C/C++ files alongside Python
7. All existing visualization features (3D graph, solar system, playback) continue to work unchanged
8. All tests pass: `python -m pytest tests/ -v`
