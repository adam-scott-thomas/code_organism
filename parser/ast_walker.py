"""
CODE ORGANISM: AST WALKER

Walks Python AST to extract the anatomical structure of code.
This is the dissection phase - we're mapping the nervous system,
the organs, the blood vessels of the code.
"""

from __future__ import annotations
import ast
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field

from ..model.nodes import (
    OrganismNode,
    Edge,
    NodeType,
    Position,
    Metrics,
)


@dataclass
class WalkContext:
    """Context maintained while walking the AST."""
    filename: str
    module_name: str
    current_class: Optional[str] = None
    current_function: Optional[str] = None
    parent_id: Optional[str] = None
    depth: int = 0
    scope_stack: list[str] = field(default_factory=list)

    def qualified_name(self, name: str) -> str:
        """Get fully qualified name for a symbol."""
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

    def pop_scope(self) -> Optional[str]:
        self.depth -= 1
        return self.scope_stack.pop() if self.scope_stack else None


class CodeAnatomist(ast.NodeVisitor):
    """
    Dissects Python code to extract its anatomical structure.

    Like an anatomist studying a body, we identify:
    - Organs (classes, modules)
    - Tissues (functions, methods)
    - Cells (variables)
    - Blood vessels (data flow)
    - Nerves (function calls)
    """

    def __init__(self, context: WalkContext):
        self.context = context
        self.nodes: list[OrganismNode] = []
        self.edges: list[Edge] = []

        # Track what we've seen for edge creation
        self._defined_names: dict[str, str] = {}  # name -> node_id
        self._imports: dict[str, str] = {}  # alias -> full_name
        self._current_node_id: Optional[str] = None

    def analyze(self, tree: ast.AST) -> tuple[list[OrganismNode], list[Edge]]:
        """Analyze an AST and return nodes and edges."""
        self.visit(tree)
        return self.nodes, self.edges

    # =========================================================================
    # MODULE LEVEL
    # =========================================================================

    def visit_Module(self, node: ast.Module) -> None:
        """Visit a module - the entire file."""
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
        self.nodes.append(module_node)
        self._current_node_id = module_node.id
        self.context.parent_id = module_node.id

        # Visit all children
        self.generic_visit(node)

    # =========================================================================
    # IMPORTS (Ligaments - structural connections)
    # =========================================================================

    def visit_Import(self, node: ast.Import) -> None:
        """Visit an import statement."""
        for alias in node.names:
            name = alias.asname or alias.name
            self._imports[name] = alias.name

            # Create external module node if not already defined
            ext_id = OrganismNode.generate_id(alias.name, NodeType.EXTERNAL_MODULE)
            if ext_id not in [n.id for n in self.nodes]:
                ext_node = OrganismNode(
                    id=ext_id,
                    name=alias.name,
                    node_type=NodeType.EXTERNAL_MODULE,
                    qualified_name=alias.name,
                    position=Position(
                        file=self.context.filename,
                        line=node.lineno,
                        column=node.col_offset,
                    ),
                )
                self.nodes.append(ext_node)

            # Create edge from module to imported module
            edge = Edge(
                id=Edge.generate_id(self.context.parent_id, ext_id, "import"),
                source_id=self.context.parent_id,
                target_id=ext_id,
                edge_type="import",
            )
            self.edges.append(edge)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Visit a from...import statement."""
        module_name = node.module or ""

        for alias in node.names:
            name = alias.asname or alias.name
            full_name = f"{module_name}.{alias.name}" if module_name else alias.name
            self._imports[name] = full_name

            # Create external module node
            ext_id = OrganismNode.generate_id(full_name, NodeType.EXTERNAL_MODULE)
            if ext_id not in [n.id for n in self.nodes]:
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
                self.nodes.append(ext_node)

            # Create edge
            edge = Edge(
                id=Edge.generate_id(self.context.parent_id, ext_id, "import"),
                source_id=self.context.parent_id,
                target_id=ext_id,
                edge_type="import",
            )
            self.edges.append(edge)

    # =========================================================================
    # CLASSES (Organs)
    # =========================================================================

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Visit a class definition."""
        qualified_name = self.context.qualified_name(node.name)

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

        # Add decorators to signature
        decorators = [self._get_decorator_name(d) for d in node.decorator_list]
        if decorators:
            class_node.signature = f"@{', @'.join(decorators)}"

        # Base classes
        bases = [self._get_name(b) for b in node.bases]
        if bases:
            class_node.type_annotation = f"({', '.join(bases)})"

        self.nodes.append(class_node)
        self._defined_names[node.name] = class_node.id

        # Add as child of parent
        parent = self._find_node(self.context.parent_id)
        if parent:
            parent.children_ids.append(class_node.id)

        # Create inheritance edges
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

        # Visit children with updated context
        old_class = self.context.current_class
        old_parent = self.context.parent_id
        self.context.current_class = node.name
        self.context.parent_id = class_node.id
        self.context.push_scope(node.name)

        self.generic_visit(node)

        self.context.pop_scope()
        self.context.current_class = old_class
        self.context.parent_id = old_parent

    # =========================================================================
    # FUNCTIONS (Tissues)
    # =========================================================================

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit a function definition."""
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit an async function definition."""
        self._visit_function(node, is_async=True)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef, is_async: bool = False) -> None:
        """Common logic for function/method visitation."""
        qualified_name = self.context.qualified_name(node.name)
        node_type = NodeType.METHOD if self.context.current_class else NodeType.FUNCTION

        # Build signature
        args = []
        for arg in node.args.args:
            arg_str = arg.arg
            if arg.annotation:
                arg_str += f": {self._get_name(arg.annotation)}"
            args.append(arg_str)

        # Handle *args and **kwargs
        if node.args.vararg:
            args.append(f"*{node.args.vararg.arg}")
        if node.args.kwarg:
            args.append(f"**{node.args.kwarg.arg}")

        signature = f"{'async ' if is_async else ''}def {node.name}({', '.join(args)})"

        # Return type
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

        # Add decorators
        decorators = [self._get_decorator_name(d) for d in node.decorator_list]
        if decorators:
            func_node.signature = f"@{', @'.join(decorators)}\n{func_node.signature}"

        self.nodes.append(func_node)
        self._defined_names[node.name] = func_node.id

        # Add as child of parent
        parent = self._find_node(self.context.parent_id)
        if parent:
            parent.children_ids.append(func_node.id)

        # Add parameters as nodes
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
            self.nodes.append(param_node)
            func_node.children_ids.append(param_node.id)

        # Visit children with updated context
        old_function = self.context.current_function
        old_parent = self.context.parent_id
        self.context.current_function = node.name
        self.context.parent_id = func_node.id
        self._current_node_id = func_node.id
        self.context.push_scope(node.name)

        # Visit body to find calls
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                self._record_call(func_node.id, child)

        self.generic_visit(node)

        self.context.pop_scope()
        self.context.current_function = old_function
        self.context.parent_id = old_parent
        self._current_node_id = old_parent

    # =========================================================================
    # CALLS (Nerve signals)
    # =========================================================================

    def _record_call(self, caller_id: str, call_node: ast.Call) -> None:
        """Record a function call as an edge."""
        callee_name = self._get_name(call_node.func)
        if not callee_name:
            return

        # Check if we know what this resolves to
        if callee_name in self._defined_names:
            callee_id = self._defined_names[callee_name]
        elif callee_name in self._imports:
            # It's an imported function
            full_name = self._imports[callee_name]
            callee_id = OrganismNode.generate_id(full_name, NodeType.EXTERNAL_MODULE)
        else:
            # Unknown - might be a builtin or undefined
            callee_id = OrganismNode.generate_id(callee_name, NodeType.BUILTIN)

            # Create builtin node if not exists
            if callee_id not in [n.id for n in self.nodes]:
                builtin_node = OrganismNode(
                    id=callee_id,
                    name=callee_name,
                    node_type=NodeType.BUILTIN,
                    qualified_name=callee_name,
                )
                self.nodes.append(builtin_node)

        # Create call edge
        edge_id = Edge.generate_id(caller_id, callee_id, "call")
        # Avoid duplicates
        if not any(e.id == edge_id for e in self.edges):
            edge = Edge(
                id=edge_id,
                source_id=caller_id,
                target_id=callee_id,
                edge_type="call",
            )
            self.edges.append(edge)

    # =========================================================================
    # VARIABLES (Cells)
    # =========================================================================

    def visit_Assign(self, node: ast.Assign) -> None:
        """Visit an assignment statement."""
        for target in node.targets:
            if isinstance(target, ast.Name):
                self._record_variable(target.id, node)
        self.generic_visit(node)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        """Visit an annotated assignment."""
        if isinstance(node.target, ast.Name):
            type_ann = self._get_name(node.annotation)
            self._record_variable(node.target.id, node, type_ann)
        self.generic_visit(node)

    def _record_variable(self, name: str, node: ast.AST, type_ann: Optional[str] = None) -> None:
        """Record a variable assignment."""
        # Only record class attributes, not local variables (too noisy)
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
            self.nodes.append(var_node)
            self._defined_names[name] = var_node.id

            # Add as child of parent
            parent = self._find_node(self.context.parent_id)
            if parent:
                parent.children_ids.append(var_node.id)

    # =========================================================================
    # HELPERS
    # =========================================================================

    def _find_node(self, node_id: Optional[str]) -> Optional[OrganismNode]:
        """Find a node by ID."""
        if node_id is None:
            return None
        for node in self.nodes:
            if node.id == node_id:
                return node
        return None

    def _get_name(self, node: Optional[ast.AST]) -> str:
        """Extract a name from various AST node types."""
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
            return self._get_name(node.func)
        if isinstance(node, ast.BinOp):
            left = self._get_name(node.left)
            right = self._get_name(node.right)
            return f"{left} | {right}"
        if isinstance(node, ast.Starred):
            return f"*{self._get_name(node.value)}"
        # Python <3.9 compatibility for Index nodes
        if hasattr(ast, 'Index') and isinstance(node, ast.Index):
            return self._get_name(node.value)
        return ""

    def _get_decorator_name(self, node: ast.AST) -> str:
        """Get the name of a decorator."""
        if isinstance(node, ast.Call):
            return self._get_name(node.func)
        return self._get_name(node)

    def _count_lines(self, node: ast.AST) -> int:
        """Count lines of code in an AST node."""
        if hasattr(node, 'end_lineno') and hasattr(node, 'lineno'):
            return (node.end_lineno or node.lineno) - node.lineno + 1
        return 1

    def _compute_complexity(self, node: ast.AST) -> int:
        """
        Compute cyclomatic complexity of a function.

        Complexity = 1 + number of decision points
        Decision points: if, elif, for, while, except, and, or, ternary
        """
        complexity = 1

        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                complexity += 1
            elif isinstance(child, ast.ExceptHandler):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                # Each 'and'/'or' adds branches
                complexity += len(child.values) - 1
            elif isinstance(child, ast.IfExp):  # Ternary
                complexity += 1
            elif isinstance(child, ast.comprehension):
                complexity += 1
                if child.ifs:
                    complexity += len(child.ifs)

        return complexity


# =============================================================================
# PUBLIC API
# =============================================================================

def parse_file(filepath: Path) -> tuple[list[OrganismNode], list[Edge]]:
    """
    Parse a Python file and extract its anatomical structure.

    Args:
        filepath: Path to the Python file

    Returns:
        Tuple of (nodes, edges)
    """
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()

    return parse_source(source, str(filepath))


def parse_source(source: str, filename: str = "<string>") -> tuple[list[OrganismNode], list[Edge]]:
    """
    Parse Python source code and extract its anatomical structure.

    Args:
        source: Python source code
        filename: Filename for error messages

    Returns:
        Tuple of (nodes, edges)
    """
    # Determine module name from filename
    path = Path(filename)
    module_name = path.stem if path.suffix == ".py" else path.name

    # Parse to AST
    tree = ast.parse(source, filename=filename)

    # Walk the tree
    context = WalkContext(
        filename=filename,
        module_name=module_name,
    )
    anatomist = CodeAnatomist(context)

    return anatomist.analyze(tree)
