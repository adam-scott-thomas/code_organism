# SPDX-License-Identifier: Apache-2.0
"""
CODE ORGANISM: Command Line Interface

Usage (legacy):
    python -m Code_Organism path/to/file.py
    python -m Code_Organism path/to/directory/
    python -m Code_Organism --export organism.json path/to/project/
    python -m Code_Organism --playback recording.corg.gz

Usage (subcommands):
    code-organism analyze <path> [--output json]
    code-organism health <path> [--output json]
    code-organism index <path> [--db PATH] [--output json]
    code-organism impact <path> --target NAME [--output json]
    code-organism communities <path> [--output json]
    code-organism query <db_path> --cypher "..." [--output json]
    code-organism query <db_path> --unhealthy [--output json]
    code-organism query <db_path> --hotspots [--output json]
    code-organism query <db_path> --stats [--output json]
    code-organism impact-graph <db_path> --target NAME [--direction upstream|downstream] [--depth N] [--output json]
"""

import argparse
import json
import sys
from pathlib import Path

from .model import Organism

# Subcommands recognized by the new CLI
SUBCOMMANDS = {"analyze", "health", "index", "impact", "communities", "query", "impact-graph"}


def _output_json(data, file=None):
    """Write JSON data to stdout (or file). All non-JSON goes to stderr."""
    text = json.dumps(data, indent=2, default=str)
    if file:
        Path(file).write_text(text, encoding="utf-8")
    else:
        print(text)


def _info(msg):
    """Print an informational message to stderr (safe for --output json)."""
    print(msg, file=sys.stderr)


def _build_organism(target: Path, pattern: str = "**/*.py") -> Organism:
    """Build an Organism from a file or directory path."""
    _info(f"Analyzing {'directory' if target.is_dir() else 'file'}: {target}")
    if target.is_dir():
        return Organism.from_directory(target, pattern=pattern)
    else:
        return Organism.from_file(target)


