"""Tests for impact / blast radius analysis."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Code_Organism.analysis.impact import analyze_impact
from Code_Organism.model.nodes import Edge, NodeType, OrganismNode, Position
from Code_Organism.model.organism import Organism


class TestAnalyzeImpact:
    """Tests for analyze_impact()."""

    def test_upstream_impact_finds_callers(self, sample_project):
        """Upstream analysis finds nodes that call the target."""
        organism = Organism.from_directory(sample_project)

        # Find a function that is called by others
        # 'validate' is called by 'main' via an import edge to utils.validate
        # Let's find a node that has callers
        target_id = None
        for node in organism.nodes.values():
            if node.node_type in (NodeType.FUNCTION, NodeType.METHOD):
                # Check if something calls this node
                if node.called_by:
                    target_id = node.id
                    break

        if target_id is None:
            # Fallback: use any node that appears as a target in call edges
            for edge in organism.edges.values():
                if edge.edge_type == "call" and edge.target_id in organism.nodes:
                    target_id = edge.target_id
                    break

        if target_id is None:
            pytest.skip("No call targets found in sample project")

        result = analyze_impact(organism, target_id, direction="upstream")

        # Should have depth keys
        assert "depth_1" in result
        assert "depth_2" in result
        assert "depth_3" in result

        # At least depth_1 should have entries (since we picked a called node)
        assert len(result["depth_1"]) >= 1, (
            f"Expected callers at depth 1 for node {target_id}"
        )

        # Check entry structure
        for entry in result["depth_1"]:
            assert "node_id" in entry
            assert "name" in entry
            assert "file" in entry
            assert "edge_type" in entry

    def test_downstream_impact_finds_callees(self, sample_project):
        """Downstream analysis finds nodes that the target calls."""
        organism = Organism.from_directory(sample_project)

        # Find 'main' function which calls several things
        target_id = None
        for node in organism.nodes.values():
            if node.name == "main" and node.node_type == NodeType.FUNCTION:
                target_id = node.id
                break

        if target_id is None:
            pytest.skip("No 'main' function found in sample project")

        result = analyze_impact(organism, target_id, direction="downstream")

        assert "depth_1" in result
        # main() calls several functions, so depth_1 should be non-empty
        assert len(result["depth_1"]) >= 1, (
            "main() should have downstream dependencies"
        )

    def test_nonexistent_node_returns_empty(self, sample_project):
        """Querying a node ID that doesn't exist returns empty depth lists."""
        organism = Organism.from_directory(sample_project)

        result = analyze_impact(organism, "nonexistent_id_12345")

        assert "depth_1" in result
        assert "depth_2" in result
        assert "depth_3" in result
        assert result["depth_1"] == []
        assert result["depth_2"] == []
        assert result["depth_3"] == []

    def test_empty_organism_returns_empty(self):
        """Impact analysis on an empty organism returns empty lists."""
        organism = Organism(name="empty")
        result = analyze_impact(organism, "any_id")

        for depth in range(1, 4):
            assert result[f"depth_{depth}"] == []

    def test_max_depth_controls_output(self, sample_project):
        """Changing max_depth changes the number of depth keys."""
        organism = Organism.from_directory(sample_project)

        # Find any node
        target_id = next(iter(organism.nodes.keys()))

        result_2 = analyze_impact(organism, target_id, max_depth=2)
        result_5 = analyze_impact(organism, target_id, max_depth=5)

        assert "depth_1" in result_2
        assert "depth_2" in result_2
        assert "depth_3" not in result_2

        assert "depth_5" in result_5

    def test_impact_entries_have_valid_files(self, sample_project):
        """Impact entries include file paths from the node's position."""
        organism = Organism.from_directory(sample_project)

        # Find a node that has callers
        target_id = None
        for edge in organism.edges.values():
            if edge.edge_type == "call" and edge.target_id in organism.nodes:
                target_id = edge.target_id
                break

        if target_id is None:
            pytest.skip("No call targets found")

        result = analyze_impact(organism, target_id, direction="upstream")

        for entry in result["depth_1"]:
            # file may be empty string for builtins, but should be a string
            assert isinstance(entry["file"], str)

    def test_synthetic_graph_upstream(self):
        """Test upstream traversal on a hand-built graph."""
        organism = Organism(name="synthetic")

        # A -> B -> C (call chain)
        node_a = OrganismNode(
            id="a", name="func_a", node_type=NodeType.FUNCTION,
            qualified_name="mod.func_a",
            position=Position(file="mod.py", line=1, column=0),
        )
        node_b = OrganismNode(
            id="b", name="func_b", node_type=NodeType.FUNCTION,
            qualified_name="mod.func_b",
            position=Position(file="mod.py", line=10, column=0),
        )
        node_c = OrganismNode(
            id="c", name="func_c", node_type=NodeType.FUNCTION,
            qualified_name="mod.func_c",
            position=Position(file="mod.py", line=20, column=0),
        )

        organism.add_node(node_a)
        organism.add_node(node_b)
        organism.add_node(node_c)

        # a calls b, b calls c
        organism.add_edge(Edge(
            id="e1", source_id="a", target_id="b", edge_type="call",
        ))
        organism.add_edge(Edge(
            id="e2", source_id="b", target_id="c", edge_type="call",
        ))

        # Upstream from c: depth_1 = b, depth_2 = a
        result = analyze_impact(organism, "c", direction="upstream")
        depth1_ids = {e["node_id"] for e in result["depth_1"]}
        depth2_ids = {e["node_id"] for e in result["depth_2"]}

        assert "b" in depth1_ids
        assert "a" in depth2_ids

    def test_synthetic_graph_downstream(self):
        """Test downstream traversal on a hand-built graph."""
        organism = Organism(name="synthetic")

        node_a = OrganismNode(
            id="a", name="func_a", node_type=NodeType.FUNCTION,
            qualified_name="mod.func_a",
            position=Position(file="mod.py", line=1, column=0),
        )
        node_b = OrganismNode(
            id="b", name="func_b", node_type=NodeType.FUNCTION,
            qualified_name="mod.func_b",
            position=Position(file="mod.py", line=10, column=0),
        )
        node_c = OrganismNode(
            id="c", name="func_c", node_type=NodeType.FUNCTION,
            qualified_name="mod.func_c",
            position=Position(file="mod.py", line=20, column=0),
        )

        organism.add_node(node_a)
        organism.add_node(node_b)
        organism.add_node(node_c)

        organism.add_edge(Edge(
            id="e1", source_id="a", target_id="b", edge_type="call",
        ))
        organism.add_edge(Edge(
            id="e2", source_id="b", target_id="c", edge_type="call",
        ))

        # Downstream from a: depth_1 = b, depth_2 = c
        result = analyze_impact(organism, "a", direction="downstream")
        depth1_ids = {e["node_id"] for e in result["depth_1"]}
        depth2_ids = {e["node_id"] for e in result["depth_2"]}

        assert "b" in depth1_ids
        assert "c" in depth2_ids
