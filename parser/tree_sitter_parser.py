"""
CODE ORGANISM: TREE-SITTER MULTI-LANGUAGE PARSER

Extends the Code Organism beyond Python by using tree-sitter
to parse JavaScript, TypeScript, Java, Go, Rust, C, and C++.

Each supported language maps its AST node types to OrganismNode
and Edge instances -- the same format as ast_walker.py -- so the
rest of the pipeline (graph, health, renderer) works identically
regardless of source language.
"""

from __future__ import annotations

import hashlib
import importlib
import logging
from pathlib import Path
from typing import Optional

import tree_sitter

from ..model.nodes import (
    Edge,
    HealthStatus,
    Metrics,
    NodeType,
    OrganismNode,
    Position,
)

logger = logging.getLogger(__name__)

# ── Language registry ────────────────────────────────────────────────
# Maps file extension -> (language key, pip package name)
# The language key is used for grammar-specific extraction rules.

LANGUAGE_MAP: dict[str, tuple[str, str]] = {
    ".js": ("javascript", "tree_sitter_javascript"),
    ".jsx": ("javascript", "tree_sitter_javascript"),
    ".mjs": ("javascript", "tree_sitter_javascript"),
    ".cjs": ("javascript", "tree_sitter_javascript"),
    ".ts": ("typescript", "tree_sitter_typescript"),
    ".tsx": ("tsx", "tree_sitter_typescript"),
    ".java": ("java", "tree_sitter_java"),
    ".go": ("go", "tree_sitter_go"),
    ".rs": ("rust", "tree_sitter_rust"),
    ".c": ("c", "tree_sitter_c"),
    ".h": ("c", "tree_sitter_c"),
    ".cpp": ("cpp", "tree_sitter_cpp"),
    ".cc": ("cpp", "tree_sitter_cpp"),
    ".cxx": ("cpp", "tree_sitter_cpp"),
    ".hpp": ("cpp", "tree_sitter_cpp"),
    ".hxx": ("cpp", "tree_sitter_cpp"),
}

# Node types in tree-sitter ASTs that map to OrganismNode types,
# keyed by language.

_FUNCTION_TYPES: dict[str, set[str]] = {
    "javascript": {"function_declaration"},
    "typescript": {"function_declaration"},
    "tsx": {"function_declaration"},
    "java": set(),  # Java only has methods inside classes
    "go": {"function_declaration"},
    "rust": {"function_item"},
    "c": {"function_definition"},
    "cpp": {"function_definition"},
}

_CLASS_TYPES: dict[str, set[str]] = {
    "javascript": {"class_declaration"},
    "typescript": {"class_declaration"},
    "tsx": {"class_declaration"},
    "java": {"class_declaration", "interface_declaration", "enum_declaration"},
    "go": set(),  # Go uses type_declaration + struct
    "rust": {"struct_item", "enum_item"},
    "c": {"struct_specifier"},
    "cpp": {"struct_specifier", "class_specifier"},
}

_METHOD_TYPES: dict[str, set[str]] = {
    "javascript": {"method_definition"},
    "typescript": {"method_definition"},
    "tsx": {"method_definition"},
    "java": {"method_declaration", "constructor_declaration"},
    "go": {"method_declaration"},
    "rust": set(),  # Rust methods are function_items inside impl_item
    "c": set(),
    "cpp": set(),
}

_IMPORT_TYPES: dict[str, set[str]] = {
    "javascript": {"import_statement"},
    "typescript": {"import_statement"},
    "tsx": {"import_statement"},
    "java": {"import_declaration"},
    "go": {"import_declaration"},
    "rust": {"use_declaration"},
    "c": {"preproc_include"},
    "cpp": {"preproc_include"},
}


def _get_language_obj(lang_key: str, package_name: str) -> tree_sitter.Language:
    """Import the grammar package and return a ``tree_sitter.Language``."""
    mod = importlib.import_module(package_name)
    if lang_key == "typescript":
        return tree_sitter.Language(mod.language_typescript())
    if lang_key == "tsx":
        return tree_sitter.Language(mod.language_tsx())
    return tree_sitter.Language(mod.language())


# ── Helper: extract name from a tree-sitter node ────────────────────

def _child_by_type(node: tree_sitter.Node, *types: str) -> Optional[tree_sitter.Node]:
    """Return the first child whose ``type`` is in *types*."""
    for child in node.children:
        if child.type in types:
            return child
    return None


def _child_text(node: tree_sitter.Node, *types: str) -> str:
    """Return the text of the first child matching any of *types*, or ``""``."""
    child = _child_by_type(node, *types)
    return child.text.decode("utf-8", errors="replace") if child else ""


