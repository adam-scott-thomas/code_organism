"""Tests for the tree-sitter multi-language parser."""

import pytest

from Code_Organism.model.nodes import Edge, NodeType, OrganismNode
from Code_Organism.parser.tree_sitter_parser import TreeSitterParser


@pytest.fixture
def parser():
    return TreeSitterParser()


# ── JavaScript ───────────────────────────────────────────────────────

class TestJavaScript:
    """Parsing JavaScript files."""

    def test_finds_class_and_helper(self, parser, sample_js_file):
        nodes, edges = parser.parse_file(str(sample_js_file))
        names = {n.name for n in nodes}
        assert "FileProcessor" in names, f"Expected FileProcessor in {names}"
        assert "helper" in names, f"Expected helper in {names}"

    def test_nodes_are_organism_nodes(self, parser, sample_js_file):
        nodes, _ = parser.parse_file(str(sample_js_file))
        for node in nodes:
            assert isinstance(node, OrganismNode)

    def test_class_has_correct_type(self, parser, sample_js_file):
        nodes, _ = parser.parse_file(str(sample_js_file))
        class_node = next(n for n in nodes if n.name == "FileProcessor")
        assert class_node.node_type == NodeType.CLASS

    def test_function_has_correct_type(self, parser, sample_js_file):
        nodes, _ = parser.parse_file(str(sample_js_file))
        func_node = next(n for n in nodes if n.name == "helper")
        assert func_node.node_type == NodeType.FUNCTION

    def test_methods_extracted(self, parser, sample_js_file):
        nodes, _ = parser.parse_file(str(sample_js_file))
        method_names = {n.name for n in nodes if n.node_type == NodeType.METHOD}
        assert "constructor" in method_names
        assert "process" in method_names

    def test_import_edge_created(self, parser, sample_js_file):
        nodes, edges = parser.parse_file(str(sample_js_file))
        import_edges = [e for e in edges if e.edge_type == "import"]
        assert len(import_edges) >= 1
        # Should have an import for fs/promises
        ext_nodes = {n.name for n in nodes if n.node_type == NodeType.EXTERNAL_MODULE}
        assert "fs/promises" in ext_nodes

    def test_call_edges_detected(self, parser, sample_js_file):
        nodes, edges = parser.parse_file(str(sample_js_file))
        call_edges = [e for e in edges if e.edge_type == "call"]
        assert len(call_edges) >= 1, "Expected at least one call edge"

    def test_same_file_function_call_resolved(self, parser, tmp_dir):
        """foo() calling bar() in the same file resolves to bar's node."""
        p = tmp_dir / "calls.js"
        p.write_text('''\
function bar() { return 1; }

function foo() { return bar(); }
''')
        nodes, edges = parser.parse_file(str(p))
        bar_node = next(n for n in nodes if n.name == "bar")
        foo_node = next(n for n in nodes if n.name == "foo")

        # There should be a call edge from foo -> bar
        call_edges = [
            e for e in edges
            if e.edge_type == "call"
            and e.source_id == foo_node.id
            and e.target_id == bar_node.id
        ]
        assert len(call_edges) == 1, (
            f"Expected foo->bar call edge, got edges: "
            f"{[(e.source_id[:8], e.target_id[:8]) for e in edges if e.edge_type == 'call']}"
        )
        # bar should NOT appear as a BUILTIN node
        builtin_names = {n.name for n in nodes if n.node_type == NodeType.BUILTIN}
        assert "bar" not in builtin_names

    def test_same_file_method_call_resolved(self, parser, tmp_dir):
        """obj.process() resolves to the class method in the same file."""
        p = tmp_dir / "methods.js"
        p.write_text('''\
class Worker {
    process() { return 42; }
}

function run() {
    const w = new Worker();
    return w.process();
}
''')
        nodes, edges = parser.parse_file(str(p))
        process_node = next(
            n for n in nodes if n.name == "process" and n.node_type == NodeType.METHOD
        )
        run_node = next(n for n in nodes if n.name == "run")

        # There should be a call edge from run -> process (the method)
        call_to_process = [
            e for e in edges
            if e.edge_type == "call"
            and e.source_id == run_node.id
            and e.target_id == process_node.id
        ]
        assert len(call_to_process) == 1, (
            "Expected run->Worker.process call edge"
        )
        # process should NOT be BUILTIN
        builtin_names = {n.name for n in nodes if n.node_type == NodeType.BUILTIN}
        assert "process" not in builtin_names

    def test_module_node_created(self, parser, sample_js_file):
        nodes, _ = parser.parse_file(str(sample_js_file))
        module_nodes = [n for n in nodes if n.node_type == NodeType.MODULE]
        assert len(module_nodes) == 1
        assert module_nodes[0].name == "sample"

    def test_position_info(self, parser, sample_js_file):
        nodes, _ = parser.parse_file(str(sample_js_file))
        class_node = next(n for n in nodes if n.name == "FileProcessor")
        assert class_node.position is not None
        assert class_node.position.line > 0
        assert class_node.position.file == str(sample_js_file)

    def test_edges_are_edge_instances(self, parser, sample_js_file):
        _, edges = parser.parse_file(str(sample_js_file))
        for edge in edges:
            assert isinstance(edge, Edge)


# ── Rust ─────────────────────────────────────────────────────────────

