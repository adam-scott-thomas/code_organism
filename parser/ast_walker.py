# SPDX-License-Identifier: Apache-2.0
"""
CODE ORGANISM: AST WALKER (v2)

Walks Python AST to extract the anatomical structure of code.
This is the dissection phase — mapping the nervous system,
the organs, the blood vessels of the code.

v2: Handles frozen dataclasses, enums, @property, module-level
constants, __post_init__, TYPE_CHECKING blocks, decorator arguments,
Generic/TypeVar, protocol/ABC detection, and rich type annotations.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path

from ..model.nodes import (
    Edge,
    Metrics,
    NodeType,
    OrganismNode,
    Position,
)

# ---------------------------------------------------------------------------
# Walk context
# ---------------------------------------------------------------------------

@dataclass
class WalkContext:
    """Context maintained while walking the AST."""
    filename: str
    module_name: str
    current_class: str | None = None
    current_function: str | None = None
    parent_id: str | None = None
    depth: int = 0
    scope_stack: list[str] = field(default_factory=list)

    # v2: class metadata collected during visit
    class_decorators: dict[str, list[str]] = field(default_factory=dict)
    class_bases: dict[str, list[str]] = field(default_factory=dict)

    def qualified_name(self, name: str) -> str:
        parts = [self.module_name]
        if self.current_class:
            parts.append(self.current_class)
        if self.current_function:
            parts.append(self.current_function)
        parts.append(name)
        return ".".join(parts)

    def push_scope(self, name: str) -> None:
        self.scope_stack.append(name)
        self.depth += 1

    def pop_scope(self) -> str | None:
        self.depth -= 1
        return self.scope_stack.pop() if self.scope_stack else None


# ---------------------------------------------------------------------------
# Anatomist
# ---------------------------------------------------------------------------

class CodeAnatomist(ast.NodeVisitor):
    """
    Dissects Python code to extract its anatomical structure.

    Like an anatomist studying a body, we identify:
    - Organs (classes, modules)
    - Tissues (functions, methods)
    - Cells (variables)
    - Blood vessels (data flow)
    - Nerves (function calls)

    v2 additions:
    - Frozen dataclasses recognized as "armored organs"
    - Enums recognized with member extraction
    - @property methods tagged
    - Module-level constants extracted
    - __post_init__ as initialization logic
    - TYPE_CHECKING blocks isolated
    - Decorator arguments captured
    - Protocols / ABCs detected
    """

    def __init__(self, context: WalkContext):
        self.context = context
        self.nodes: list[OrganismNode] = []
        self.edges: list[Edge] = []

        self._defined_names: dict[str, str] = {}   # name -> node_id
        self._imports: dict[str, str] = {}          # alias -> full_name
        self._current_node_id: str | None = None

        # v2: track type-checking-only imports
        self._in_type_checking: bool = False
        # v2: node-id lookup cache (avoid O(n) scans)
        self._id_to_node: dict[str, OrganismNode] = {}

    def analyze(self, tree: ast.AST) -> tuple[list[OrganismNode], list[Edge]]:
        self.visit(tree)
        return self.nodes, self.edges

    def _add_node(self, node: OrganismNode) -> None:
        """Register a node (with cache)."""
        self.nodes.append(node)
        self._id_to_node[node.id] = node

    def _find_node(self, node_id: str | None) -> OrganismNode | None:
        if node_id is None:
            return None
        return self._id_to_node.get(node_id)

    # =================================================================
    # MODULE
    # =================================================================

    def visit_Module(self, node: ast.Module) -> None:
        module_node = OrganismNode(
            id=OrganismNode.generate_id(self.context.module_name, NodeType.MODULE),
            name=self.context.module_name,
            node_type=NodeType.MODULE,
            qualified_name=self.context.module_name,
            position=Position(
                file=self.context.filename,
                line=1,
                column=0,
            ),
            docstring=ast.get_docstring(node),
            metrics=Metrics(
                lines_of_code=self._count_lines(node),
                depth=0,
            ),
        )
        self._add_node(module_node)
        self._current_node_id = module_node.id
        self.context.parent_id = module_node.id

        # v2: first pass — extract module-level constants
        self._extract_module_constants(node)

        self.generic_visit(node)

    def _extract_module_constants(self, module: ast.Module) -> None:
        """v2: Extract module-level constants (UPPER_CASE assignments)."""
        for stmt in module.body:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name) and target.id.isupper():
                        self._record_module_constant(target.id, stmt)
            elif isinstance(stmt, ast.AnnAssign):
                if (isinstance(stmt.target, ast.Name)
                        and stmt.target.id.isupper()):
                    type_ann = self._get_name(stmt.annotation)
                    self._record_module_constant(stmt.target.id, stmt, type_ann)

    def _record_module_constant(
        self, name: str, node: ast.AST, type_ann: str | None = None,
    ) -> None:
        qualified_name = f"{self.context.module_name}.{name}"
        const_node = OrganismNode(
            id=OrganismNode.generate_id(qualified_name, NodeType.VARIABLE),
            name=name,
            node_type=NodeType.VARIABLE,
            qualified_name=qualified_name,
            parent_id=self.context.parent_id,
            position=Position(
                file=self.context.filename,
                line=node.lineno,
                column=node.col_offset,
            ),
            type_annotation=type_ann,
        )
        # Tag as constant for visualization
        const_node.health_notes.append("module-constant")
        self._add_node(const_node)
        self._defined_names[name] = const_node.id

        parent = self._find_node(self.context.parent_id)
        if parent:
            parent.children_ids.append(const_node.id)

    # =================================================================
    # IMPORTS (Ligaments)
    # =================================================================

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = alias.asname or alias.name
            self._imports[name] = alias.name
            self._create_import_node_and_edge(alias.name, node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module_name = node.module or ""
        for alias in node.names:
            name = alias.asname or alias.name
            full_name = f"{module_name}.{alias.name}" if module_name else alias.name
            self._imports[name] = full_name
            self._create_import_node_and_edge(
                full_name, node,
                type_checking_only=self._in_type_checking,
            )

    def _create_import_node_and_edge(
        self, full_name: str, node: ast.AST, *,
        type_checking_only: bool = False,
    ) -> None:
        ext_id = OrganismNode.generate_id(full_name, NodeType.EXTERNAL_MODULE)
        if ext_id not in self._id_to_node:
            ext_node = OrganismNode(
                id=ext_id,
                name=full_name,
                node_type=NodeType.EXTERNAL_MODULE,
                qualified_name=full_name,
                position=Position(
                    file=self.context.filename,
                    line=node.lineno,
                    column=node.col_offset,
                ),
            )
            if type_checking_only:
                ext_node.health_notes.append("type-checking-only")
            self._add_node(ext_node)

        edge_type = "import_type_only" if type_checking_only else "import"
        edge = Edge(
            id=Edge.generate_id(self.context.parent_id, ext_id, edge_type),
            source_id=self.context.parent_id,
            target_id=ext_id,
            edge_type=edge_type,
        )
        if type_checking_only:
            edge.weight = 0.3  # weaker link — only for type hints
        self.edges.append(edge)

    # =================================================================
    # TYPE_CHECKING blocks (v2)
    # =================================================================

    def visit_If(self, node: ast.If) -> None:
        """Detect TYPE_CHECKING guard blocks."""
        if self._is_type_checking_guard(node.test):
            old = self._in_type_checking
            self._in_type_checking = True
            for stmt in node.body:
                self.visit(stmt)
            self._in_type_checking = old
            for stmt in node.orelse:
                self.visit(stmt)
        else:
            self.generic_visit(node)

    @staticmethod
    def _is_type_checking_guard(test: ast.AST) -> bool:
        if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
            return True
        if isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING":
            return True
        return False

    # =================================================================
    # CLASSES (Organs) — v2: dataclass + enum detection
    # =================================================================

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualified_name = self.context.qualified_name(node.name)

        # v2: classify class kind
        decorators = [self._get_decorator_name(d) for d in node.decorator_list]
        decorator_details = [self._get_decorator_full(d) for d in node.decorator_list]
        bases = [self._get_name(b) for b in node.bases]

        is_dataclass = any("dataclass" in d for d in decorators)
        is_frozen = any("frozen=True" in d for d in decorator_details)
        has_slots = any("slots=True" in d for d in decorator_details)
        is_enum = any(b in ("Enum", "enum.Enum") for b in bases)
        is_protocol = any(b in ("Protocol", "ABC", "abc.ABC") for b in bases)

        class_node = OrganismNode(
            id=OrganismNode.generate_id(qualified_name, NodeType.CLASS),
            name=node.name,
            node_type=NodeType.CLASS,
            qualified_name=qualified_name,
            parent_id=self.context.parent_id,
            position=Position(
                file=self.context.filename,
                line=node.lineno,
                column=node.col_offset,
                end_line=node.end_lineno,
                end_column=node.end_col_offset,
            ),
            docstring=ast.get_docstring(node),
            metrics=Metrics(
                lines_of_code=self._count_lines(node),
                depth=self.context.depth,
            ),
        )

        # v2: tag class kind in health notes for visualization
        if is_dataclass:
            class_node.health_notes.append("dataclass")
        if is_frozen:
            class_node.health_notes.append("frozen")
        if has_slots:
            class_node.health_notes.append("slots")
        if is_enum:
            class_node.health_notes.append("enum")
        if is_protocol:
            class_node.health_notes.append("protocol")

        if decorator_details:
            class_node.signature = " | ".join(decorator_details)
        if bases:
            class_node.type_annotation = f"({', '.join(bases)})"

        self._add_node(class_node)
        self._defined_names[node.name] = class_node.id

        # Store for later reference
        self.context.class_decorators[node.name] = decorators
        self.context.class_bases[node.name] = bases

        parent = self._find_node(self.context.parent_id)
        if parent:
            parent.children_ids.append(class_node.id)

        # Inheritance edges
        for base in node.bases:
            base_name = self._get_name(base)
            if base_name in self._defined_names:
                edge = Edge(
                    id=Edge.generate_id(class_node.id, self._defined_names[base_name], "inheritance"),
                    source_id=class_node.id,
                    target_id=self._defined_names[base_name],
                    edge_type="inheritance",
                )
                self.edges.append(edge)

        # v2: extract enum members
        if is_enum:
            self._extract_enum_members(node, class_node.id, qualified_name)

        # v2: extract dataclass fields
        if is_dataclass:
            self._extract_dataclass_fields(node, class_node.id, qualified_name)

        # Visit children
        old_class = self.context.current_class
        old_parent = self.context.parent_id
        self.context.current_class = node.name
        self.context.parent_id = class_node.id
        self.context.push_scope(node.name)

        self.generic_visit(node)

        self.context.pop_scope()
        self.context.current_class = old_class
        self.context.parent_id = old_parent

    def _extract_enum_members(
        self, class_node: ast.ClassDef, parent_id: str, class_qname: str,
    ) -> None:
        """v2: Extract enum member assignments."""
        for stmt in class_node.body:
            if isinstance(stmt, ast.Assign):
                for target in stmt.targets:
                    if isinstance(target, ast.Name):
                        member_qname = f"{class_qname}.{target.id}"
                        value_str = self._get_name(stmt.value) if stmt.value else ""
                        member_node = OrganismNode(
                            id=OrganismNode.generate_id(member_qname, NodeType.ATTRIBUTE),
                            name=target.id,
                            node_type=NodeType.ATTRIBUTE,
                            qualified_name=member_qname,
                            parent_id=parent_id,
                            position=Position(
                                file=self.context.filename,
                                line=stmt.lineno,
                                column=stmt.col_offset,
                            ),
                            type_annotation=value_str,
                        )
                        member_node.health_notes.append("enum-member")
                        self._add_node(member_node)
                        parent = self._find_node(parent_id)
                        if parent:
                            parent.children_ids.append(member_node.id)

    def _extract_dataclass_fields(
        self, class_node: ast.ClassDef, parent_id: str, class_qname: str,
    ) -> None:
        """v2: Extract typed fields from a dataclass body."""
        for stmt in class_node.body:
            if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                field_name = stmt.target.id
                field_qname = f"{class_qname}.{field_name}"
                type_ann = self._get_name(stmt.annotation)

                # Detect field(default_factory=...) or literal defaults
                default_info = None
                if stmt.value is not None:
                    default_info = self._get_name(stmt.value)

                field_node = OrganismNode(
                    id=OrganismNode.generate_id(field_qname, NodeType.ATTRIBUTE),
                    name=field_name,
                    node_type=NodeType.ATTRIBUTE,
                    qualified_name=field_qname,
                    parent_id=parent_id,
                    position=Position(
                        file=self.context.filename,
                        line=stmt.lineno,
                        column=stmt.col_offset,
                    ),
                    type_annotation=type_ann,
                )
                field_node.health_notes.append("dataclass-field")
                if default_info:
                    field_node.health_notes.append(f"default={default_info}")

                self._add_node(field_node)
                self._defined_names[field_name] = field_node.id
                parent = self._find_node(parent_id)
                if parent:
                    parent.children_ids.append(field_node.id)

    # =================================================================
    # FUNCTIONS (Tissues) — v2: @property, __post_init__, async
    # =================================================================

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node, is_async=True)

    def _visit_function(
        self, node: ast.FunctionDef | ast.AsyncFunctionDef,
        is_async: bool = False,
    ) -> None:
        qualified_name = self.context.qualified_name(node.name)
        node_type = NodeType.METHOD if self.context.current_class else NodeType.FUNCTION

        # v2: detect special method kinds
        decorators = [self._get_decorator_name(d) for d in node.decorator_list]
        decorator_details = [self._get_decorator_full(d) for d in node.decorator_list]
        is_property = "property" in decorators
        is_staticmethod = "staticmethod" in decorators
        is_classmethod = "classmethod" in decorators
        is_post_init = node.name == "__post_init__"

        # Build signature
        args = []
        for arg in node.args.args:
            arg_str = arg.arg
            if arg.annotation:
                arg_str += f": {self._get_name(arg.annotation)}"
            args.append(arg_str)
        if node.args.vararg:
            v = node.args.vararg
            arg_str = f"*{v.arg}"
            if v.annotation:
                arg_str += f": {self._get_name(v.annotation)}"
            args.append(arg_str)
        if node.args.kwarg:
            k = node.args.kwarg
            arg_str = f"**{k.arg}"
            if k.annotation:
                arg_str += f": {self._get_name(k.annotation)}"
            args.append(arg_str)

        signature = f"{'async ' if is_async else ''}def {node.name}({', '.join(args)})"

        return_type = None
        if node.returns:
            return_type = self._get_name(node.returns)
            signature += f" -> {return_type}"

        func_node = OrganismNode(
            id=OrganismNode.generate_id(qualified_name, node_type),
            name=node.name,
            node_type=node_type,
            qualified_name=qualified_name,
            parent_id=self.context.parent_id,
            position=Position(
                file=self.context.filename,
                line=node.lineno,
                column=node.col_offset,
                end_line=node.end_lineno,
                end_column=node.end_col_offset,
            ),
            docstring=ast.get_docstring(node),
            signature=signature,
            return_type=return_type,
            metrics=Metrics(
                lines_of_code=self._count_lines(node),
                depth=self.context.depth,
                cyclomatic_complexity=self._compute_complexity(node),
            ),
        )

        # v2: tag special kinds
        if is_property:
            func_node.health_notes.append("property")
        if is_staticmethod:
            func_node.health_notes.append("staticmethod")
        if is_classmethod:
            func_node.health_notes.append("classmethod")
        if is_post_init:
            func_node.health_notes.append("post-init")
        if is_async:
            func_node.health_notes.append("async")
        if node.name.startswith("__") and node.name.endswith("__"):
            func_node.health_notes.append("dunder")

        if decorator_details:
            func_node.signature = " | ".join(decorator_details) + "\n" + func_node.signature

        self._add_node(func_node)
        self._defined_names[node.name] = func_node.id

        parent = self._find_node(self.context.parent_id)
        if parent:
            parent.children_ids.append(func_node.id)

        # Parameters as nodes
        for arg in node.args.args:
            param_qualified = f"{qualified_name}.{arg.arg}"
            param_node = OrganismNode(
                id=OrganismNode.generate_id(param_qualified, NodeType.PARAMETER),
                name=arg.arg,
                node_type=NodeType.PARAMETER,
                qualified_name=param_qualified,
                parent_id=func_node.id,
                position=Position(
                    file=self.context.filename,
                    line=node.lineno,
                    column=node.col_offset,
                ),
                type_annotation=self._get_name(arg.annotation) if arg.annotation else None,
            )
            self._add_node(param_node)
            func_node.children_ids.append(param_node.id)

        # Visit children
        old_function = self.context.current_function
        old_parent = self.context.parent_id
        self.context.current_function = node.name
        self.context.parent_id = func_node.id
        self._current_node_id = func_node.id
        self.context.push_scope(node.name)

        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                self._record_call(func_node.id, child)

        self.generic_visit(node)

        self.context.pop_scope()
        self.context.current_function = old_function
        self.context.parent_id = old_parent
        self._current_node_id = old_parent

    # =================================================================
    # CALLS (Nerve signals)
    # =================================================================

    def _record_call(self, caller_id: str, call_node: ast.Call) -> None:
        callee_name = self._get_name(call_node.func)
        if not callee_name:
            return

        if callee_name in self._defined_names:
            callee_id = self._defined_names[callee_name]
        elif callee_name in self._imports:
            full_name = self._imports[callee_name]
            callee_id = OrganismNode.generate_id(full_name, NodeType.EXTERNAL_MODULE)
        else:
            callee_id = OrganismNode.generate_id(callee_name, NodeType.BUILTIN)
            if callee_id not in self._id_to_node:
                builtin_node = OrganismNode(
                    id=callee_id,
                    name=callee_name,
                    node_type=NodeType.BUILTIN,
                    qualified_name=callee_name,
                )
                self._add_node(builtin_node)

        edge_id = Edge.generate_id(caller_id, callee_id, "call")
        if not any(e.id == edge_id for e in self.edges):
            edge = Edge(
                id=edge_id,
                source_id=caller_id,
                target_id=callee_id,
                edge_type="call",
            )
            self.edges.append(edge)

    # =================================================================
    # VARIABLES (Cells)
    # =================================================================

    def visit_Assign(self, node: ast.Assign) -> None:
        for target in node.targets:
            if isinstance(target, ast.Name):
                # Skip module-level constants (already extracted)
                if (not self.context.current_class
                        and not self.context.current_function
                        and target.id.isupper()):
                    continue
                self._record_variable(target.id, node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if isinstance(node.target, ast.Name):
            # Skip dataclass fields (already extracted) and module constants
            if self.context.current_class:
                class_name = self.context.current_class
                class_decs = self.context.class_decorators.get(class_name, [])
                if any("dataclass" in d for d in class_decs):
                    return  # handled by _extract_dataclass_fields
            if not self.context.current_class and not self.context.current_function:
                if node.target.id.isupper():
                    return  # handled by _extract_module_constants
            type_ann = self._get_name(node.annotation)
            self._record_variable(node.target.id, node, type_ann)
        self.generic_visit(node)

    def _record_variable(
        self, name: str, node: ast.AST, type_ann: str | None = None,
    ) -> None:
        # Only class attributes (not local vars — too noisy)
        if self.context.current_class and not self.context.current_function:
            qualified_name = self.context.qualified_name(name)
            var_node = OrganismNode(
                id=OrganismNode.generate_id(qualified_name, NodeType.ATTRIBUTE),
                name=name,
                node_type=NodeType.ATTRIBUTE,
                qualified_name=qualified_name,
                parent_id=self.context.parent_id,
                position=Position(
                    file=self.context.filename,
                    line=node.lineno,
                    column=node.col_offset,
                ),
                type_annotation=type_ann,
            )
            self._add_node(var_node)
            self._defined_names[name] = var_node.id

            parent = self._find_node(self.context.parent_id)
            if parent:
                parent.children_ids.append(var_node.id)

    # =================================================================
    # HELPERS
    # =================================================================

    def _get_name(self, node: ast.AST | None) -> str:
        """Extract a name from various AST node types.

        v2: handles more node kinds for richer type annotations.
        """
        if node is None:
            return ""
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            value = self._get_name(node.value)
            return f"{value}.{node.attr}" if value else node.attr
        if isinstance(node, ast.Subscript):
            value = self._get_name(node.value)
            slice_str = self._get_name(node.slice)
            return f"{value}[{slice_str}]"
        if isinstance(node, ast.Constant):
            return repr(node.value)
        if isinstance(node, ast.Tuple):
            return ", ".join(self._get_name(e) for e in node.elts)
        if isinstance(node, ast.List):
            return "[" + ", ".join(self._get_name(e) for e in node.elts) + "]"
        if isinstance(node, ast.Call):
            func = self._get_name(node.func)
            # v2: capture keyword arguments (e.g., field(default_factory=list))
            kw_parts = []
            for kw in node.keywords:
                if kw.arg:
                    kw_parts.append(f"{kw.arg}={self._get_name(kw.value)}")
            args_parts = [self._get_name(a) for a in node.args]
            all_parts = args_parts + kw_parts
            if all_parts:
                return f"{func}({', '.join(all_parts)})"
            return func
        if isinstance(node, ast.BinOp):
            left = self._get_name(node.left)
            right = self._get_name(node.right)
            op = self._binop_symbol(node.op)
            return f"{left} {op} {right}"
        if isinstance(node, ast.Starred):
            return f"*{self._get_name(node.value)}"
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return f"-{self._get_name(node.operand)}"
        # Python <3.9 compat
        if hasattr(ast, "Index") and isinstance(node, ast.Index):
            return self._get_name(node.value)  # type: ignore[attr-defined]
        # v2: keyword (standalone)
        if isinstance(node, ast.keyword):
            if node.arg:
                return f"{node.arg}={self._get_name(node.value)}"
            return f"**{self._get_name(node.value)}"
        return ""

    @staticmethod
    def _binop_symbol(op: ast.AST) -> str:
        symbols = {
            ast.BitOr: "|", ast.BitAnd: "&", ast.BitXor: "^",
            ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/",
            ast.Mod: "%", ast.Pow: "**", ast.FloorDiv: "//",
            ast.LShift: "<<", ast.RShift: ">>",
        }
        return symbols.get(type(op), "|")

    def _get_decorator_name(self, node: ast.AST) -> str:
        if isinstance(node, ast.Call):
            return self._get_name(node.func)
        return self._get_name(node)

    def _get_decorator_full(self, node: ast.AST) -> str:
        """v2: Get full decorator with arguments.

        e.g., @dataclass(frozen=True, slots=True) -> "dataclass(frozen=True, slots=True)"
        """
        if isinstance(node, ast.Call):
            func_name = self._get_name(node.func)
            parts = [self._get_name(a) for a in node.args]
            for kw in node.keywords:
                if kw.arg:
                    parts.append(f"{kw.arg}={self._get_name(kw.value)}")
            if parts:
                return f"{func_name}({', '.join(parts)})"
            return f"{func_name}()"
        return self._get_name(node)

    def _count_lines(self, node: ast.AST) -> int:
        if hasattr(node, "end_lineno") and hasattr(node, "lineno"):
            return (node.end_lineno or node.lineno) - node.lineno + 1
        return 1

    def _compute_complexity(self, node: ast.AST) -> int:
        """Cyclomatic complexity: 1 + decision points."""
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                complexity += 1
            elif isinstance(child, ast.ExceptHandler):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                complexity += len(child.values) - 1
            elif isinstance(child, ast.IfExp):
                complexity += 1
            elif isinstance(child, ast.comprehension):
                complexity += 1
                if child.ifs:
                    complexity += len(child.ifs)
            # v2: match/case (Python 3.10+)
            elif hasattr(ast, "Match") and isinstance(child, ast.Match):
                complexity += len(child.cases) if hasattr(child, "cases") else 1
        return complexity


# =============================================================================
# PUBLIC API
# =============================================================================

def parse_file(filepath: Path) -> tuple[list[OrganismNode], list[Edge]]:
    """Parse a Python file and extract its anatomical structure."""
    with open(filepath, encoding="utf-8") as f:
        source = f.read()
    return parse_source(source, str(filepath))


def parse_source(source: str, filename: str = "<string>") -> tuple[list[OrganismNode], list[Edge]]:
    """Parse Python source code and extract its anatomical structure."""
    path = Path(filename)
    module_name = path.stem if path.suffix == ".py" else path.name

    tree = ast.parse(source, filename=filename)

    context = WalkContext(
        filename=filename,
        module_name=module_name,
    )
    anatomist = CodeAnatomist(context)

    return anatomist.analyze(tree)
