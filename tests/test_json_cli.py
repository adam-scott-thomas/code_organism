"""Tests for the refactored CLI with --output json and subcommands."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

# Path to the Code_Organism package root (parent of tests/)
PKG_ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = PKG_ROOT.parent  # D:\lost_marbles


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


# =========================================================================
# Fixtures
# =========================================================================


@pytest.fixture
def sample_file(tmp_path):
    """A simple Python file for CLI tests."""
    p = tmp_path / "sample.py"
    p.write_text('''\
"""Sample module."""

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


def helper(x: int, y: int) -> int:
    """Add two numbers."""
    if x < 0:
        x = 0
    return x + y
''')
    return p


@pytest.fixture
def sample_project(tmp_path, sample_file):
    """A small multi-file project."""
    (tmp_path / "utils.py").write_text('''\
"""Utility functions."""

def validate(value: str) -> bool:
    return len(value) > 0

def format_output(data: dict) -> str:
    return str(data)
''')
    return tmp_path


# =========================================================================
# Subcommand: analyze
# =========================================================================


class TestAnalyzeSubcommand:
    """Tests for 'analyze' subcommand."""

    def test_analyze_json_returns_valid_json(self, sample_file):
        stdout, stderr, rc = run_cli("analyze", str(sample_file), "--output", "json")
        assert rc == 0, f"CLI failed: {stderr}"
        data = json.loads(stdout)
        assert "nodes" in data
        assert "edges" in data
        assert "stats" in data

    def test_analyze_json_has_node_fields(self, sample_file):
        stdout, _, rc = run_cli("analyze", str(sample_file), "--output", "json")
        assert rc == 0
        data = json.loads(stdout)
        assert len(data["nodes"]) > 0
        node = data["nodes"][0]
        assert "id" in node
        assert "name" in node
        assert "type" in node
        assert "health_status" in node
        assert "health_score" in node

    def test_analyze_json_has_stats_fields(self, sample_file):
        stdout, _, rc = run_cli("analyze", str(sample_file), "--output", "json")
        assert rc == 0
        data = json.loads(stdout)
        stats = data["stats"]
        assert "total_nodes" in stats
        assert "total_modules" in stats
        assert "total_classes" in stats
        assert "total_functions" in stats
        assert isinstance(stats["total_nodes"], int)
        assert stats["total_nodes"] > 0

    def test_analyze_json_has_edges(self, sample_file):
        stdout, _, rc = run_cli("analyze", str(sample_file), "--output", "json")
        assert rc == 0
        data = json.loads(stdout)
        # Edges list should exist (may be empty for simple files)
        assert isinstance(data["edges"], list)

    def test_analyze_text_mode(self, sample_file):
        """Default (no --output) should produce text, not JSON."""
        stdout, stderr, rc = run_cli("analyze", str(sample_file))
        assert rc == 0
        # Should NOT be valid JSON
        with pytest.raises(json.JSONDecodeError):
            json.loads(stdout)
        # Should contain the text table
        assert "ORGANISM ANALYSIS" in stdout

    def test_analyze_directory(self, sample_project):
        stdout, _, rc = run_cli("analyze", str(sample_project), "--output", "json")
        assert rc == 0
        data = json.loads(stdout)
        assert data["stats"]["total_modules"] >= 2

    def test_analyze_nonexistent_path(self, tmp_path):
        stdout, stderr, rc = run_cli("analyze", str(tmp_path / "nope.py"), "--output", "json")
        assert rc != 0


# =========================================================================
# Subcommand: health
# =========================================================================


class TestHealthSubcommand:
    """Tests for 'health' subcommand."""

    def test_health_json_returns_valid_json(self, sample_file):
        stdout, stderr, rc = run_cli("health", str(sample_file), "--output", "json")
        assert rc == 0, f"CLI failed: {stderr}"
        data = json.loads(stdout)
        assert "health_summary" in data
        assert "nodes" in data

    def test_health_json_summary_keys(self, sample_file):
        stdout, _, rc = run_cli("health", str(sample_file), "--output", "json")
        assert rc == 0
        data = json.loads(stdout)
        summary = data["health_summary"]
        assert "healthy" in summary
        assert "stressed" in summary
        assert "inflamed" in summary
        assert "necrotic" in summary
        assert "cancerous" in summary
        # Values should be floats between 0 and 1
        for v in summary.values():
            assert 0.0 <= v <= 1.0

    def test_health_json_node_fields(self, sample_file):
        stdout, _, rc = run_cli("health", str(sample_file), "--output", "json")
        assert rc == 0
        data = json.loads(stdout)
        assert len(data["nodes"]) > 0
        node = data["nodes"][0]
        assert "name" in node
        assert "qualified_name" in node
        assert "health_status" in node
        assert "health_score" in node

    def test_health_text_mode(self, sample_file):
        stdout, _, rc = run_cli("health", str(sample_file))
        assert rc == 0
        with pytest.raises(json.JSONDecodeError):
            json.loads(stdout)
        assert "Health Summary" in stdout


# =========================================================================
# Legacy: --stats --output json
# =========================================================================


class TestLegacyStatsJson:
    """Tests for legacy CLI with --output json."""

    def test_stats_json(self, sample_file):
        stdout, stderr, rc = run_cli(str(sample_file), "--stats", "--output", "json")
        assert rc == 0, f"CLI failed: {stderr}"
        data = json.loads(stdout)
        assert "nodes" in data
        assert "edges" in data
        assert "stats" in data
        assert data["stats"]["total_nodes"] > 0

    def test_stats_text_default(self, sample_file):
        """Without --output json, --stats should produce text."""
        stdout, _, rc = run_cli(str(sample_file), "--stats")
        assert rc == 0
        with pytest.raises(json.JSONDecodeError):
            json.loads(stdout)
        assert "ORGANISM ANALYSIS" in stdout


# =========================================================================
# Legacy: --malware-scan --output json
# =========================================================================


class TestLegacyMalwareScanJson:
    """Tests for legacy --malware-scan with --output json."""

    def test_malware_scan_json(self, sample_file):
        stdout, stderr, rc = run_cli(str(sample_file), "--malware-scan", "--output", "json")
        assert rc == 0, f"CLI failed: {stderr}"
        data = json.loads(stdout)
        assert "overall_risk" in data
        assert "is_likely_malware" in data
        assert "markers" in data
        assert isinstance(data["overall_risk"], (int, float))
        assert isinstance(data["is_likely_malware"], bool)
        assert isinstance(data["markers"], list)

    def test_malware_scan_clean_file(self, tmp_path):
        """A clean file should have low/zero risk."""
        clean = tmp_path / "clean.py"
        clean.write_text('def hello():\n    return "hi"\n')
        stdout, _, rc = run_cli(str(clean), "--malware-scan", "--output", "json")
        assert rc == 0
        data = json.loads(stdout)
        assert data["overall_risk"] == 0.0
        assert data["is_likely_malware"] is False

    def test_malware_scan_text_default(self, sample_file):
        stdout, _, rc = run_cli(str(sample_file), "--malware-scan")
        assert rc == 0
        with pytest.raises(json.JSONDecodeError):
            json.loads(stdout)
        assert "Scan complete" in stdout


# =========================================================================
# Legacy: --complexity --output json
# =========================================================================


class TestLegacyComplexityJson:
    """Tests for legacy --complexity with --output json."""

    def test_complexity_json(self, sample_file):
        stdout, stderr, rc = run_cli(str(sample_file), "--complexity", "--output", "json")
        assert rc == 0, f"CLI failed: {stderr}"
        data = json.loads(stdout)
        assert "complexity" in data
        assert isinstance(data["complexity"], list)

    def test_complexity_json_fields(self, sample_file):
        stdout, _, rc = run_cli(str(sample_file), "--complexity", "--output", "json")
        assert rc == 0
        data = json.loads(stdout)
        assert len(data["complexity"]) > 0
        item = data["complexity"][0]
        assert "name" in item
        assert "location" in item
        assert "cyclomatic" in item
        assert "cognitive" in item
        assert "maintainability_index" in item

    def test_complexity_text_default(self, sample_file):
        stdout, _, rc = run_cli(str(sample_file), "--complexity")
        assert rc == 0
        with pytest.raises(json.JSONDecodeError):
            json.loads(stdout)
        assert "COMPLEXITY REPORT" in stdout


# =========================================================================
# --version
# =========================================================================


class TestVersion:
    """Tests for --version flag."""

    def test_version_flag(self):
        stdout, stderr, rc = run_cli("--version")
        # argparse may print to stdout or stderr depending on version
        combined = stdout + stderr
        assert "2.0.0" in combined


# =========================================================================
# Stub subcommands
# =========================================================================


class TestLiveSubcommands:
    """Tests that index/impact/communities subcommands work."""

    def test_index_runs(self, sample_file, tmp_path):
        db_path = tmp_path / ".code_organism"
        stdout, stderr, rc = run_cli("index", str(sample_file), "--db", str(db_path), "--output", "json")
        assert rc == 0
        data = json.loads(stdout)
        assert data["nodes_indexed"] > 0

    def test_impact_runs(self, sample_file):
        stdout, stderr, rc = run_cli("impact", str(sample_file), "--target", "helper", "--output", "json")
        # May exit 0 (found) or 1 (not found depending on parse)
        assert rc in (0, 1)

    def test_communities_runs(self, sample_file):
        stdout, stderr, rc = run_cli("communities", str(sample_file), "--output", "json")
        assert rc == 0
        data = json.loads(stdout)
        assert "communities" in data


# =========================================================================
# JSON output goes to stdout, progress to stderr
# =========================================================================


class TestOutputSeparation:
    """Verify that JSON goes to stdout and progress to stderr."""

    def test_analyze_json_clean_stdout(self, sample_file):
        """stdout should contain ONLY valid JSON when --output json is used."""
        stdout, stderr, rc = run_cli("analyze", str(sample_file), "--output", "json")
        assert rc == 0
        # Should parse cleanly — no stray text mixed in
        data = json.loads(stdout)
        assert isinstance(data, dict)
        # Progress info should be in stderr
        assert "Analyzing" in stderr

    def test_malware_json_clean_stdout(self, sample_file):
        stdout, stderr, rc = run_cli(str(sample_file), "--malware-scan", "--output", "json")
        assert rc == 0
        data = json.loads(stdout)
        assert isinstance(data, dict)
        assert "Scanning" in stderr

    def test_complexity_json_clean_stdout(self, sample_file):
        stdout, stderr, rc = run_cli(str(sample_file), "--complexity", "--output", "json")
        assert rc == 0
        data = json.loads(stdout)
        assert isinstance(data, dict)
        assert "Analyzing complexity" in stderr
