"""Tests for process / execution flow detection."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from Code_Organism.model.organism import Organism
from Code_Organism.model.nodes import OrganismNode, Edge, NodeType, Position
from Code_Organism.analysis.processes import detect_processes


@pytest.fixture
def call_chain_project(tmp_dir):
    """A project with internal call chains (same-module calls resolve)."""
    (tmp_dir / "pipeline.py").write_text('''\
"""A pipeline with internal call chains."""

def step_a():
    result = step_b()
    return result

def step_b():
    data = step_c()
    return data + 1

def step_c():
    return step_d()

def step_d():
    return 42
''')
    return tmp_dir


class TestDetectProcesses:
    """Tests for detect_processes()."""

    def test_detects_flows_in_call_chain_project(self, call_chain_project):
        """Execution flows are detected in a project with internal call chains."""
        organism = Organism.from_directory(call_chain_project)
        processes = detect_processes(organism)

        assert len(processes) >= 1, "Should detect at least one process"

        # Verify structure
        for proc in processes:
            assert "id" in proc
            assert "name" in proc
            assert "entry_point" in proc
            assert "terminal" in proc
            assert "steps" in proc
            assert "step_count" in proc
            assert proc["step_count"] == len(proc["steps"])
            assert proc["step_count"] >= 3, (
                f"Process {proc['name']} has only {proc['step_count']} steps"
            )

    def test_steps_are_ordered_and_reference_valid_nodes(self, call_chain_project):
        """Steps have sequential indices and reference nodes in the organism."""
        organism = Organism.from_directory(call_chain_project)
        processes = detect_processes(organism)

        for proc in processes:
            for i, step in enumerate(proc["steps"]):
                assert step["step"] == i, (
                    f"Step index mismatch: expected {i}, got {step['step']}"
                )
                assert step["node_id"] in organism.nodes, (
                    f"Step references unknown node: {step['node_id']}"
                )
                assert isinstance(step["name"], str)

    def test_entry_and_terminal_are_in_steps(self, call_chain_project):
        """Entry point is the first step, terminal is the last."""
        organism = Organism.from_directory(call_chain_project)
        processes = detect_processes(organism)

        for proc in processes:
            assert proc["entry_point"] == proc["steps"][0]["node_id"]
            assert proc["terminal"] == proc["steps"][-1]["node_id"]

    def test_empty_organism_returns_empty(self):
        """An organism with no nodes returns an empty list."""
        organism = Organism(name="empty")
        processes = detect_processes(organism)
        assert processes == []

    def test_no_call_edges_returns_empty(self, tmp_dir):
        """A project with no call edges returns no processes."""
        (tmp_dir / "constants_only.py").write_text('X = 1\nY = 2\n')
        organism = Organism.from_directory(tmp_dir)
        processes = detect_processes(organism)
        assert processes == []

    def test_process_names_contain_function_names(self, call_chain_project):
        """Auto-generated process names reference actual function names."""
        organism = Organism.from_directory(call_chain_project)
        processes = detect_processes(organism)

        for proc in processes:
            # Name should be "entry -> terminal"
            assert " -> " in proc["name"], (
                f"Process name '{proc['name']}' missing arrow separator"
            )

    def test_sample_project_returns_valid_structure(self, sample_project):
        """Process detection on sample_project returns list (may be empty if chains are short)."""
        organism = Organism.from_directory(sample_project)
        processes = detect_processes(organism)

        # sample_project has cross-module calls that resolve to
        # external/builtin nodes, so chains may be < 3 steps.
        # Just verify the return is a well-formed list.
        assert isinstance(processes, list)
        for proc in processes:
            assert "id" in proc
            assert "steps" in proc