def _node_name(node: tree_sitter.Node, lang_key: str) -> str:
    """Extract a human-readable name from a tree-sitter AST node.

    The tricky part: some node types (e.g. Java ``method_declaration``,
    Go ``method_declaration``) have *both* a ``type_identifier`` (return
    type) and an ``identifier`` (name).  We must prefer the actual name
    over the return type.
    """
    node_type = node.type

    # Go method_declaration: name is a field_identifier
    if lang_key == "go" and node_type == "method_declaration":
        return _child_text(node, "field_identifier")

    # Java/Go/Rust nodes that can have both identifier and type_identifier:
    # prefer identifier first, then field_identifier, then property_identifier.
    # Only fall back to type_identifier for type-definition nodes.
    if node_type in (
        "method_declaration", "constructor_declaration",
        "function_declaration", "function_item",
    ):
        name = _child_text(node, "identifier", "field_identifier", "property_identifier")
        if name:
            return name

    # For class/struct/enum definitions, type_identifier IS the name
    if node_type in (
        "class_declaration", "interface_declaration", "enum_declaration",
        "struct_item", "enum_item",
    ):
        return _child_text(node, "type_identifier", "identifier")

    # General fallback: identifier first, then type_identifier
    name = _child_text(node, "identifier", "property_identifier")
    if name:
        return name
    name = _child_text(node, "type_identifier")
    if name:
        return name

    # Go: type_declaration wraps a type_spec
    if lang_key == "go" and node_type == "type_declaration":
        spec = _child_by_type(node, "type_spec")
        if spec:
            return _child_text(spec, "type_identifier")

    # Rust: impl_item -- name is the type being implemented
    if lang_key == "rust" and node_type == "impl_item":
        return _child_text(node, "type_identifier")

    # C/C++: function_definition -> function_declarator -> identifier
    if node_type == "function_definition":
        declarator = _child_by_type(node, "function_declarator")
        if declarator:
            return _child_text(declarator, "identifier")

    return ""


# ── TreeSitterParser ─────────────────────────────────────────────────