def _organism_to_json(organism: Organism) -> dict:
    """Convert an organism to the JSON output schema for analyze."""
    stats = organism.stats
    nodes = []
    for node in organism.nodes.values():
        nodes.append({
            "id": node.id,
            "name": node.name,
            "qualified_name": node.qualified_name,
            "type": node.node_type.value,
            "health_status": node.health.value,
            "health_score": node.metrics.health_score(),
            "cyclomatic_complexity": node.metrics.cyclomatic_complexity,
            "lines_of_code": node.metrics.lines_of_code,
            "depth": node.metrics.depth,
        })
    edges = []
    for edge in organism.edges.values():
        edges.append({
            "id": edge.id,
            "source": edge.source_id,
            "target": edge.target_id,
            "type": edge.edge_type,
            "weight": edge.weight,
        })
    return {
        "nodes": nodes,
        "edges": edges,
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


def _health_to_json(organism: Organism) -> dict:
    """Convert organism health data to the JSON output schema."""
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
    return {
        "health_summary": health_summary,
        "nodes": nodes,
    }


def _malware_result_to_json(results: list) -> dict:
    """Aggregate malware scan results into JSON output schema.

    Args:
        results: list of (filepath, MalwareAnalysisResult) tuples
    """
    all_markers = []
    max_risk = 0.0
    any_likely = False
    for filepath, result in results:
        max_risk = max(max_risk, result.overall_risk)
        any_likely = any_likely or result.is_likely_malware
        for marker in result.markers:
            all_markers.append({
                "file": str(filepath),
                "pattern_name": marker.pattern_name,
                "severity": marker.severity.value,
                "description": marker.description,
                "location": marker.location,
                "confidence": marker.confidence,
                "category": marker.category,
            })
    return {
        "overall_risk": max_risk,
        "is_likely_malware": any_likely,
        "markers": all_markers,
    }


def _complexity_to_json(all_functions: list) -> dict:
    """Convert complexity metrics to JSON output schema."""
    items = []
    for func in all_functions:
        items.append({
            "name": func.name,
            "location": func.location,
            "cyclomatic": func.cyclomatic,
            "cognitive": func.cognitive,
            "maintainability_index": func.maintainability_index,
            "lines_of_code": func.lines_of_code,
            "max_nesting_depth": func.max_nesting_depth,
        })
    return {"complexity": items}


# =========================================================================
# SUBCOMMAND HANDLERS
# =========================================================================


def cmd_analyze(args):
    """Handle the 'analyze' subcommand."""
    target = Path(args.path)
    if not target.exists():
        _info(f"Error: '{target}' does not exist")
        sys.exit(1)

    try:
        organism = _build_organism(target, pattern=args.pattern)
    except Exception as e:
        _info(f"Error analyzing code: {e}")
        sys.exit(1)

    if args.output == "json":
        _output_json(_organism_to_json(organism))
    else:
        _print_organism_stats(organism)


def cmd_health(args):
    """Handle the 'health' subcommand."""
    target = Path(args.path)
    if not target.exists():
        _info(f"Error: '{target}' does not exist")
        sys.exit(1)

    try:
        organism = _build_organism(target)
    except Exception as e:
        _info(f"Error analyzing code: {e}")
        sys.exit(1)

    if args.output == "json":
        _output_json(_health_to_json(organism))
    else:
        _print_health_report(organism)


def cmd_index(args):
    """Handle the 'index' subcommand — analyze and persist to KuzuDB."""
    from .analysis.communities import detect_communities
    from .analysis.processes import detect_processes
    from .graph.store import GraphStore

    target = Path(args.path)
    if not target.exists():
        _info(f"Error: '{target}' does not exist")
        sys.exit(1)

    organism = _build_organism(target, getattr(args, "pattern", "**/*.py"))
    organism.analyze_health()

    db_path = Path(args.db)
    if not db_path.is_absolute():
        db_path = (target if target.is_dir() else target.parent) / args.db

    with GraphStore(db_path) as store:
        store.save(organism)
        node_count = store.count_nodes()

        # Detect and store communities
        communities = detect_communities(organism)
        for comm in communities:
            store._conn.execute(
                "CREATE (:Community {uid: $uid, name: $name, keywords: $kw, cohesion: $coh, symbolCount: $sc})",
                parameters={
                    "uid": comm["id"], "name": comm["name"],
                    "kw": ", ".join(comm.get("keywords", [])),
                    "coh": comm.get("cohesion", 0.0),
                    "sc": len(comm.get("members", [])),
                },
            )

        # Detect and store processes
        processes = detect_processes(organism)
        for proc in processes:
            store._conn.execute(
                "CREATE (:Process {uid: $uid, name: $name, entryPointId: $ep, stepCount: $sc, processType: $pt})",
                parameters={
                    "uid": proc["id"], "name": proc["name"],
                    "ep": proc.get("entry_point", ""),
                    "sc": proc.get("step_count", 0),
                    "pt": "call_chain",
                },
            )

    edge_count = len(organism.edges)
    if getattr(args, "output", "text") == "json":
        _output_json({
            "nodes_indexed": node_count,
            "edges_indexed": edge_count,
            "communities": len(communities),
            "processes": len(processes),
            "db_path": str(db_path),
        })
    else:
        _info(f"Indexed {node_count} nodes, {edge_count} edges, "
              f"{len(communities)} communities, {len(processes)} processes → {db_path}")


def cmd_impact(args):
    """Handle the 'impact' subcommand — blast radius analysis."""
    from .analysis.impact import analyze_impact

    target = Path(args.path)
    if not target.exists():
        _info(f"Error: '{target}' does not exist")
        sys.exit(1)

    organism = _build_organism(target, getattr(args, "pattern", "**/*.py"))

    # Find the target node by name
    matches = organism.find_nodes(args.target)
    if not matches:
        _info(f"Error: symbol '{args.target}' not found")
        if getattr(args, "output", "text") == "json":
            _output_json({"error": f"symbol '{args.target}' not found", "depth_1": [], "depth_2": [], "depth_3": []})
        sys.exit(1)

    target_node = matches[0]
    direction = getattr(args, "direction", "upstream")
    max_depth = getattr(args, "depth", 3)

    result = analyze_impact(organism, target_node.id, direction=direction, max_depth=max_depth)

    if getattr(args, "output", "text") == "json":
        _output_json(result)
    else:
        for depth_key in sorted(result.keys()):
            items = result[depth_key]
            label = {"depth_1": "WILL BREAK", "depth_2": "LIKELY AFFECTED", "depth_3": "MAY NEED TESTING"}.get(depth_key, depth_key)
            print(f"\n{depth_key} ({label}): {len(items)} symbols")
            for item in items[:10]:
                print(f"  - {item['name']} ({item['edge_type']}) {item.get('file', '')}")


def cmd_communities(args):
    """Handle the 'communities' subcommand — Leiden community detection."""
    from .analysis.communities import detect_communities

    target = Path(args.path)
    if not target.exists():
        _info(f"Error: '{target}' does not exist")
        sys.exit(1)

    organism = _build_organism(target, getattr(args, "pattern", "**/*.py"))
    communities = detect_communities(organism)

    if getattr(args, "output", "text") == "json":
        _output_json({"communities": communities, "total": len(communities)})
    else:
        print(f"\nDetected {len(communities)} communities:\n")
        for comm in communities:
            print(f"  [{comm['id']}] {comm['name']} — {len(comm['members'])} members, cohesion={comm['cohesion']:.2f}")
            for kw in comm.get("keywords", [])[:5]:
                print(f"    - {kw}")


def cmd_query(args):
    """Handle the 'query' subcommand — query a persisted KuzuDB graph."""
    from .graph.store import GraphStore

    db_path = Path(args.db)
    if not db_path.exists():
        _info(f"Error: database '{db_path}' not found. Run 'code-organism index' first.")
        sys.exit(1)

    json_mode = getattr(args, "output", None) == "json"

    with GraphStore(db_path) as store:
        if args.cypher:
            results = store.query(args.cypher)
            if json_mode:
                _output_json({"results": results, "count": len(results)})
            else:
                if not results:
                    _info("No results.")
                else:
                    columns = list(results[0].keys())
                    # Print header
                    header = " | ".join(f"{c:>20}" for c in columns)
                    print(header)
                    print("-" * len(header))
                    for row in results:
                        print(" | ".join(f"{str(row[c]):>20}" for c in columns))

        elif args.unhealthy:
            results = store.query(
                "MATCH (f:Function) WHERE f.health_score < 0.5 "
                "RETURN f.name AS name, f.filePath AS file, "
                "f.health_status AS status, f.health_score AS score "
                "ORDER BY f.health_score"
            )
            # Also check methods
            method_results = store.query(
                "MATCH (m:Method) WHERE m.health_score < 0.5 "
                "RETURN m.name AS name, m.filePath AS file, "
                "m.health_status AS status, m.health_score AS score "
                "ORDER BY m.health_score"
            )
            results = results + method_results
            results.sort(key=lambda r: r.get("score", 0))

            if json_mode:
                _output_json({"unhealthy": results, "count": len(results)})
            else:
                if not results:
                    print("No unhealthy nodes found.")
                else:
                    print(f"\nUnhealthy nodes ({len(results)}):\n")
                    for r in results:
                        print(f"  [{r['status']:>10}] {r['name']:<30} score={r['score']:.3f}  {r['file']}")

        elif args.hotspots:
            results = store.query(
                "MATCH (f:Function) WHERE f.cyclomatic_complexity > 0 "
                "RETURN f.name AS name, f.filePath AS file, "
                "f.cyclomatic_complexity AS complexity, f.health_score AS score "
                "ORDER BY f.cyclomatic_complexity DESC LIMIT 10"
            )
            if json_mode:
                _output_json({"hotspots": results, "count": len(results)})
            else:
                if not results:
                    print("No complexity hotspots found.")
                else:
                    print("\nTop complexity hotspots:\n")
                    for r in results:
                        print(f"  CC={r['complexity']:>3}  score={r['score']:.3f}  {r['name']:<30}  {r['file']}")

        elif args.stats:
            # Gather summary stats from the graph
            total = store.count_nodes()
            table_counts = {}
            for table in ["Module", "Package", "Class", "Function", "Method", "Variable", "External", "Community", "Process"]:
                try:
                    rows = store.query(f"MATCH (n:{table}) RETURN count(n) AS cnt")
                    table_counts[table] = rows[0]["cnt"] if rows else 0
                except Exception:
                    table_counts[table] = 0

            edge_rows = store.query("MATCH ()-[r:CodeRelation]->() RETURN count(r) AS cnt")
            edge_count = edge_rows[0]["cnt"] if edge_rows else 0

            # Health distribution for Function + Method nodes
            health_dist = {}
            for table in ["Function", "Method"]:
                try:
                    rows = store.query(
                        f"MATCH (n:{table}) RETURN n.health_status AS status, count(n) AS cnt"
                    )
                    for r in rows:
                        status = r["status"]
                        health_dist[status] = health_dist.get(status, 0) + r["cnt"]
                except Exception:
                    pass

            stats_data = {
                "total_nodes": total,
                "total_edges": edge_count,
                "node_counts": table_counts,
                "health_distribution": health_dist,
            }

            if json_mode:
                _output_json(stats_data)
            else:
                print("\nGraph Statistics:")
                print(f"  Total nodes: {total}")
                print(f"  Total edges: {edge_count}")
                print("\n  Node counts by type:")
                for table, count in table_counts.items():
                    if count > 0:
                        print(f"    {table:>12}: {count}")
                if health_dist:
                    print("\n  Health distribution (Functions + Methods):")
                    for status, count in sorted(health_dist.items()):
                        print(f"    {status:>12}: {count}")

        else:
            _info("Error: specify --cypher, --unhealthy, --hotspots, or --stats")
            sys.exit(1)


def cmd_impact_graph(args):
    """Handle the 'impact-graph' subcommand — blast radius from persisted KuzuDB."""
    from .graph.store import GraphStore

    db_path = Path(args.db)
    if not db_path.exists():
        _info(f"Error: database '{db_path}' not found. Run 'code-organism index' first.")
        sys.exit(1)

    json_mode = getattr(args, "output", None) == "json"
    direction = getattr(args, "direction", "upstream")
    max_depth = getattr(args, "depth", 3)
    target_name = args.target

    with GraphStore(db_path) as store:
        # Find the target node by name across all structural tables
        target_uid = None
        for table in ["Function", "Method", "Class", "Module", "Package", "Variable"]:
            try:
                rows = store.query(
                    f"MATCH (n:{table} {{name: $name}}) RETURN n.uid AS uid",
                    {"name": target_name},
                )
                if rows:
                    target_uid = rows[0]["uid"]
                    break
            except Exception:
                continue

        if target_uid is None:
            _info(f"Error: symbol '{target_name}' not found in the graph.")
            if json_mode:
                _output_json({
                    "error": f"symbol '{target_name}' not found",
                    "target": target_name,
                    **{f"depth_{d}": [] for d in range(1, max_depth + 1)},
                })
            sys.exit(1)

        # BFS traversal via repeated Cypher queries (KuzuDB variable-length
        # path support varies, so we do explicit per-depth queries)
        result: dict[str, list[dict]] = {}
        visited: set[str] = {target_uid}
        current_frontier: set[str] = {target_uid}

        for depth in range(1, max_depth + 1):
            next_frontier: set[str] = set()
            depth_entries: list[dict] = []

            for uid in current_frontier:
                if direction == "upstream":
                    # Who points TO this node?
                    rows = store.query(
                        "MATCH (src)-[r:CodeRelation]->(tgt {uid: $uid}) "
                        "RETURN src.uid AS uid, src.name AS name, src.filePath AS file, r.kind AS edge_type",
                        {"uid": uid},
                    )
                else:
                    # What does this node point TO?
                    rows = store.query(
                        "MATCH (src {uid: $uid})-[r:CodeRelation]->(tgt) "
                        "RETURN tgt.uid AS uid, tgt.name AS name, tgt.filePath AS file, r.kind AS edge_type",
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

            result[f"depth_{depth}"] = depth_entries
            current_frontier = next_frontier

            if not current_frontier:
                for remaining in range(depth + 1, max_depth + 1):
                    result[f"depth_{remaining}"] = []
                break

    if json_mode:
        _output_json(result)
    else:
        total = sum(len(v) for v in result.values())
        print(f"\nImpact analysis for '{target_name}' ({direction}, depth={max_depth}): {total} affected symbols\n")
        for depth_key in sorted(result.keys()):
            items = result[depth_key]
            label = {
                "depth_1": "WILL BREAK",
                "depth_2": "LIKELY AFFECTED",
                "depth_3": "MAY NEED TESTING",
            }.get(depth_key, depth_key)
            print(f"{depth_key} ({label}): {len(items)} symbols")
            for item in items[:10]:
                print(f"  - {item['name']} ({item['edge_type']}) {item.get('file', '')}")
            if len(items) > 10:
                print(f"  ... and {len(items) - 10} more")


def _print_organism_stats(organism: Organism):
    """Print the organism stats table to stdout (text mode)."""
    stats = organism.stats
    print(f"""
+--------------------------------------------------------------+
|                    ORGANISM ANALYSIS                          |
+--------------------------------------------------------------+
|  Name:           {organism.name:42} |
|  Modules:        {stats.total_modules:42} |
|  Classes:        {stats.total_classes:42} |
|  Functions:      {stats.total_functions:42} |
|  Total Nodes:    {stats.total_nodes:42} |
|  Connections:    {stats.total_edges:42} |
|  Lines of Code:  {stats.total_lines:42} |
+--------------------------------------------------------------+
|  COMPLEXITY                                                   |
+--------------------------------------------------------------+
|  Avg Complexity: {stats.avg_complexity:42.2f} |
|  Max Complexity: {stats.max_complexity:42} |
|  Max Depth:      {stats.max_depth:42} |
|  Circular Deps:  {stats.circular_dependencies:42} |
+--------------------------------------------------------------+
|  HEALTH                                                       |
+--------------------------------------------------------------+
|  Healthy:        {stats.healthy_nodes:42} |
|  Stressed:       {stats.stressed_nodes:42} |
|  Inflamed:       {stats.inflamed_nodes:42} |
|  Necrotic:       {stats.necrotic_nodes:42} |
|  Cancerous:      {stats.cancerous_nodes:42} |
+--------------------------------------------------------------+
""")


def _print_health_report(organism: Organism):
    """Print a health report to stdout (text mode)."""
    stats = organism.stats
    summary = stats.health_summary()
    print("Health Summary:")
    for status, pct in summary.items():
        bar = "#" * int(pct * 40)
        print(f"  {status:12} {pct:6.1%}  {bar}")
    print()
    # Show unhealthy nodes
    unhealthy = [n for n in organism.nodes.values() if n.health.value not in ("healthy", "unknown")]
    if unhealthy:
        print(f"Unhealthy nodes ({len(unhealthy)}):")
        for node in unhealthy[:20]:
            notes = "; ".join(node.health_notes) if node.health_notes else ""
            print(f"  [{node.health.value:>10}] {node.qualified_name}  {notes}")
        if len(unhealthy) > 20:
            print(f"  ... and {len(unhealthy) - 20} more")


# =========================================================================
# NEW SUBCOMMAND-BASED CLI
# =========================================================================


def _build_subcommand_parser():
    """Build the argparse parser with subcommands."""
    parser = argparse.ArgumentParser(
        prog="code-organism",
        description="Code_Organism analysis engine",
    )
    parser.add_argument("--version", action="version", version="code-organism 2.0.0")

    subparsers = parser.add_subparsers(dest="command")

    # --- analyze ---
    p_analyze = subparsers.add_parser("analyze", help="Parse and return organism data")
    p_analyze.add_argument("path", type=str, help="Python file or directory to analyze")
    p_analyze.add_argument("--output", type=str, choices=["json"], default=None,
                           help="Output format (default: text)")
    p_analyze.add_argument("--pattern", type=str, default="**/*.py",
                           help="Glob pattern for files (default: **/*.py)")

    # --- health ---
    p_health = subparsers.add_parser("health", help="Health diagnostics")
    p_health.add_argument("path", type=str, help="Python file or directory to analyze")
    p_health.add_argument("--output", type=str, choices=["json"], default=None,
                          help="Output format (default: text)")

    # --- index ---
    p_index = subparsers.add_parser("index", help="Analyze and persist to graph database")
    p_index.add_argument("path", type=str, help="Python file or directory to analyze")
    p_index.add_argument("--db", type=str, default=None, help="Path to KuzuDB database")
    p_index.add_argument("--output", type=str, choices=["json"], default=None,
                         help="Output format (default: text)")

    # --- impact ---
    p_impact = subparsers.add_parser("impact", help="Blast radius analysis")
    p_impact.add_argument("path", type=str, help="Python file or directory to analyze")
    p_impact.add_argument("--target", type=str, required=True,
                          help="Name of the target node to analyze")
    p_impact.add_argument("--direction", type=str, choices=["upstream", "downstream"],
                          default="downstream", help="Direction of analysis")
    p_impact.add_argument("--output", type=str, choices=["json"], default=None,
                          help="Output format (default: text)")

    # --- communities ---
    p_communities = subparsers.add_parser("communities", help="Community detection")
    p_communities.add_argument("path", type=str, help="Python file or directory to analyze")
    p_communities.add_argument("--output", type=str, choices=["json"], default=None,
                               help="Output format (default: text)")

    # --- query ---
    p_query = subparsers.add_parser("query", help="Query a persisted KuzuDB graph")
    p_query.add_argument("db", type=str, help="Path to KuzuDB database")
    p_query.add_argument("--cypher", type=str, default=None,
                         help="Raw Cypher query to execute")
    p_query.add_argument("--unhealthy", action="store_true",
                         help="Show all nodes with health_score < 0.5")
    p_query.add_argument("--hotspots", action="store_true",
                         help="Show top 10 nodes by cyclomatic complexity")
    p_query.add_argument("--stats", action="store_true",
                         help="Show summary statistics from the graph")
    p_query.add_argument("--output", type=str, choices=["json"], default=None,
                         help="Output format (default: text)")

    # --- impact-graph ---
    p_impact_graph = subparsers.add_parser("impact-graph",
                                           help="Blast radius from persisted graph")
    p_impact_graph.add_argument("db", type=str, help="Path to KuzuDB database")
    p_impact_graph.add_argument("--target", type=str, required=True,
                                help="Name of the target symbol")
    p_impact_graph.add_argument("--direction", type=str,
                                choices=["upstream", "downstream"],
                                default="upstream",
                                help="Direction of analysis (default: upstream)")
    p_impact_graph.add_argument("--depth", type=int, default=3,
                                help="Maximum traversal depth (default: 3)")
    p_impact_graph.add_argument("--output", type=str, choices=["json"], default=None,
                                help="Output format (default: text)")

    return parser


def _subcommand_main():
    """Entry point for the new subcommand-based CLI."""
    parser = _build_subcommand_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    dispatch = {
        "analyze": cmd_analyze,
        "health": cmd_health,
        "index": cmd_index,
        "impact": cmd_impact,
        "communities": cmd_communities,
        "query": cmd_query,
        "impact-graph": cmd_impact_graph,
    }

    handler = dispatch.get(args.command)
    if handler:
        handler(args)
    else:
        parser.print_help()
        sys.exit(1)


# =========================================================================
# LEGACY CLI (original main, preserved for backward compatibility)
# =========================================================================


def _legacy_main():
    """Original CLI entry point — handles positional path + flag-based modes."""
    from .renderer import (
        render_organism,
        render_organism_instanced,
        render_solar_system,
    )

    parser = argparse.ArgumentParser(
        description="Code Organism Visualizer - See the soul of software",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s script.py                    Visualize a single file
  %(prog)s my_project/                  Visualize a whole directory
  %(prog)s --port 9000 script.py        Use custom port
  %(prog)s --export out.json .          Export organism data to JSON
  %(prog)s --stats script.py            Print stats without visualization
  %(prog)s --playback recording.corg.gz Play back a recorded session
  %(prog)s --malware-scan script.py     Scan for malware patterns
        """,
    )

    parser.add_argument(
        "target",
        type=str,
        nargs="?",
        help="Python file or directory to analyze",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port for visualization server (default: 8765)",
    )

    parser.add_argument(
        "--export",
        type=str,
        metavar="FILE",
        help="Export organism data to JSON file",
    )

    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print statistics and exit (no visualization)",
    )

    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't automatically open browser",
    )

    parser.add_argument(
        "--pattern",
        type=str,
        default="**/*.py",
        help="Glob pattern for files (default: **/*.py)",
    )

    parser.add_argument(
        "--playback",
        type=str,
        metavar="FILE",
        help="Play back a recorded session (.corg or .corg.gz file)",
    )

    parser.add_argument(
        "--malware-scan",
        action="store_true",
        help="Scan for malware patterns and suspicious code",
    )

    parser.add_argument(
        "--complexity",
        action="store_true",
        help="Show detailed complexity analysis",
    )

    parser.add_argument(
        "--instanced",
        action="store_true",
        help="Use GPU-instanced renderer for large codebases (1000+ nodes)",
    )

    parser.add_argument(
        "--max-level",
        type=int,
        default=2,
        help="Maximum cluster detail level for instanced renderer (0-4, default: 2)",
    )

    parser.add_argument(
        "--solar",
        action="store_true",
        help="Use solar system navigation (click-to-expand cosmic hierarchy)",
    )

    parser.add_argument(
        "--output",
        type=str,
        choices=["json"],
        default=None,
        help="Output format (default: text)",
    )

    args = parser.parse_args()

    # Handle playback mode
    if args.playback:
        return run_playback(args)

    # Require target for other modes
    if not args.target:
        parser.print_help()
        sys.exit(1)

    target = Path(args.target)

    if not target.exists():
        print(f"Error: '{target}' does not exist")
        sys.exit(1)

    # Handle malware scan
    if args.malware_scan:
        return run_malware_scan(target, args)

    # Handle complexity analysis
    if args.complexity:
        return run_complexity_analysis(target, args)

    # Analyze
    if args.output == "json":
        _info(f"Analyzing {'directory' if target.is_dir() else 'file'}: {target}")
    else:
        print(f"Analyzing {'directory' if target.is_dir() else 'file'}: {target}")

    try:
        if target.is_dir():
            organism = Organism.from_directory(target, pattern=args.pattern)
        else:
            organism = Organism.from_file(target)
    except Exception as e:
        print(f"Error analyzing code: {e}")
        sys.exit(1)

    # JSON output for stats/analyze mode
    if args.output == "json":
        _output_json(_organism_to_json(organism))
        # Also export if requested
        if args.export:
            export_path = Path(args.export)
            organism.save(export_path)
            _info(f"Exported to: {export_path}")
        return

    # Print stats
    _print_organism_stats(organism)

    # Report hotspots
    stats = organism.stats
    if stats.complexity_hotspots:
        print("Complexity Hotspots:")
        for hotspot in stats.complexity_hotspots[:5]:
            print(f"   - {hotspot}")
        print()

    # Report dead code
    dead_code = organism.find_dead_code()
    if dead_code:
        print(f"Dead Code ({len(dead_code)} items):")
        for node in dead_code[:5]:
            print(f"   - {node.qualified_name}")
        if len(dead_code) > 5:
            print(f"   ... and {len(dead_code) - 5} more")
        print()

    # Report circular dependencies
    circles = organism.find_circular_dependencies()
    if circles:
        print(f"Circular Dependencies ({len(circles)} cycles):")
        for cycle in circles[:3]:
            cycle_str = " -> ".join(cycle[:5])
            if len(cycle) > 5:
                cycle_str += " -> ..."
            print(f"   - {cycle_str}")
        print()

    # Export if requested
    if args.export:
        export_path = Path(args.export)
        organism.save(export_path)
        print(f"Exported to: {export_path}")

    # Visualize unless --stats
    if not args.stats:
        if args.solar:
            # Solar system navigation mode
            print("Launching solar system navigation...")
            print("  Click on cosmic bodies to explore deeper")
            print("  Use breadcrumbs to navigate back")
            renderer = render_solar_system(
                organism,
                port=args.port,
                open_browser=not args.no_browser,
            )
        elif args.instanced or stats.total_nodes > 5000:
            # GPU-instanced mode for large codebases
            print(f"Launching GPU-instanced visualization (level {args.max_level})...")
            print("  Using hierarchical clustering for large-scale rendering")
            renderer = render_organism_instanced(
                organism,
                port=args.port,
                open_browser=not args.no_browser,
                max_level=args.max_level,
            )
        else:
            print("Launching 3D visualization...")
            renderer = render_organism(
                organism,
                port=args.port,
                open_browser=not args.no_browser,
            )

        try:
            print("\n   Press Ctrl+C to stop the server\n")
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down...")
            renderer.stop()


def run_playback(args):
    """Run playback mode."""
    from .renderer import render_playback_file

    filepath = Path(args.playback)

    if not filepath.exists():
        print(f"Error: Recording file '{filepath}' does not exist")
        sys.exit(1)

    print(f"Loading recording: {filepath}")

    try:
        renderer = render_playback_file(
            filepath,
            port=args.port,
            open_browser=not args.no_browser,
        )

        print("\n   Press Ctrl+C to stop the server\n")
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        renderer.stop()


def run_malware_scan(target: Path, args):
    """Run malware pattern scan."""
    from .health import analyze_for_malware

    json_mode = getattr(args, "output", None) == "json"

    if json_mode:
        _info(f"Scanning for malware patterns: {target}")
    else:
        print(f"Scanning for malware patterns: {target}")
        print()

    if target.is_file():
        files = [target]
    else:
        files = list(target.glob(args.pattern))

    results = []  # (filepath, MalwareAnalysisResult) for JSON mode
    total_markers = 0
    critical_count = 0

    for filepath in files:
        try:
            with open(filepath, encoding="utf-8", errors="ignore") as f:
                source = f.read()

            result = analyze_for_malware(source, str(filepath))
            results.append((filepath, result))

            if not json_mode and result.markers:
                print(f"\n[!] {filepath}")
                for marker in result.markers:
                    severity_icon = {
                        "critical": "[CRITICAL]",
                        "high": "[HIGH]",
                        "medium": "[MEDIUM]",
                        "low": "[low]",
                    }.get(marker.severity.value, "[ ]")

                    print(f"    {severity_icon} {marker.description}")
                    print(f"        Location: {marker.location}")
                    if marker.code_snippet:
                        print(f"        Code: {marker.code_snippet[:60]}...")

                    total_markers += 1
                    if marker.severity.value == "critical":
                        critical_count += 1

        except Exception as e:
            if json_mode:
                _info(f"Error scanning {filepath}: {e}")
            else:
                print(f"Error scanning {filepath}: {e}")

    if json_mode:
        _output_json(_malware_result_to_json(results))
    else:
        print()
        print(f"Scan complete: {len(files)} files scanned")
        print(f"Findings: {total_markers} suspicious patterns")
        if critical_count:
            print(f"[!] CRITICAL: {critical_count} critical issues found!")


def run_complexity_analysis(target: Path, args):
    """Run detailed complexity analysis."""
    from .health import analyze_complexity

    json_mode = getattr(args, "output", None) == "json"

    if json_mode:
        _info(f"Analyzing complexity: {target}")
    else:
        print(f"Analyzing complexity: {target}")
        print()

    if target.is_file():
        files = [target]
    else:
        files = list(target.glob(args.pattern))

    all_functions = []

    for filepath in files:
        try:
            with open(filepath, encoding="utf-8", errors="ignore") as f:
                source = f.read()

            report = analyze_complexity(source, str(filepath))
            all_functions.extend(report.functions)

        except Exception as e:
            if json_mode:
                _info(f"Error analyzing {filepath}: {e}")
            else:
                print(f"Error analyzing {filepath}: {e}")

    # Sort by complexity
    all_functions.sort(key=lambda f: f.cyclomatic, reverse=True)

    if json_mode:
        _output_json(_complexity_to_json(all_functions))
    else:
        print("+--------------------------------------------------------------+")
        print("|                    COMPLEXITY REPORT                          |")
        print("+--------------------------------------------------------------+")
        print(f"| Total functions analyzed: {len(all_functions):33} |")
        print("+--------------------------------------------------------------+")
        print()

        if all_functions:
            avg_cyclomatic = sum(f.cyclomatic for f in all_functions) / len(all_functions)
            avg_cognitive = sum(f.cognitive for f in all_functions) / len(all_functions)
            avg_maintainability = sum(f.maintainability_index for f in all_functions) / len(all_functions)

            print(f"Average Cyclomatic Complexity: {avg_cyclomatic:.2f}")
            print(f"Average Cognitive Complexity:  {avg_cognitive:.2f}")
            print(f"Average Maintainability Index: {avg_maintainability:.2f}")
            print()

            print("Top 10 Most Complex Functions:")
            print("-" * 70)
            for func in all_functions[:10]:
                print(f"  {func.name:30} CC={func.cyclomatic:3}  COG={func.cognitive:3}  MI={func.maintainability_index:.1f}")
                print(f"    {func.location}")
            print()


# =========================================================================
# MAIN ENTRY POINT — detects legacy vs. subcommand invocation
# =========================================================================


def main():
    """
    Main entry point. Detects whether the user is invoking a new subcommand
    or using the legacy flag-based CLI, and dispatches accordingly.
    """
    # If no arguments at all, or first arg is --version, use new CLI
    if len(sys.argv) <= 1:
        _subcommand_main()
        return

    first_arg = sys.argv[1]

    # If the first arg is a known subcommand, use new CLI
    if first_arg in SUBCOMMANDS:
        _subcommand_main()
        return

    # If the first arg is --version, use new CLI (it handles --version)
    if first_arg == "--version":
        _subcommand_main()
        return

    # Otherwise, delegate to the legacy CLI
    _legacy_main()


if __name__ == "__main__":
    main()
