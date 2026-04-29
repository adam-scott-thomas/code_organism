# SPDX-License-Identifier: Apache-2.0
"""
Code_Organism MCP Server

Exposes Code_Organism's analysis capabilities as MCP tools.
Run via: python -m Code_Organism.mcp_server
"""

from __future__ import annotations

import json
import traceback
from pathlib import Path

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# Server instance
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "Code_Organism",
    instructions=(
        "Code analysis engine that parses source code into graph structures, "
        "detects communities, measures health, and performs impact analysis. "
        "Supports Python, JavaScript, TypeScript, Java, Go, Rust, C, and C++."
    ),
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_pattern(path: str, pattern: str | None) -> str:
    """Determine the glob pattern for a path.

    If *pattern* is explicitly provided, use it. Otherwise auto-detect
    from file extension or default to ``**/*.py``.
    """
    if pattern:
        return pattern

    p = Path(path)
    if p.is_file():
        return "**/*.py"  # not used for single files

    # Auto-detect: if the directory contains non-Python source files,
    # use a broader pattern, otherwise default to Python.
    LANG_GLOBS = {
        ".js": "**/*.js",
        ".ts": "**/*.ts",
        ".tsx": "**/*.tsx",
        ".java": "**/*.java",
        ".go": "**/*.go",
        ".rs": "**/*.rs",
        ".c": "**/*.c",
        ".cpp": "**/*.cpp",
    }
    for ext, glob in LANG_GLOBS.items():
        if any(p.glob(f"**/*{ext}")):
            return glob
    return "**/*.py"


def _build_organism(path: str, pattern: str | None = None):
    """Build an Organism from a file or directory path."""
    from Code_Organism.model import Organism

    target = Path(path)
    if not target.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")

    if target.is_dir():
        pat = _resolve_pattern(path, pattern)
        return Organism.from_directory(target, pattern=pat)
    else:
        return Organism.from_file(target)


def _node_to_dict(node) -> dict:
    """Serialize an OrganismNode to a JSON-friendly dict."""
    return {
        "id": node.id,
        "name": node.name,
        "qualified_name": node.qualified_name,
        "type": node.node_type.value,
        "health_status": node.health.value,
        "health_score": node.metrics.health_score(),
        "cyclomatic_complexity": node.metrics.cyclomatic_complexity,
        "lines_of_code": node.metrics.lines_of_code,
        "depth": node.metrics.depth,
        "file": node.position.file if node.position else "",
        "line": node.position.line if node.position else 0,
    }


def _edge_to_dict(edge) -> dict:
    """Serialize an Edge to a JSON-friendly dict."""
    return {
        "id": edge.id,
        "source": edge.source_id,
        "target": edge.target_id,
        "type": edge.edge_type,
        "weight": edge.weight,
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool(
    name="analyze",
    description=(
        "Parse a file or directory and return nodes, edges, and aggregate stats. "
        "Input: path (required), pattern (optional glob like '**/*.py'). "
        "Returns JSON with nodes, edges, and stats."
    ),
)
def analyze(path: str, pattern: str = "") -> str:
    """Parse a file or directory, return nodes/edges/stats."""
    try:
        organism = _build_organism(path, pattern or None)
        stats = organism.stats

        result = {
            "nodes": [_node_to_dict(n) for n in organism.nodes.values()],
            "edges": [_edge_to_dict(e) for e in organism.edges.values()],
            "stats": {
                "total_nodes": stats.total_nodes,
                "total_edges": stats.total_edges,
                "total_modules": stats.total_modules,
                "total_classes": stats.total_classes,
                "total_functions": stats.total_functions,
                "total_lines": stats.total_lines,
                "avg_complexity": stats.avg_complexity,
                "max_complexity": stats.max_complexity,
                "max_depth": stats.max_depth,
                "circular_dependencies": stats.circular_dependencies,
                "healthy_nodes": stats.healthy_nodes,
                "stressed_nodes": stats.stressed_nodes,
                "inflamed_nodes": stats.inflamed_nodes,
                "necrotic_nodes": stats.necrotic_nodes,
                "cancerous_nodes": stats.cancerous_nodes,
            },
        }
        return json.dumps(result, indent=2, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc), "traceback": traceback.format_exc()})


