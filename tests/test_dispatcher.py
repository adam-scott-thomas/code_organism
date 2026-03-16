"""Tests for the parser dispatcher (routing files to the correct backend)."""

import pytest

from Code_Organism.model.nodes import NodeType, OrganismNode
from Code_Organism.parser.dispatcher import parse_file


class TestPythonRouting:
    """Python files route to ast_walker."""

    def test_finds_class_and_function(self, sample_python_file):
        nodes, edges = parse_file(str(sample_python_file))
        names = {n.name for n in nodes}
        assert "FileProcessor" in names
        assert "helper" in names

    def test_rich_python_features(self, sample_python_file):
        """ast_walker extracts features tree-sitter would not
        (docstrings, decorators, parameters, etc.)."""
        nodes, _ = parse_file(str(sample_python_file))

        # Module node with docstring
        module = next(n for n in nodes if n.node_type == NodeType.MODULE)
        assert module.docstring is not None

        # Class with methods
        cls = next(n for n in nodes if n.name == "FileProcessor")
        assert cls.node_type == NodeType.CLASS

        # Method parameters
        params = [n for n in nodes if n.node_type == NodeType.PARAMETER]
        param_names = {p.name for p in params}
        assert "root" in param_names or "self" in param_names

        # @property tagged
        cached = next(
            (n for n in nodes if n.name == "cached_count"), None,
        )
        if cached:
            assert "property" in cached.health_notes

    def test_import_edges(self, sample_python_file):
        _, edges = parse_file(str(sample_python_file))
        import_edges = [e for e in edges if e.edge_type == "import"]
        assert len(import_edges) >= 1


class TestJavaScriptRouting:
    """JavaScript files route to tree-sitter."""

    def test_finds_class_and_function(self, sample_js_file):
        nodes, edges = parse_file(str(sample_js_file))
        names = {n.name for n in nodes}
        assert "FileProcessor" in names
        assert "helper" in names

    def test_class_is_class_type(self, sample_js_file):
        nodes, _ = parse_file(str(sample_js_file))
        cls = next(n for n in nodes if n.name == "FileProcessor")
        assert cls.node_type == NodeType.CLASS

    def test_methods_found(self, sample_js_file):
        nodes, _ = parse_file(str(sample_js_file))
        method_names = {n.name for n in nodes if n.node_type == NodeType.METHOD}
        assert "constructor" in method_names
        assert "process" in method_names


class TestRustRouting:
    """Rust files route to tree-sitter."""

    def test_finds_structs_and_functions(self, sample_rust_file):
        nodes, _ = parse_file(str(sample_rust_file))
        names = {n.name for n in nodes}
        assert "Config" in names
        assert "helper" in names


class TestUnknownExtension:
    """Unknown extensions return empty results."""

    def test_txt_returns_empty(self, tmp_dir):
        p = tmp_dir / "data.csv"
        p.write_text("a,b,c\n1,2,3\n")
        nodes, edges = parse_file(str(p))
        assert nodes == []
        assert edges == []

    def test_no_extension_returns_empty(self, tmp_dir):
        p = tmp_dir / "Makefile"
        p.write_text("all:\n\techo hello\n")
        nodes, edges = parse_file(str(p))
        assert nodes == []
        assert edges == []