class TreeSitterParser:
    """
    Multi-language parser backed by tree-sitter.

    Parsers are lazy-loaded per language and cached for reuse.
    """

    def __init__(self) -> None:
        self._parsers: dict[str, tree_sitter.Parser] = {}

    # ── public API ───────────────────────────────────────────────────

    def supports(self, filepath: str) -> bool:
        """Return *True* if this parser can handle *filepath*."""
        ext = Path(filepath).suffix.lower()
        return ext in LANGUAGE_MAP

    def parse_file(self, filepath: str) -> tuple[list[OrganismNode], list[Edge]]:
        """Parse *filepath* and return ``(nodes, edges)``."""
        ext = Path(filepath).suffix.lower()
        if ext not in LANGUAGE_MAP:
            return [], []

        lang_key, package_name = LANGUAGE_MAP[ext]
        parser = self._get_parser(lang_key, package_name)

        try:
            source = Path(filepath).read_bytes()
        except (OSError, IOError) as exc:
            logger.warning("Cannot read %s: %s", filepath, exc)
            return [], []

        tree = parser.parse(source)
        return self._extract(tree.root_node, filepath, lang_key)

    # ── parser cache ─────────────────────────────────────────────────

    def _get_parser(self, lang_key: str, package_name: str) -> tree_sitter.Parser:
        if lang_key not in self._parsers:
            lang_obj = _get_language_obj(lang_key, package_name)
            self._parsers[lang_key] = tree_sitter.Parser(lang_obj)
        return self._parsers[lang_key]

    # ── extraction ───────────────────────────────────────────────────

    def _extract(
        self,
        root: tree_sitter.Node,
        filepath: str,
        lang_key: str,
    ) -> tuple[list[OrganismNode], list[Edge]]:
        """Walk the tree-sitter AST and extract nodes and edges."""
        nodes: list[OrganismNode] = []
        edges: list[Edge] = []
        seen_edge_ids: set[str] = set()

        filename = str(filepath)
        file_stem = Path(filepath).stem

        # Create a module-level node for the file itself
        module_qname = file_stem
        module_node = OrganismNode(
            id=OrganismNode.generate_id(module_qname, NodeType.MODULE),
            name=file_stem,
            node_type=NodeType.MODULE,
            qualified_name=module_qname,
            position=Position(file=filename, line=1, column=0),
            metrics=Metrics(
                lines_of_code=root.end_point[0] + 1,
            ),
        )
        nodes.append(module_node)

        func_types = _FUNCTION_TYPES.get(lang_key, set())
        class_types = _CLASS_TYPES.get(lang_key, set())
        method_types = _METHOD_TYPES.get(lang_key, set())
        import_types = _IMPORT_TYPES.get(lang_key, set())

        # Collect all defined names -> node_id (for call edge resolution)
        # Both bare names ("helper") and dotted names ("Config.process")
        # are tracked so that obj.method() can resolve to the method.
        defined_names: dict[str, str] = {}

        # Track class names -> set of method names for dotted-call resolution
        class_methods: dict[str, dict[str, str]] = {}  # class_name -> {method_name -> node_id}

        def _make_node(
            name: str,
            node_type: NodeType,
            ts_node: tree_sitter.Node,
            parent_qname: str,
            parent_id: str,
        ) -> OrganismNode:
            qname = f"{parent_qname}:{name}" if parent_qname else name
            node_id = OrganismNode.generate_id(qname, node_type)
            org_node = OrganismNode(
                id=node_id,
                name=name,
                node_type=node_type,
                qualified_name=qname,
                parent_id=parent_id,
                position=Position(
                    file=filename,
                    line=ts_node.start_point[0] + 1,
                    column=ts_node.start_point[1],
                    end_line=ts_node.end_point[0] + 1,
                    end_column=ts_node.end_point[1],
                ),
                metrics=Metrics(
                    lines_of_code=ts_node.end_point[0] - ts_node.start_point[0] + 1,
                ),
                health=HealthStatus.UNKNOWN,
            )
            nodes.append(org_node)
            defined_names[name] = node_id

            # If this is a method, also register under "ClassName.method"
            if node_type == NodeType.METHOD:
                # Walk up the parent chain to find the owning class name
                parent_org = next(
                    (n for n in nodes if n.id == parent_id
                     and n.node_type == NodeType.CLASS),
                    None,
                )
                if parent_org:
                    dotted = f"{parent_org.name}.{name}"
                    defined_names[dotted] = node_id
                    if parent_org.name not in class_methods:
                        class_methods[parent_org.name] = {}
                    class_methods[parent_org.name][name] = node_id

            return org_node

        def _add_edge(source_id: str, target_id: str, edge_type: str) -> None:
            eid = Edge.generate_id(source_id, target_id, edge_type)
            if eid not in seen_edge_ids:
                seen_edge_ids.add(eid)
                edges.append(Edge(
                    id=eid,
                    source_id=source_id,
                    target_id=target_id,
                    edge_type=edge_type,
                ))

        def _extract_import_name(ts_node: tree_sitter.Node) -> str:
            """Best-effort extraction of the imported module/path name."""
            # JS/TS: import_statement contains a string child for the path
            string_node = _child_by_type(ts_node, "string")
            if string_node:
                frag = _child_by_type(string_node, "string_fragment")
                if frag:
                    return frag.text.decode("utf-8", errors="replace")
                # Fallback: strip quotes
                raw = string_node.text.decode("utf-8", errors="replace")
                return raw.strip("'\"")

            # Java: import_declaration -> scoped_identifier
            scoped = _child_by_type(ts_node, "scoped_identifier")
            if scoped:
                return scoped.text.decode("utf-8", errors="replace")

            # Go: import_declaration -> import_spec -> interpreted_string_literal
            spec = _child_by_type(ts_node, "import_spec")
            if spec:
                lit = _child_by_type(spec, "interpreted_string_literal")
                if lit:
                    content = _child_by_type(lit, "interpreted_string_literal_content")
                    if content:
                        return content.text.decode("utf-8", errors="replace")
                    return lit.text.decode("utf-8", errors="replace").strip('"')

            # Go: import_spec_list (multi-import)
            spec_list = _child_by_type(ts_node, "import_spec_list")
            if spec_list:
                # Just return the first import for now
                first_spec = _child_by_type(spec_list, "import_spec")
                if first_spec:
                    lit = _child_by_type(first_spec, "interpreted_string_literal")
                    if lit:
                        content = _child_by_type(lit, "interpreted_string_literal_content")
                        if content:
                            return content.text.decode("utf-8", errors="replace")

            # Rust: use_declaration
            if ts_node.type == "use_declaration":
                # Return everything after 'use' keyword
                for child in ts_node.children:
                    if child.type not in ("use", ";", "pub"):
                        return child.text.decode("utf-8", errors="replace")

            # C/C++: preproc_include -> system_lib_string or string_literal
            for child_type in ("system_lib_string", "string_literal"):
                child = _child_by_type(ts_node, child_type)
                if child:
                    return child.text.decode("utf-8", errors="replace").strip("<>\"")

            return ts_node.text.decode("utf-8", errors="replace")[:60]

        def _collect_calls(
            ts_node: tree_sitter.Node,
            caller_id: str,
        ) -> None:
            """Recursively find call_expression nodes and create edges."""
            if ts_node.type == "call_expression":
                callee_name = _resolve_callee(ts_node)
                if callee_name:
                    target_id = _resolve_call_target(ts_node, callee_name)
                    if target_id:
                        _add_edge(caller_id, target_id, "call")
                    else:
                        # Create a builtin/external node
                        callee_id = OrganismNode.generate_id(
                            callee_name, NodeType.BUILTIN,
                        )
                        if not any(n.id == callee_id for n in nodes):
                            nodes.append(OrganismNode(
                                id=callee_id,
                                name=callee_name,
                                node_type=NodeType.BUILTIN,
                                qualified_name=callee_name,
                            ))
                        _add_edge(caller_id, callee_id, "call")
            for child in ts_node.children:
                _collect_calls(child, caller_id)

        def _resolve_call_target(
            call_node: tree_sitter.Node,
            callee_name: str,
        ) -> Optional[str]:
            """Try to resolve a callee name to a defined node ID.

            Resolution order:
            1. Exact match in defined_names (handles ``foo()`` and
               ``Class.method`` dotted names).
            2. For ``obj.method()`` calls, check if any class in this
               file defines a method with that name.
            3. Return *None* if unresolved (caller creates BUILTIN node).
            """
            # 1. Direct lookup (bare name or dotted "Class.method")
            if callee_name in defined_names:
                return defined_names[callee_name]

            # 2. Member-expression heuristic: if the call is obj.method(),
            #    try matching "method" against any class's method table.
            if call_node.children and call_node.children[0].type in (
                "member_expression", "field_expression",
            ):
                for _cls_name, methods in class_methods.items():
                    if callee_name in methods:
                        return methods[callee_name]

            return None

        def _resolve_callee(call_node: tree_sitter.Node) -> str:
            """Extract the callee name from a call_expression node."""
            if not call_node.children:
                return ""
            first = call_node.children[0]
            if first.type == "identifier":
                return first.text.decode("utf-8", errors="replace")
            if first.type == "member_expression":
                prop = _child_by_type(first, "property_identifier")
                if prop:
                    return prop.text.decode("utf-8", errors="replace")
            if first.type == "field_expression":
                field = _child_by_type(first, "field_identifier")
                if field:
                    return field.text.decode("utf-8", errors="replace")
            return first.text.decode("utf-8", errors="replace")

        def _walk_named_arrow_functions(ts_node: tree_sitter.Node, parent_qname: str, parent_id: str) -> None:
            """Detect named arrow functions: const foo = (...) => { ... }"""
            if lang_key not in ("javascript", "typescript", "tsx"):
                return
            if ts_node.type in ("lexical_declaration", "variable_declaration"):
                for child in ts_node.children:
                    if child.type == "variable_declarator":
                        name_node = _child_by_type(child, "identifier")
                        arrow = _child_by_type(child, "arrow_function")
                        if name_node and arrow:
                            name = name_node.text.decode("utf-8", errors="replace")
                            org_node = _make_node(
                                name, NodeType.FUNCTION, arrow, parent_qname, parent_id,
                            )
                            module_node.children_ids.append(org_node.id)
                            # Collect calls inside the arrow function body
                            _collect_calls(arrow, org_node.id)

        def _walk(ts_node: tree_sitter.Node, parent_qname: str, parent_id: str) -> None:
            """Recursively walk tree-sitter AST and extract structure."""

            node_type_str = ts_node.type

            # ── Functions ────────────────────────────────────────────
            if node_type_str in func_types:
                name = _node_name(ts_node, lang_key)
                if name:
                    org_node = _make_node(
                        name, NodeType.FUNCTION, ts_node, parent_qname, parent_id,
                    )
                    module_node.children_ids.append(org_node.id)
                    # Collect calls inside the function body
                    body = _child_by_type(
                        ts_node, "statement_block", "block", "compound_statement",
                    )
                    if body:
                        _collect_calls(body, org_node.id)
                    return  # Don't recurse into function body again

            # ── Classes / structs / enums ────────────────────────────
            if node_type_str in class_types:
                name = _node_name(ts_node, lang_key)
                if name:
                    org_node = _make_node(
                        name, NodeType.CLASS, ts_node, parent_qname, parent_id,
                    )
                    module_node.children_ids.append(org_node.id)
                    # Recurse into class body for methods
                    for child in ts_node.children:
                        _walk(child, org_node.qualified_name, org_node.id)
                    return

            # ── Go type_declaration (wraps type_spec with struct) ────
            if lang_key == "go" and node_type_str == "type_declaration":
                spec = _child_by_type(ts_node, "type_spec")
                if spec:
                    struct = _child_by_type(spec, "struct_type")
                    if struct:
                        name = _child_text(spec, "type_identifier")
                        if name:
                            org_node = _make_node(
                                name, NodeType.CLASS, ts_node, parent_qname, parent_id,
                            )
                            module_node.children_ids.append(org_node.id)
                            return

            # ── Rust impl blocks ─────────────────────────────────────
            if lang_key == "rust" and node_type_str == "impl_item":
                name = _child_text(ts_node, "type_identifier")
                if name:
                    impl_qname = f"{parent_qname}:{name}"
                    impl_id = OrganismNode.generate_id(impl_qname, NodeType.CLASS)
                    # Only create the impl node if we haven't already got a
                    # struct/enum with this name -- otherwise reuse it.
                    existing = None
                    for n in nodes:
                        if n.name == name and n.node_type == NodeType.CLASS:
                            existing = n
                            break
                    target_id = existing.id if existing else impl_id
                    target_qname = existing.qualified_name if existing else impl_qname
                    if not existing:
                        org_node = _make_node(
                            name, NodeType.CLASS, ts_node, parent_qname, parent_id,
                        )
                        module_node.children_ids.append(org_node.id)
                        target_id = org_node.id
                        target_qname = org_node.qualified_name

                    # Walk children for function_items (methods)
                    decl_list = _child_by_type(ts_node, "declaration_list")
                    if decl_list:
                        for child in decl_list.children:
                            if child.type == "function_item":
                                fname = _child_text(child, "identifier")
                                if fname:
                                    method_node = _make_node(
                                        fname, NodeType.METHOD, child,
                                        target_qname, target_id,
                                    )
                                    # Add as child of the struct/impl node
                                    parent_org = next(
                                        (n for n in nodes if n.id == target_id), None,
                                    )
                                    if parent_org:
                                        parent_org.children_ids.append(method_node.id)
                                    # Collect calls
                                    body = _child_by_type(child, "block")
                                    if body:
                                        _collect_calls(body, method_node.id)
                    return

            # ── Methods ──────────────────────────────────────────────
            if node_type_str in method_types:
                name = _node_name(ts_node, lang_key)
                if not name:
                    # Go method_declaration: name is a field_identifier
                    name = _child_text(ts_node, "field_identifier")
                if name:
                    org_node = _make_node(
                        name, NodeType.METHOD, ts_node, parent_qname, parent_id,
                    )
                    parent_org = next(
                        (n for n in nodes if n.id == parent_id), None,
                    )
                    if parent_org:
                        parent_org.children_ids.append(org_node.id)
                    # Collect calls inside the method body
                    body = _child_by_type(
                        ts_node, "statement_block", "block", "constructor_body",
                    )
                    if body:
                        _collect_calls(body, org_node.id)
                    return

            # ── Imports ──────────────────────────────────────────────
            if node_type_str in import_types:
                import_name = _extract_import_name(ts_node)
                if import_name:
                    ext_id = OrganismNode.generate_id(
                        import_name, NodeType.EXTERNAL_MODULE,
                    )
                    if not any(n.id == ext_id for n in nodes):
                        nodes.append(OrganismNode(
                            id=ext_id,
                            name=import_name,
                            node_type=NodeType.EXTERNAL_MODULE,
                            qualified_name=import_name,
                            position=Position(
                                file=filename,
                                line=ts_node.start_point[0] + 1,
                                column=ts_node.start_point[1],
                            ),
                        ))
                    _add_edge(module_node.id, ext_id, "import")
                return  # No need to recurse into import statements

            # ── Named arrow functions (JS/TS) ────────────────────────
            _walk_named_arrow_functions(ts_node, parent_qname, parent_id)

            # ── Recurse ─────────────────────────────────────────────
            for child in ts_node.children:
                _walk(child, parent_qname, parent_id)

        # Kick off the walk
        _walk(root, module_qname, module_node.id)

        return nodes, edges


# ── Module-level convenience ─────────────────────────────────────────

_default_parser: Optional[TreeSitterParser] = None


def get_parser() -> TreeSitterParser:
    """Return the module-level shared parser instance (lazy singleton)."""
    global _default_parser
    if _default_parser is None:
        _default_parser = TreeSitterParser()
    return _default_parser


def parse_file(filepath: str) -> tuple[list[OrganismNode], list[Edge]]:
    """Parse a non-Python file using tree-sitter."""
    return get_parser().parse_file(filepath)