@mcp.tool(
    name="health",
    description=(
        "Run health diagnostics on a file or directory. "
        "Returns a health summary (percentage breakdown) and per-node health data."
    ),
)
def health(path: str) -> str:
    """Health diagnostics for a codebase."""
    try:
        organism = _build_organism(path)
        stats = organism.stats
        health_summary = stats.health_summary()

        nodes = []
        for node in organism.nodes.values():
            nodes.append({
                "name": node.name,
                "qualified_name": node.qualified_name,
                "type": node.node_type.value,
                "health_status": node.health.value,
                "health_score": node.metrics.health_score(),
                "cyclomatic_complexity": node.metrics.cyclomatic_complexity,
                "lines_of_code": node.metrics.lines_of_code,
                "health_notes": node.health_notes,
            })

        result = {"health_summary": health_summary, "nodes": nodes}
        return json.dumps(result, indent=2, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc), "traceback": traceback.format_exc()})


@mcp.tool(
    name="index",
    description=(
        "Parse a codebase and persist the graph to KuzuDB. "
        "Also runs community detection and process detection. "
        "Input: path (required), db_path (optional, defaults to .code_organism.db "
        "inside the target directory). "
        "Returns counts of indexed nodes, edges, communities, and processes."
    ),
)
def index(path: str, db_path: str = "") -> str:
    """Parse and persist to KuzuDB."""
    try:
        from Code_Organism.analysis.communities import detect_communities
        from Code_Organism.analysis.processes import detect_processes
        from Code_Organism.graph.store import GraphStore

        target = Path(path)
        organism = _build_organism(path)
        organism.analyze_health()

        if db_path:
            resolved_db = Path(db_path)
        else:
            base = target if target.is_dir() else target.parent
            resolved_db = base / ".code_organism.db"

        with GraphStore(resolved_db) as store:
            store.save(organism)
            node_count = store.count_nodes()
            assert store._conn is not None  # set by __enter__

            # Detect and store communities
            communities = detect_communities(organism)
            for comm in communities:
                store._conn.execute(
                    "CREATE (:Community {uid: $uid, name: $name, keywords: $kw, "
                    "cohesion: $coh, symbolCount: $sc})",
                    parameters={
                        "uid": comm["id"],
                        "name": comm["name"],
                        "kw": ", ".join(comm.get("keywords", [])),
                        "coh": comm.get("cohesion", 0.0),
                        "sc": len(comm.get("members", [])),
                    },
                )

            # Detect and store processes
            processes = detect_processes(organism)
            for proc in processes:
                store._conn.execute(
                    "CREATE (:Process {uid: $uid, name: $name, entryPointId: $ep, "
                    "stepCount: $sc, processType: $pt})",
                    parameters={
                        "uid": proc["id"],
                        "name": proc["name"],
                        "ep": proc.get("entry_point", ""),
                        "sc": proc.get("step_count", 0),
                        "pt": "call_chain",
                    },
                )

        edge_count = len(organism.edges)
        result = {
            "nodes_indexed": node_count,
            "edges_indexed": edge_count,
            "communities": len(communities),
            "processes": len(processes),
            "db_path": str(resolved_db),
        }
        return json.dumps(result, indent=2, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc), "traceback": traceback.format_exc()})


@mcp.tool(
    name="query",
    description=(
        "Execute a Cypher query against a persisted KuzuDB graph. "
        "The graph must have been created by the 'index' tool first. "
        "Input: db_path (required), cypher (required Cypher query string). "
        "Returns query results as a list of row dicts."
    ),
)
def query(db_path: str, cypher: str) -> str:
    """Query persisted graph with Cypher."""
    try:
        from Code_Organism.graph.store import GraphStore

        db = Path(db_path)
        if not db.exists():
            return json.dumps({
                "error": f"Database not found: {db_path}. Run the 'index' tool first.",
            })

        with GraphStore(db) as store:
            results = store.query(cypher)

        return json.dumps({"results": results, "count": len(results)}, indent=2, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc), "traceback": traceback.format_exc()})


