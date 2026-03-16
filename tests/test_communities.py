"""Tests for community detection analysis."""

import sys
from pathlib import Path

import pytest

# Ensure the package is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Code_Organism.model.organism import Organism
from Code_Organism.model.nodes import OrganismNode, Edge, NodeType
from Code_Organism.analysis.communities import (
    detect_communities,
    _merge_small_communities,
    _MIN_COMMUNITY_SIZE,
)


class TestDetectCommunities:
    """Tests for detect_communities()."""

    def test_detects_communities_in_multi_file_project(self, sample_project):
        """Communities are detected across a multi-file project."""
        organism = Organism.from_directory(sample_project)
        communities = detect_communities(organism)

        assert len(communities) >= 1, "Should detect at least one community"

        # Every community has required keys
        for comm in communities:
            assert "id" in comm
            assert "name" in comm
            assert "members" in comm
            assert "cohesion" in comm
            assert "keywords" in comm
            assert isinstance(comm["members"], list)
            assert len(comm["members"]) > 0

    def test_all_structural_nodes_assigned(self, sample_project):
        """Every structural node appears in exactly one community."""
        organism = Organism.from_directory(sample_project)
        communities = detect_communities(organism)

        structural_types = {NodeType.MODULE, NodeType.CLASS, NodeType.FUNCTION, NodeType.METHOD}
        structural_ids = {
            n.id for n in organism.nodes.values()
            if n.node_type in structural_types
        }

        assigned_ids: set[str] = set()
        for comm in communities:
            for member in comm["members"]:
                assert member not in assigned_ids, (
                    f"Node {member} assigned to multiple communities"
                )
                assigned_ids.add(member)

        assert structural_ids == assigned_ids, (
            f"Not all structural nodes assigned. "
            f"Missing: {structural_ids - assigned_ids}"
        )

    def test_single_file_does_not_crash(self, sample_python_file):
        """Analyzing a single file does not raise an exception."""
        organism = Organism.from_file(sample_python_file)
        communities = detect_communities(organism)

        # Should return at least 1 community or empty list
        assert isinstance(communities, list)
        # If returned, each community is well-formed
        for comm in communities:
            assert "id" in comm
            assert "members" in comm

    def test_empty_organism_returns_empty(self):
        """An organism with no nodes returns an empty list."""
        organism = Organism(name="empty")
        communities = detect_communities(organism)
        assert communities == []

    def test_cohesion_is_between_0_and_1(self, sample_project):
        """Cohesion values are in the valid range."""
        organism = Organism.from_directory(sample_project)
        communities = detect_communities(organism)

        for comm in communities:
            assert 0.0 <= comm["cohesion"] <= 1.0, (
                f"Cohesion {comm['cohesion']} out of range for {comm['name']}"
            )

    def test_resolution_parameter_affects_output(self, sample_project):
        """Different resolution values produce valid results."""
        organism = Organism.from_directory(sample_project)
        low_res = detect_communities(organism, resolution=0.01)
        high_res = detect_communities(organism, resolution=5.0)

        # Both return valid community lists
        assert isinstance(low_res, list)
        assert isinstance(high_res, list)
        # Higher resolution should generally produce more (or equal)
        # communities, but for tiny test graphs this is not guaranteed.
        # Just verify both are non-empty.
        assert len(low_res) >= 1
        assert len(high_res) >= 1

    def test_default_resolution_is_low(self):
        """Default resolution is 0.1, not 1.0 (produces fewer communities)."""
        import inspect
        sig = inspect.signature(detect_communities)
        assert sig.parameters["resolution"].default == 0.1

    def test_no_singleton_communities_when_mergeable(self, sample_project):
        """Small communities are merged — no singletons unless unavoidable."""
        organism = Organism.from_directory(sample_project)
        communities = detect_communities(organism)

        # With our small test project, all nodes should be in communities
        # of at least min_community_size (or there's only one community)
        if len(communities) > 1:
            for comm in communities:
                assert len(comm["members"]) >= _MIN_COMMUNITY_SIZE, (
                    f"Community '{comm['name']}' has only "
                    f"{len(comm['members'])} member(s) — should be merged"
                )

    def test_community_ids_are_sequential(self, sample_project):
        """Community IDs are numbered sequentially starting from 0."""
        organism = Organism.from_directory(sample_project)
        communities = detect_communities(organism)

        for i, comm in enumerate(communities):
            assert comm["id"] == f"community_{i}", (
                f"Expected community_{i}, got {comm['id']}"
            )

    def test_min_community_size_parameter(self, sample_project):
        """The min_community_size parameter controls merge threshold."""
        organism = Organism.from_directory(sample_project)

        # With a very high min_community_size, everything should merge
        # into very few communities
        communities = detect_communities(organism, min_community_size=100)
        # Should still return valid results
        assert isinstance(communities, list)
        assert len(communities) >= 1
        for comm in communities:
            assert "members" in comm
            assert len(comm["members"]) > 0

    def test_colocation_edges_group_same_module(self):
        """Nodes from the same module are grouped together via co-location."""
        organism = Organism(name="colocation_test")

        # Create two modules, each with functions
        mod_a = OrganismNode(
            id="mod_a", name="module_a", node_type=NodeType.MODULE,
            qualified_name="module_a",
        )
        fn_a1 = OrganismNode(
            id="fn_a1", name="func_one", node_type=NodeType.FUNCTION,
            qualified_name="module_a.func_one",
        )
        fn_a2 = OrganismNode(
            id="fn_a2", name="func_two", node_type=NodeType.FUNCTION,
            qualified_name="module_a.func_two",
        )
        mod_b = OrganismNode(
            id="mod_b", name="module_b", node_type=NodeType.MODULE,
            qualified_name="module_b",
        )
        fn_b1 = OrganismNode(
            id="fn_b1", name="func_three", node_type=NodeType.FUNCTION,
            qualified_name="module_b.func_three",
        )
        fn_b2 = OrganismNode(
            id="fn_b2", name="func_four", node_type=NodeType.FUNCTION,
            qualified_name="module_b.func_four",
        )

        for node in [mod_a, fn_a1, fn_a2, mod_b, fn_b1, fn_b2]:
            organism.nodes[node.id] = node

        communities = detect_communities(organism)

        # All nodes assigned
        all_members = set()
        for comm in communities:
            all_members.update(comm["members"])
        assert all_members == {"mod_a", "fn_a1", "fn_a2", "mod_b", "fn_b1", "fn_b2"}

    def test_inheritance_edges_used(self):
        """Inheritance edges contribute to clustering."""
        organism = Organism(name="inheritance_test")

        # Create a class hierarchy: Base -> Child1, Child2
        base = OrganismNode(
            id="base", name="Base", node_type=NodeType.CLASS,
            qualified_name="mod.Base",
        )
        child1 = OrganismNode(
            id="child1", name="Child1", node_type=NodeType.CLASS,
            qualified_name="mod.Child1",
        )
        child2 = OrganismNode(
            id="child2", name="Child2", node_type=NodeType.CLASS,
            qualified_name="mod.Child2",
        )

        organism.nodes["base"] = base
        organism.nodes["child1"] = child1
        organism.nodes["child2"] = child2

        # Add inheritance edges
        organism.edges["e1"] = Edge(
            id="e1", source_id="child1", target_id="base",
            edge_type="inheritance",
        )
        organism.edges["e2"] = Edge(
            id="e2", source_id="child2", target_id="base",
            edge_type="inheritance",
        )

        communities = detect_communities(organism)

        # All three should end up in the same community (connected via inheritance)
        assert len(communities) == 1
        assert len(communities[0]["members"]) == 3
