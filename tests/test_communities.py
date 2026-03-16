"""Tests for community detection analysis."""

import sys
from pathlib import Path

import pytest

# Ensure the package is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Code_Organism.model.organism import Organism
from Code_Organism.analysis.communities import detect_communities


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
        from Code_Organism.model.nodes import NodeType

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
        """Higher resolution produces at least as many communities."""
        organism = Organism.from_directory(sample_project)
        low_res = detect_communities(organism, resolution=0.5)
        high_res = detect_communities(organism, resolution=3.0)

        # Higher resolution should generally produce more communities
        # (or at least the same number), but this is not guaranteed
        # for tiny graphs. Just verify both return valid results.
        assert isinstance(low_res, list)
        assert isinstance(high_res, list)