class TestRust:
    """Parsing Rust files."""

    def test_finds_structs_and_functions(self, parser, sample_rust_file):
        nodes, _ = parser.parse_file(str(sample_rust_file))
        names = {n.name for n in nodes}
        assert "Config" in names, f"Expected Config in {names}"
        assert "helper" in names, f"Expected helper in {names}"

    def test_struct_is_class_type(self, parser, sample_rust_file):
        nodes, _ = parser.parse_file(str(sample_rust_file))
        config = next(n for n in nodes if n.name == "Config")
        assert config.node_type == NodeType.CLASS

    def test_enum_extracted(self, parser, sample_rust_file):
        nodes, _ = parser.parse_file(str(sample_rust_file))
        color = next(n for n in nodes if n.name == "Color")
        assert color.node_type == NodeType.CLASS

    def test_impl_methods_extracted(self, parser, sample_rust_file):
        nodes, _ = parser.parse_file(str(sample_rust_file))
        method_names = {n.name for n in nodes if n.node_type == NodeType.METHOD}
        assert "new" in method_names, f"Expected 'new' in {method_names}"
        assert "process" in method_names, f"Expected 'process' in {method_names}"

    def test_impl_methods_parented_to_struct(self, parser, sample_rust_file):
        nodes, _ = parser.parse_file(str(sample_rust_file))
        config = next(n for n in nodes if n.name == "Config" and n.node_type == NodeType.CLASS)
        new_method = next(n for n in nodes if n.name == "new" and n.node_type == NodeType.METHOD)
        assert new_method.parent_id == config.id

    def test_standalone_function(self, parser, sample_rust_file):
        nodes, _ = parser.parse_file(str(sample_rust_file))
        helper = next(n for n in nodes if n.name == "helper")
        assert helper.node_type == NodeType.FUNCTION

    def test_use_import(self, parser, sample_rust_file):
        nodes, edges = parser.parse_file(str(sample_rust_file))
        import_edges = [e for e in edges if e.edge_type == "import"]
        assert len(import_edges) >= 1


# ── Go ───────────────────────────────────────────────────────────────

class TestGo:
    """Parsing Go files."""

    def test_finds_struct_and_function(self, parser, sample_go_file):
        nodes, _ = parser.parse_file(str(sample_go_file))
        names = {n.name for n in nodes}
        assert "Config" in names
        assert "helper" in names

    def test_method_extracted(self, parser, sample_go_file):
        nodes, _ = parser.parse_file(str(sample_go_file))
        method_names = {n.name for n in nodes if n.node_type == NodeType.METHOD}
        assert "Process" in method_names

    def test_import_detected(self, parser, sample_go_file):
        nodes, edges = parser.parse_file(str(sample_go_file))
        import_edges = [e for e in edges if e.edge_type == "import"]
        assert len(import_edges) >= 1


# ── Java ─────────────────────────────────────────────────────────────

class TestJava:
    """Parsing Java files."""

    def test_finds_class(self, parser, sample_java_file):
        nodes, _ = parser.parse_file(str(sample_java_file))
        class_names = {n.name for n in nodes if n.node_type == NodeType.CLASS}
        assert "Config" in class_names

    def test_methods_extracted(self, parser, sample_java_file):
        nodes, _ = parser.parse_file(str(sample_java_file))
        method_names = {n.name for n in nodes if n.node_type == NodeType.METHOD}
        assert "Config" in method_names  # constructor
        assert "getName" in method_names

    def test_import_detected(self, parser, sample_java_file):
        nodes, edges = parser.parse_file(str(sample_java_file))
        import_edges = [e for e in edges if e.edge_type == "import"]
        assert len(import_edges) >= 1


# ── C ────────────────────────────────────────────────────────────────

class TestC:
    """Parsing C files."""

    def test_finds_struct_and_functions(self, parser, sample_c_file):
        nodes, _ = parser.parse_file(str(sample_c_file))
        names = {n.name for n in nodes}
        assert "Config" in names
        assert "process" in names
        assert "main" in names

    def test_include_detected(self, parser, sample_c_file):
        nodes, edges = parser.parse_file(str(sample_c_file))
        import_edges = [e for e in edges if e.edge_type == "import"]
        assert len(import_edges) >= 1
        ext_names = {n.name for n in nodes if n.node_type == NodeType.EXTERNAL_MODULE}
        assert "stdio.h" in ext_names


# ── Unsupported extension ───────────────────────────────────────────

class TestUnsupported:
    """Unsupported file extensions return empty results."""

    def test_txt_returns_empty(self, parser, tmp_dir):
        p = tmp_dir / "readme.txt"
        p.write_text("hello world")
        nodes, edges = parser.parse_file(str(p))
        assert nodes == []
        assert edges == []

    def test_md_returns_empty(self, parser, tmp_dir):
        p = tmp_dir / "README.md"
        p.write_text("# Hello")
        nodes, edges = parser.parse_file(str(p))
        assert nodes == []
        assert edges == []

    def test_supports_method(self, parser, tmp_dir):
        assert parser.supports("app.js")
        assert parser.supports("main.rs")
        assert not parser.supports("readme.txt")
        assert not parser.supports("notes.md")


# ── Node ID generation ──────────────────────────────────────────────

class TestNodeIds:
    """Node IDs are deterministic and consistent."""

    def test_ids_are_hex_strings(self, parser, sample_js_file):
        nodes, _ = parser.parse_file(str(sample_js_file))
        for node in nodes:
            assert len(node.id) == 16
            int(node.id, 16)  # Should not raise

    def test_ids_are_unique(self, parser, sample_js_file):
        nodes, _ = parser.parse_file(str(sample_js_file))
        ids = [n.id for n in nodes]
        assert len(ids) == len(set(ids)), "Duplicate node IDs found"

    def test_ids_are_deterministic(self, parser, sample_js_file):
        nodes1, _ = parser.parse_file(str(sample_js_file))
        nodes2, _ = parser.parse_file(str(sample_js_file))
        ids1 = sorted(n.id for n in nodes1)
        ids2 = sorted(n.id for n in nodes2)
        assert ids1 == ids2