@mcp.tool(
    name="impact",
    description=(
        "Blast radius analysis: find all symbols affected by changing a target symbol. "
        "Works from a persisted KuzuDB graph (run 'index' first). "
        "Input: db_path (required), target (symbol name), "
        "direction ('upstream' = who depends on me, 'downstream' = what do I depend on), "
        "depth (max traversal depth, default 3). "
        "Returns affected nodes grouped by depth level."
    ),
)
def impact(db_path: str, target: str, direction: str = "upstream", depth: int = 3) -> str:
    """Blast radius analysis from a persisted graph."""
    try:
        from Code_Organism.graph.store import GraphStore

        db = Path(db_path)
        if not db.exists():
            return json.dumps({
                "error": f"Database not found: {db_path}. Run the 'index' tool first.",
            })

        with GraphStore(db) as store:
            # Find target node by name
            target_uid = None
            for table in ["Function", "Method", "Class", "Module", "Package", "Variable"]:
                try:
                    rows = store.query(
                        f"MATCH (n:{table} {{name: $name}}) RETURN n.uid AS uid",
                        {"name": target},
                    )
                    if rows:
                        target_uid = rows[0]["uid"]
                        break
                except Exception:
                    continue

            if target_uid is None:
                return json.dumps({
                    "error": f"Symbol '{target}' not found in the graph.",
                    "target": target,
                    **{f"depth_{d}": [] for d in range(1, depth + 1)},
                })

            # BFS traversal via repeated Cypher queries
            result: dict[str, list[dict]] = {}
            visited: set[str] = {target_uid}
            current_frontier: set[str] = {target_uid}

            for d in range(1, depth + 1):
                next_frontier: set[str] = set()
                depth_entries: list[dict] = []

                for uid in current_frontier:
                    if direction == "upstream":
                        rows = store.query(
                            "MATCH (src)-[r:CodeRelation]->(tgt {uid: $uid}) "
                            "RETURN src.uid AS uid, src.name AS name, "
                            "src.filePath AS file, r.kind AS edge_type",
                            {"uid": uid},
                        )
                    else:
                        rows = store.query(
                            "MATCH (src {uid: $uid})-[r:CodeRelation]->(tgt) "
                            "RETURN tgt.uid AS uid, tgt.name AS name, "
                            "tgt.filePath AS file, r.kind AS edge_type",
                            {"uid": uid},
                        )

                    for row in rows:
                        neighbor_uid = row["uid"]
                        if neighbor_uid in visited:
                            continue
                        visited.add(neighbor_uid)
                        next_frontier.add(neighbor_uid)
                        depth_entries.append({
                            "node_id": neighbor_uid,
                            "name": row["name"],
                            "file": row.get("file", ""),
                            "edge_type": row["edge_type"],
                        })

                result[f"depth_{d}"] = depth_entries
                current_frontier = next_frontier

                if not current_frontier:
                    for remaining in range(d + 1, depth + 1):
                        result[f"depth_{remaining}"] = []
                    break

        return json.dumps(result, indent=2, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc), "traceback": traceback.format_exc()})


@mcp.tool(
    name="communities",
    description=(
        "Detect functional communities in a codebase using the Leiden algorithm. "
        "Clusters of tightly-coupled code that form logical subsystems. "
        "Input: path (required, file or directory). "
        "Returns list of communities with members, cohesion, and keywords."
    ),
)
def communities(path: str) -> str:
    """Community detection via Leiden algorithm."""
    try:
        from Code_Organism.analysis.communities import detect_communities as _detect

        organism = _build_organism(path)
        comms = _detect(organism)

        result = {"communities": comms, "total": len(comms)}
        return json.dumps(result, indent=2, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc), "traceback": traceback.format_exc()})


@mcp.tool(
    name="hotspots",
    description=(
        "Find complexity hotspots from a persisted KuzuDB graph. "
        "Returns the top N functions/methods by cyclomatic complexity. "
        "Input: db_path (required), limit (optional, default 10)."
    ),
)
def hotspots(db_path: str, limit: int = 10) -> str:
    """Complexity hotspots from a persisted graph."""
    try:
        from Code_Organism.graph.store import GraphStore

        db = Path(db_path)
        if not db.exists():
            return json.dumps({
                "error": f"Database not found: {db_path}. Run the 'index' tool first.",
            })

        with GraphStore(db) as store:
            results = store.query(
                "MATCH (f:Function) WHERE f.cyclomatic_complexity > 0 "
                "RETURN f.name AS name, f.filePath AS file, "
                "f.cyclomatic_complexity AS complexity, f.health_score AS score "
                f"ORDER BY f.cyclomatic_complexity DESC LIMIT {int(limit)}"
            )

        return json.dumps({"hotspots": results, "count": len(results)}, indent=2, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc), "traceback": traceback.format_exc()})


