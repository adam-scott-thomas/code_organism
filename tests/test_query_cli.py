"""Tests for the 'query' and 'impact-graph' CLI subcommands.

These subcommands query a persisted KuzuDB graph without re-parsing
the codebase.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from Code_Organism.graph.store import GraphStore
from Code_Organism.model.nodes import Edge, HealthStatus, Metrics, NodeType, OrganismNode, Position
from Code_Organism.model.organism import Organism


PKG_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = PKG_ROOT.parent


def run_cli(*args, cwd=None):
    """Run the CLI as a subprocess, returning (stdout, stderr, returncode)."""
    cmd = [sys.executable, "-m", "Code_Organism"] + list(args)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=cwd or str(WORKSPACE),
    )
    return result.stdout, result.stderr, result.returncode


def _make_test_organism() -> Organism:
    """Build a test organism with varied health and complexity."""
    org = Organism(name="test-query")

    mod = OrganismNode(
        id="mod1", name="app", node_type=NodeType.MODULE,
        qualified_name="app",
        position=Position(file="app.py", line=1, column=0, end_line=100),
        metrics=Metrics(
            cyclomatic_complexity=1, cognitive_complexity=0,
            maintainability_index=90.0, halstead_difficulty=2.0,
            lines_of_code=100,
        ),
        health=HealthStatus.HEALTHY,
    )

    func_healthy = OrganismNode(
        id="fn_healthy", name="do_work", node_type=NodeType.FUNCTION,
        qualified_name="app.do_work",
        position=Position(file="app.py", line=5, column=0, end_line=20),
        signature="do_work() -> None",
        metrics=Metrics(
            cyclomatic_complexity=2, cognitive_complexity=1,
            maintainability_index=85.0, halstead_difficulty=3.0,
            lines_of_code=15,
        ),
        health=HealthStatus.HEALTHY,
    )

    func_stressed = OrganismNode(
        id="fn_stressed", name="parse_data", node_type=NodeType.FUNCTION,
        qualified_name="app.parse_data",
        position=Position(file="app.py", line=25, column=0, end_line=60),
        signature="parse_data(raw: str) -> dict",
        metrics=Metrics(
            cyclomatic_complexity=20, cognitive_complexity=25,
            maintainability_index=0.0, halstead_difficulty=30.0,
            lines_of_code=35, depth=8,
        ),
        health=HealthStatus.STRESSED,
    )

    func_inflamed = OrganismNode(
        id="fn_inflamed", name="validate_all", node_type=NodeType.FUNCTION,
        qualified_name="app.validate_all",
        position=Position(file="app.py", line=65, column=0, end_line=95),
        signature="validate_all(items: list) -> bool",
        metrics=Metrics(
            cyclomatic_complexity=30, cognitive_complexity=40,
            maintainability_index=0.0, halstead_difficulty=50.0,
            lines_of_code=30, depth=10,
        ),
        health=HealthStatus.INFLAMED,
    )

    var = OrganismNode(
        id="var1", name="CONFIG", node_type=NodeType.VARIABLE,
        qualified_name="app.CONFIG",
        position=Position(file="app.py", line=3, column=0),
    )

    for node in [mod, func_healthy, func_stressed, func_inflamed, var]:
        org.add_node(node)

    # Edges: mod contains functions, do_work calls parse_data,
    # parse_data calls validate_all
    org.add_edge(Edge(id="e1", source_id="mod1", target_id="fn_healthy",
                      edge_type="contains", weight=1.0))
    org.add_edge(Edge(id="e2", source_id="mod1", target_id="fn_stressed",
                      edge_type="contains", weight=1.0))
    org.add_edge(Edge(id="e3", source_id="mod1", target_id="fn_inflamed",
                      edge_type="contains", weight=1.0))
    org.add_edge(Edge(id="e4", source_id="fn_healthy", target_id="fn_stressed",
                      edge_type="call", weight=1.0))
    org.add_edge(Edge(id="e5", source_id="fn_stressed", target_id="fn_inflamed",
                      edge_type="call", weight=1.0))
    org.add_edge(Edge(id="e6", source_id="fn_healthy", target_id="var1",
                      edge_type="reference", weight=0.5))

    return org


@pytest.fixture
def indexed_db(tmp_path):
    """Index a test organism into KuzuDB and return the db path."""
    db_path = tmp_path / "test_graph.kuzu"
    org = _make_test_organism()

    with GraphStore(db_path) as store:
        store.save(org)

    return db_path


# =========================================================================
# query --cypher
# =========================================================================


class TestQueryCypher:
    """Tests for the --cypher flag."""

    def test_cypher_json(self, indexed_db):
        stdout, stderr, rc = run_cli(
            "query", str(indexed_db),
            "--cypher", "MATCH (f:Function) RETURN f.name AS name ORDER BY f.name",
            "--output", "json",
        )
        assert rc == 0, f"CLI failed: {stderr}"
        data = json.loads(stdout)
        assert "results" in data
        assert "count" in data
        names = [r["name"] for r in data["results"]]
        assert "do_work" in names
        assert "parse_data" in names
        assert "validate_all" in names

    def test_cypher_text(self, indexed_db):
        stdout, stderr, rc = run_cli(
            "query", str(indexed_db),
            "--cypher", "MATCH (f:Function) RETURN f.name AS name ORDER BY f.name",
        )
        assert rc == 0, f"CLI failed: {stderr}"
        assert "do_work" in stdout
        assert "parse_data" in stdout

    def test_cypher_empty_result(self, indexed_db):
        stdout, stderr, rc = run_cli(
            "query", str(indexed_db),
            "--cypher", "MATCH (f:Function {name: 'nonexistent'}) RETURN f.name AS name",
            "--output", "json",
        )
        assert rc == 0
        data = json.loads(stdout)
        assert data["count"] == 0
        assert data["results"] == []


# =========================================================================
# query --unhealthy
# =========================================================================


class TestQueryUnhealthy:
    """Tests for the --unhealthy shortcut."""

    def test_unhealthy_json(self, indexed_db):
        stdout, stderr, rc = run_cli(
            "query", str(indexed_db), "--unhealthy", "--output", "json",
        )
        assert rc == 0, f"CLI failed: {stderr}"
        data = json.loads(stdout)
        assert "unhealthy" in data
        assert "count" in data
        # parse_data (stressed, score < 0.5) and validate_all (inflamed, score < 0.5)
        # should appear; do_work (healthy, score >= 0.5) should NOT
        names = [r["name"] for r in data["unhealthy"]]
        assert "do_work" not in names
        # At least one unhealthy node
        assert data["count"] >= 1

    def test_unhealthy_text(self, indexed_db):
        stdout, stderr, rc = run_cli(
            "query", str(indexed_db), "--unhealthy",
        )
        assert rc == 0, f"CLI failed: {stderr}"
        # Should mention "Unhealthy" in output
        assert "unhealthy" in stdout.lower() or "Unhealthy" in stdout


# =========================================================================
# query --hotspots
# =========================================================================


class TestQueryHotspots:
    """Tests for the --hotspots shortcut."""

    def test_hotspots_json(self, indexed_db):
        stdout, stderr, rc = run_cli(
            "query", str(indexed_db), "--hotspots", "--output", "json",
        )
        assert rc == 0, f"CLI failed: {stderr}"
        data = json.loads(stdout)
        assert "hotspots" in data
        assert "count" in data
        assert data["count"] >= 1
        # Should be sorted by complexity descending
        complexities = [r["complexity"] for r in data["hotspots"]]
        assert complexities == sorted(complexities, reverse=True)

    def test_hotspots_text(self, indexed_db):
        stdout, stderr, rc = run_cli(
            "query", str(indexed_db), "--hotspots",
        )
        assert rc == 0, f"CLI failed: {stderr}"
        assert "hotspot" in stdout.lower() or "CC=" in stdout


# =========================================================================
# query --stats
# =========================================================================


class TestQueryStats:
    """Tests for the --stats shortcut."""

    def test_stats_json(self, indexed_db):
        stdout, stderr, rc = run_cli(
            "query", str(indexed_db), "--stats", "--output", "json",
        )
        assert rc == 0, f"CLI failed: {stderr}"
        data = json.loads(stdout)
        assert "total_nodes" in data
        assert "total_edges" in data
        assert "node_counts" in data
        assert data["total_nodes"] == 5  # mod + 3 funcs + var
        assert data["total_edges"] == 6

    def test_stats_text(self, indexed_db):
        stdout, stderr, rc = run_cli(
            "query", str(indexed_db), "--stats",
        )
        assert rc == 0, f"CLI failed: {stderr}"
        assert "Total nodes" in stdout
        assert "Total edges" in stdout


# =========================================================================
# query — error cases
# =========================================================================


class TestQueryErrors:
    """Tests for error handling."""

    def test_nonexistent_db(self, tmp_path):
        db_path = tmp_path / "nonexistent.kuzu"
        stdout, stderr, rc = run_cli(
            "query", str(db_path), "--stats",
        )
        assert rc != 0
        assert "not found" in stderr.lower()

    def test_no_mode_specified(self, indexed_db):
        """Should fail if none of --cypher/--unhealthy/--hotspots/--stats."""
        stdout, stderr, rc = run_cli(
            "query", str(indexed_db),
        )
        assert rc != 0


# =========================================================================
# impact-graph
# =========================================================================


class TestImpactGraph:
    """Tests for the 'impact-graph' subcommand."""

    def test_impact_graph_upstream_json(self, indexed_db):
        stdout, stderr, rc = run_cli(
            "impact-graph", str(indexed_db),
            "--target", "validate_all",
            "--direction", "upstream",
            "--output", "json",
        )
        assert rc == 0, f"CLI failed: {stderr}"
        data = json.loads(stdout)
        assert "depth_1" in data
        assert "depth_2" in data
        assert "depth_3" in data
        # validate_all is called by parse_data at depth 1
        depth1_names = {e["name"] for e in data["depth_1"]}
        assert "parse_data" in depth1_names
        # parse_data is called by do_work at depth 2
        depth2_names = {e["name"] for e in data["depth_2"]}
        assert "do_work" in depth2_names

    def test_impact_graph_downstream_json(self, indexed_db):
        stdout, stderr, rc = run_cli(
            "impact-graph", str(indexed_db),
            "--target", "do_work",
            "--direction", "downstream",
            "--output", "json",
        )
        assert rc == 0, f"CLI failed: {stderr}"
        data = json.loads(stdout)
        # do_work calls parse_data (depth 1) and references CONFIG (depth 1)
        depth1_names = {e["name"] for e in data["depth_1"]}
        assert "parse_data" in depth1_names
        # parse_data calls validate_all (depth 2)
        depth2_names = {e["name"] for e in data["depth_2"]}
        assert "validate_all" in depth2_names

    def test_impact_graph_text(self, indexed_db):
        stdout, stderr, rc = run_cli(
            "impact-graph", str(indexed_db),
            "--target", "validate_all",
            "--direction", "upstream",
        )
        assert rc == 0, f"CLI failed: {stderr}"
        assert "parse_data" in stdout
        assert "depth_1" in stdout

    def test_impact_graph_custom_depth(self, indexed_db):
        stdout, stderr, rc = run_cli(
            "impact-graph", str(indexed_db),
            "--target", "validate_all",
            "--direction", "upstream",
            "--depth", "1",
            "--output", "json",
        )
        assert rc == 0, f"CLI failed: {stderr}"
        data = json.loads(stdout)
        assert "depth_1" in data
        assert "depth_2" not in data

    def test_impact_graph_nonexistent_target(self, indexed_db):
        stdout, stderr, rc = run_cli(
            "impact-graph", str(indexed_db),
            "--target", "nonexistent_symbol",
            "--output", "json",
        )
        assert rc != 0
        assert "not found" in stderr.lower()

    def test_impact_graph_nonexistent_db(self, tmp_path):
        db_path = tmp_path / "nonexistent.kuzu"
        stdout, stderr, rc = run_cli(
            "impact-graph", str(db_path),
            "--target", "anything",
        )
        assert rc != 0
        assert "not found" in stderr.lower()


# =========================================================================
# Integration: index then query
# =========================================================================


class TestIndexThenQuery:
    """End-to-end: index a sample project, then query the DB."""

    @pytest.fixture
    def sample_file(self, tmp_path):
        p = tmp_path / "sample.py"
        p.write_text('''\
"""Sample module."""

import os

def healthy_func():
    """Simple healthy function."""
    return 42

def complex_func(data):
    """A more complex function."""
    result = []
    for item in data:
        if item > 0:
            if item % 2 == 0:
                result.append(item * 2)
            else:
                result.append(item + 1)
        else:
            result.append(0)
    return result

class MyClass:
    def method_a(self):
        return healthy_func()

    def method_b(self):
        return complex_func([1, 2, 3])
''')
        return p

    def test_index_then_query_stats(self, sample_file, tmp_path):
        """Index a file, then query stats from the resulting DB."""
        db_path = tmp_path / "test_db.kuzu"

        # Step 1: Index
        stdout, stderr, rc = run_cli(
            "index", str(sample_file), "--db", str(db_path), "--output", "json",
        )
        assert rc == 0, f"Index failed: {stderr}"
        index_data = json.loads(stdout)
        assert index_data["nodes_indexed"] > 0

        # Step 2: Query stats
        stdout, stderr, rc = run_cli(
            "query", str(db_path), "--stats", "--output", "json",
        )
        assert rc == 0, f"Query stats failed: {stderr}"
        stats = json.loads(stdout)
        assert stats["total_nodes"] > 0
        assert stats["total_edges"] >= 0

    def test_index_then_query_hotspots(self, sample_file, tmp_path):
        """Index a file, then query hotspots."""
        db_path = tmp_path / "test_db.kuzu"

        # Index
        _, stderr, rc = run_cli(
            "index", str(sample_file), "--db", str(db_path), "--output", "json",
        )
        assert rc == 0, f"Index failed: {stderr}"

        # Query hotspots
        stdout, stderr, rc = run_cli(
            "query", str(db_path), "--hotspots", "--output", "json",
        )
        assert rc == 0, f"Query hotspots failed: {stderr}"
        data = json.loads(stdout)
        assert "hotspots" in data
