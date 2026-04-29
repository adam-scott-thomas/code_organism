"""Tests for the parser dispatcher (routing files to the correct backend)."""


from Code_Organism.model.nodes import Edge, NodeType, OrganismNode
from Code_Organism.parser.dispatcher import parse_file, resolve_cross_file_calls


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


# ── Cross-file resolution ────────────────────────────────────────────


class TestCrossFileResolution:
    """resolve_cross_file_calls retargets BUILTIN edges to real defs."""

    def test_js_cross_file_calls_resolved(self, cross_file_js_project):
        """app.js calls formatName/calculateTotal defined in utils.js.

        Before resolution: call edges point to BUILTIN nodes.
        After resolution: call edges point to the real FUNCTION nodes.
        """
        all_nodes = []
        all_edges = []

        for fname in ("utils.js", "app.js"):
            nodes, edges = parse_file(str(cross_file_js_project / fname))
            all_nodes.extend(nodes)
            all_edges.extend(edges)

        # Before resolution, there should be BUILTIN nodes for the callees
        builtin_names_before = {
            n.name for n in all_nodes if n.node_type == NodeType.BUILTIN
        }
        # formatName and calculateTotal should be BUILTIN in app.js's parse
        assert "formatName" in builtin_names_before or "calculateTotal" in builtin_names_before, (
            f"Expected cross-file calls to create BUILTIN nodes, got: {builtin_names_before}"
        )

        # Run cross-file resolution
        resolve_cross_file_calls(all_nodes, all_edges)

        # After resolution, BUILTIN nodes for formatName/calculateTotal
        # should be removed (they have real FUNCTION defs in utils.js)
        builtin_names_after = {
            n.name for n in all_nodes if n.node_type == NodeType.BUILTIN
        }
        assert "formatName" not in builtin_names_after
        assert "calculateTotal" not in builtin_names_after

        # The call edges should now point to the actual FUNCTION node IDs
        func_ids = {
            n.id for n in all_nodes
            if n.node_type == NodeType.FUNCTION
            and n.name in ("formatName", "calculateTotal")
        }
        call_targets = {
            e.target_id for e in all_edges if e.edge_type == "call"
        }
        # Both real function IDs should appear as call targets
        assert func_ids.issubset(call_targets), (
            f"Expected resolved targets {func_ids} in call targets {call_targets}"
        )

    def test_python_cross_file_calls_resolved(self, cross_file_python_project):
        """runner.py calls compute/transform defined in helpers.py."""
        all_nodes = []
        all_edges = []

        for fname in ("helpers.py", "runner.py"):
            nodes, edges = parse_file(str(cross_file_python_project / fname))
            all_nodes.extend(nodes)
            all_edges.extend(edges)

        resolve_cross_file_calls(all_nodes, all_edges)

        # compute and transform should NOT be BUILTIN after resolution
        builtin_names = {
            n.name for n in all_nodes if n.node_type == NodeType.BUILTIN
        }
        assert "compute" not in builtin_names
        assert "transform" not in builtin_names

    def test_no_resolution_for_truly_external_calls(self, cross_file_js_project):
        """console.log should remain as a BUILTIN (no definition in project)."""
        all_nodes = []
        all_edges = []

        for fname in ("utils.js", "app.js"):
            nodes, edges = parse_file(str(cross_file_js_project / fname))
            all_nodes.extend(nodes)
            all_edges.extend(edges)

        resolve_cross_file_calls(all_nodes, all_edges)

        # console.log -> "log" should still be BUILTIN (no def for "log")
        builtin_names = {
            n.name for n in all_nodes if n.node_type == NodeType.BUILTIN
        }
        assert "log" in builtin_names

    def test_ambiguous_names_not_resolved(self):
        """When two files define the same function name, resolution is skipped."""
        # Manually create nodes that simulate ambiguity
        func_a = OrganismNode(
            id=OrganismNode.generate_id("fileA:doWork", NodeType.FUNCTION),
            name="doWork",
            node_type=NodeType.FUNCTION,
            qualified_name="fileA:doWork",
        )
        func_b = OrganismNode(
            id=OrganismNode.generate_id("fileB:doWork", NodeType.FUNCTION),
            name="doWork",
            node_type=NodeType.FUNCTION,
            qualified_name="fileB:doWork",
        )
        builtin = OrganismNode(
            id=OrganismNode.generate_id("doWork", NodeType.BUILTIN),
            name="doWork",
            node_type=NodeType.BUILTIN,
            qualified_name="doWork",
        )
        caller = OrganismNode(
            id=OrganismNode.generate_id("fileC:main", NodeType.FUNCTION),
            name="main",
            node_type=NodeType.FUNCTION,
            qualified_name="fileC:main",
        )
        edge = Edge(
            id=Edge.generate_id(caller.id, builtin.id, "call"),
            source_id=caller.id,
            target_id=builtin.id,
            edge_type="call",
        )

        all_nodes = [func_a, func_b, builtin, caller]
        all_edges = [edge]

        resolve_cross_file_calls(all_nodes, all_edges)

        # Edge should still point to BUILTIN (ambiguous -> not resolved)
        assert edge.target_id == builtin.id
        # BUILTIN node should still exist
        assert builtin in all_nodes

    def test_resolution_does_not_affect_non_call_edges(self):
        """Import and reference edges are never retargeted."""
        func = OrganismNode(
            id=OrganismNode.generate_id("mod:helper", NodeType.FUNCTION),
            name="helper",
            node_type=NodeType.FUNCTION,
            qualified_name="mod:helper",
        )
        builtin = OrganismNode(
            id=OrganismNode.generate_id("helper", NodeType.BUILTIN),
            name="helper",
            node_type=NodeType.BUILTIN,
            qualified_name="helper",
        )
        module = OrganismNode(
            id=OrganismNode.generate_id("other", NodeType.MODULE),
            name="other",
            node_type=NodeType.MODULE,
            qualified_name="other",
        )
        import_edge = Edge(
            id=Edge.generate_id(module.id, builtin.id, "import"),
            source_id=module.id,
            target_id=builtin.id,
            edge_type="import",
        )

        all_nodes = [func, builtin, module]
        all_edges = [import_edge]

        resolve_cross_file_calls(all_nodes, all_edges)

        # Import edge should NOT be retargeted
        assert import_edge.target_id == builtin.id

    def test_orphaned_builtins_removed(self):
        """BUILTIN nodes with no remaining inbound edges are cleaned up."""
        func = OrganismNode(
            id=OrganismNode.generate_id("lib:compute", NodeType.FUNCTION),
            name="compute",
            node_type=NodeType.FUNCTION,
            qualified_name="lib:compute",
        )
        builtin = OrganismNode(
            id=OrganismNode.generate_id("compute", NodeType.BUILTIN),
            name="compute",
            node_type=NodeType.BUILTIN,
            qualified_name="compute",
        )
        caller = OrganismNode(
            id=OrganismNode.generate_id("app:run", NodeType.FUNCTION),
            name="run",
            node_type=NodeType.FUNCTION,
            qualified_name="app:run",
        )
        edge = Edge(
            id=Edge.generate_id(caller.id, builtin.id, "call"),
            source_id=caller.id,
            target_id=builtin.id,
            edge_type="call",
        )

        all_nodes = [func, builtin, caller]
        all_edges = [edge]

        resolve_cross_file_calls(all_nodes, all_edges)

        # Edge should now point to the real function
        assert edge.target_id == func.id
        # BUILTIN node should be removed (no more edges point to it)
        assert builtin not in all_nodes
        # Real function should still be there
        assert func in all_nodes