@mcp.tool(
    name="unhealthy",
    description=(
        "Find unhealthy nodes from a persisted KuzuDB graph. "
        "Returns functions and methods with health_score below a threshold. "
        "Input: db_path (required), threshold (optional, default 0.5)."
    ),
)
def unhealthy(db_path: str, threshold: float = 0.5) -> str:
    """Unhealthy nodes from a persisted graph."""
    try:
        from Code_Organism.graph.store import GraphStore

        db = Path(db_path)
        if not db.exists():
            return json.dumps({
                "error": f"Database not found: {db_path}. Run the 'index' tool first.",
            })

        with GraphStore(db) as store:
            func_results = store.query(
                "MATCH (f:Function) WHERE f.health_score < $threshold "
                "RETURN f.name AS name, f.filePath AS file, "
                "f.health_status AS status, f.health_score AS score "
                "ORDER BY f.health_score",
                {"threshold": threshold},
            )
            method_results = store.query(
                "MATCH (m:Method) WHERE m.health_score < $threshold "
                "RETURN m.name AS name, m.filePath AS file, "
                "m.health_status AS status, m.health_score AS score "
                "ORDER BY m.health_score",
                {"threshold": threshold},
            )

        combined = func_results + method_results
        combined.sort(key=lambda r: r.get("score", 0))

        return json.dumps({"unhealthy": combined, "count": len(combined)}, indent=2, default=str)
    except Exception as exc:
        return json.dumps({"error": str(exc), "traceback": traceback.format_exc()})


# ---------------------------------------------------------------------------
# Resources
# ---------------------------------------------------------------------------

@mcp.resource(
    "code-organism://status",
    name="status",
    description="Code_Organism version and capabilities.",
    mime_type="application/json",
)
def resource_status() -> str:
    """Return server status and capabilities."""
    from Code_Organism import __version__

    return json.dumps({
        "name": "Code_Organism",
        "version": __version__,
        "capabilities": {
            "tools": [
                "analyze", "health", "index", "query",
                "impact", "communities", "hotspots", "unhealthy",
            ],
            "resources": [
                "code-organism://status",
                "code-organism://schema",
            ],
        },
        "supported_languages": [
            "Python", "JavaScript", "TypeScript",
            "Java", "Go", "Rust", "C", "C++",
        ],
    }, indent=2)


@mcp.resource(
    "code-organism://schema",
    name="schema",
    description="Graph schema reference (node types, edge types) for writing Cypher queries.",
    mime_type="application/json",
)
def resource_schema() -> str:
    """Return the graph schema for Cypher query reference."""
    from Code_Organism.graph.schema import NODE_TABLES

    return json.dumps({
        "node_tables": {
            name: cols for name, cols in NODE_TABLES.items()
        },
        "edge_table": {
            "name": "CodeRelation",
            "columns": {
                "kind": "STRING - edge type (call, import, reference, inheritance, composition, etc.)",
                "weight": "DOUBLE - edge weight",
            },
            "connects": "All structural node types (Module, Package, Class, Function, Method, Variable, External)",
        },
        "common_queries": {
            "all_functions": "MATCH (f:Function) RETURN f.name, f.filePath, f.health_score",
            "call_graph": "MATCH (a)-[r:CodeRelation {kind: 'call'}]->(b) RETURN a.name, b.name",
            "imports": "MATCH (a)-[r:CodeRelation {kind: 'import'}]->(b) RETURN a.name, b.name",
            "unhealthy": "MATCH (f:Function) WHERE f.health_score < 0.5 RETURN f.name, f.health_score ORDER BY f.health_score",
            "hotspots": "MATCH (f:Function) RETURN f.name, f.cyclomatic_complexity ORDER BY f.cyclomatic_complexity DESC LIMIT 10",
            "communities": "MATCH (c:Community) RETURN c.name, c.keywords, c.cohesion, c.symbolCount",
            "processes": "MATCH (p:Process) RETURN p.name, p.entryPointId, p.stepCount",
        },
    }, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """Run the MCP server on stdio."""
    mcp.run(transport="stdio")
