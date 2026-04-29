#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""
EXECUTE-CYCLE EXTRACTOR
=======================

Parses a Python function (default: _execute_cycle) using the ast module
and extracts:

  1. Every function call in source order
  2. Assigned outputs  (lhs = call(...))
  3. Arguments passed   (call(a, b, kw=c))
  4. Conditionals        (if / elif / else branches)
  5. Loops               (for phase in phases: ...)

Emits:
  artifacts/execute_cycle_steps.json   — ordered step list
  artifacts/execute_cycle_deps.json    — dependency graph (adjacency list)
  artifacts/execute_cycle_graph.mmd    — Mermaid flowchart
  artifacts/execute_cycle_graph.dot    — Graphviz digraph

Usage:
  python -m Code_Organism.tools.extract_execute_cycle <file.py> [--function _execute_cycle]
  python tools/extract_execute_cycle.py <file.py>

Can target ANY function in ANY Python file — not just Maelstrom.
"""
from __future__ import annotations

import ast
import json
import sys
import textwrap
from dataclasses import dataclass, field
from pathlib import Path

# ═══════════════════════════════════════════════════════════════════════
# DATA MODEL
# ═══════════════════════════════════════════════════════════════════════

@dataclass
class StepCall:
    """A single function/method call extracted from the AST."""
    order: int                           # Sequential position (1-based)
    line: int                            # Source line number
    callee: str                          # Function/method name
    full_callee: str                     # Full dotted expression (self.x.y())
    outputs: list[str]                   # LHS targets (empty if expression-stmt)
    args: list[str]                      # Positional arg expressions
    kwargs: dict[str, str]               # Keyword arg expressions
    inside_loop: str | None = None    # Loop variable if inside for-loop
    inside_if: str | None = None      # Condition expression if inside if-block
    comment: str | None = None        # Inline comment / docstring hint
    step_label: str | None = None     # e.g. "Step 3" from comments


@dataclass
class Branch:
    """A conditional branch in the function."""
    line: int
    condition: str
    calls: list[StepCall] = field(default_factory=list)


@dataclass
class Loop:
    """A for-loop block in the function."""
    line: int
    target: str          # Loop variable
    iterable: str        # What we iterate over
    calls: list[StepCall] = field(default_factory=list)


@dataclass
class ExtractionResult:
    """Complete extraction output."""
    source_file: str
    function_name: str
    function_line: int
    function_end_line: int
    total_steps: int
    steps: list[StepCall]
    branches: list[Branch] = field(default_factory=list)
    loops: list[Loop] = field(default_factory=list)
    step_labels: list[str] = field(default_factory=list)


# ═══════════════════════════════════════════════════════════════════════
# AST UTILITIES
# ═══════════════════════════════════════════════════════════════════════

def unparse_node(node: ast.AST) -> str:
    """Turn an AST node back into source text."""
    try:
        return ast.unparse(node)
    except Exception:
        return "<complex>"


def extract_callee_name(call_node: ast.Call) -> tuple[str, str]:
    """
    Extract (short_name, full_dotted_name) from a Call node's func.

    e.g. self.doctrine.compute_regret(...)
         -> ("compute_regret", "self.doctrine.compute_regret")
    """
    func = call_node.func
    full = unparse_node(func)

    if isinstance(func, ast.Name):
        return func.id, full
    elif isinstance(func, ast.Attribute):
        return func.attr, full
    else:
        return full, full


def extract_targets(node: ast.AST) -> list[str]:
    """Extract assignment target names from an Assign/AnnAssign."""
    if isinstance(node, ast.Assign):
        targets = []
        for t in node.targets:
            targets.append(unparse_node(t))
        return targets
    elif isinstance(node, ast.AnnAssign):
        return [unparse_node(node.target)]
    return []


def extract_step_label(source_lines: list[str], lineno: int) -> str | None:
    """
    Look for a comment above `lineno` that looks like a step label.
    e.g.  # --- Step 3: Update S(t) ---
          # --- Archive counterfactuals ---
    Searches up to 6 lines above (accounts for intermediate comments,
    blank lines, and simple assignments between label and call).
    """
    for offset in range(1, 7):
        idx = lineno - 1 - offset
        if idx < 0:
            break
        line = source_lines[idx].strip()
        if line.startswith("#") and "---" in line:
            clean = line.lstrip("#").strip().strip("-").strip()
            if clean:
                return clean
    return None


# ═══════════════════════════════════════════════════════════════════════
# CORE EXTRACTOR
# ═══════════════════════════════════════════════════════════════════════

class FunctionExtractor(ast.NodeVisitor):
    """
    Extracts the ordered call sequence from a specific function.

    Walks the function body in source order, recording every call
    expression along with its context (assignment targets, loop,
    conditional branch).
    """

    def __init__(self, source_lines: list[str]):
        self.source_lines = source_lines
        self.steps: list[StepCall] = []
        self.branches: list[Branch] = []
        self.loops: list[Loop] = []
        self.step_labels: list[str] = []
        self._order = 0
        self._loop_stack: list[str] = []       # Full nesting chain
        self._if_stack: list[str] = []          # Full nesting chain
        self._current_branch: Branch | None = None
        self._current_loop: Loop | None = None

    def extract(self, func_node: ast.FunctionDef) -> ExtractionResult:
        """Main entry: walk the function body and return structured result."""
        self._walk_body(func_node.body)

        return ExtractionResult(
            source_file="",  # filled by caller
            function_name=func_node.name,
            function_line=func_node.lineno,
            function_end_line=func_node.end_lineno or func_node.lineno,
            total_steps=len(self.steps),
            steps=self.steps,
            branches=self.branches,
            loops=self.loops,
            step_labels=self.step_labels,
        )

    def _walk_body(self, body: list[ast.stmt]):
        """Walk a sequence of statements in source order."""
        for stmt in body:
            self._visit_stmt(stmt)

    def _visit_stmt(self, stmt: ast.stmt):
        """Dispatch a single statement."""
        if isinstance(stmt, (ast.Assign, ast.AnnAssign)):
            self._visit_assignment(stmt)
        elif isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Call):
            self._visit_bare_call(stmt)
        elif isinstance(stmt, ast.For):
            self._visit_for(stmt)
        elif isinstance(stmt, ast.If):
            self._visit_if(stmt)
        elif isinstance(stmt, ast.Assign):
            # Already handled above but catch augmented assigns
            self._visit_assignment(stmt)
        elif isinstance(stmt, ast.AugAssign):
            # e.g. x += foo()
            if isinstance(stmt.value, ast.Call):
                self._record_call(stmt.value, [unparse_node(stmt.target)], stmt.lineno)
        elif isinstance(stmt, (ast.With, ast.AsyncWith)):
            self._walk_body(stmt.body)
        elif isinstance(stmt, ast.Try):
            self._walk_body(stmt.body)
            for handler in stmt.handlers:
                self._walk_body(handler.body)
            if stmt.finalbody:
                self._walk_body(stmt.finalbody)
            if hasattr(stmt, 'orelse') and stmt.orelse:
                self._walk_body(stmt.orelse)

    def _visit_assignment(self, stmt):
        """Handle x = call(...) or x = expr containing calls."""
        targets = extract_targets(stmt)

        # Get the value side
        value = stmt.value if isinstance(stmt, ast.Assign) else stmt.value
        if value is None:
            return

        if isinstance(value, ast.Call):
            self._record_call(value, targets, stmt.lineno)
        elif isinstance(value, ast.ListComp):
            # [call(x) for x in ...]
            for node in ast.walk(value):
                if isinstance(node, ast.Call):
                    self._record_call(node, targets, stmt.lineno)
        elif isinstance(value, ast.DictComp):
            for node in ast.walk(value):
                if isinstance(node, ast.Call):
                    self._record_call(node, targets, stmt.lineno)
        elif isinstance(value, ast.Dict):
            # Might have calls in values
            for v in value.values:
                if v and isinstance(v, ast.Call):
                    self._record_call(v, targets, stmt.lineno)
        elif isinstance(value, ast.Tuple) or isinstance(value, ast.List):
            for elt in value.elts:
                if isinstance(elt, ast.Call):
                    self._record_call(elt, targets, stmt.lineno)
        else:
            # Walk for any nested calls (e.g. x = not foo())
            for node in ast.walk(value):
                if isinstance(node, ast.Call):
                    self._record_call(node, targets, stmt.lineno)
                    break  # Only record the outermost call

    def _visit_bare_call(self, stmt: ast.Expr):
        """Handle bare call expression (no assignment)."""
        self._record_call(stmt.value, [], stmt.lineno)

    def _visit_for(self, stmt: ast.For):
        """Handle for-loop: record context, then walk body."""
        target = unparse_node(stmt.target)
        iterable = unparse_node(stmt.iter)

        loop = Loop(
            line=stmt.lineno,
            target=target,
            iterable=iterable,
        )
        self.loops.append(loop)

        # Push loop context
        prev_loop_obj = self._current_loop
        self._loop_stack.append(f"for {target} in {iterable}")
        self._current_loop = loop

        self._walk_body(stmt.body)

        self._loop_stack.pop()
        self._current_loop = prev_loop_obj

        # Handle else clause
        if stmt.orelse:
            self._walk_body(stmt.orelse)

    def _visit_if(self, stmt: ast.If):
        """Handle if/elif/else: record branch context."""
        condition = unparse_node(stmt.test)

        branch = Branch(
            line=stmt.lineno,
            condition=condition,
        )
        self.branches.append(branch)

        # Push if context
        prev_branch = self._current_branch
        self._if_stack.append(condition)
        self._current_branch = branch

        self._walk_body(stmt.body)

        self._if_stack.pop()
        self._current_branch = prev_branch

        # Handle elif/else
        if stmt.orelse:
            if len(stmt.orelse) == 1 and isinstance(stmt.orelse[0], ast.If):
                # elif
                self._visit_if(stmt.orelse[0])
            else:
                # else
                else_cond = f"else (not {condition})"
                else_branch = Branch(
                    line=stmt.orelse[0].lineno if stmt.orelse else stmt.lineno,
                    condition=else_cond,
                )
                self.branches.append(else_branch)

                prev_branch2 = self._current_branch
                self._if_stack.append(else_cond)
                self._current_branch = else_branch

                self._walk_body(stmt.orelse)

                self._if_stack.pop()
                self._current_branch = prev_branch2

    def _record_call(self, call_node: ast.Call, targets: list[str], lineno: int):
        """Record a function call as a step.

        Also extracts function calls nested inside keyword arguments.
        e.g. update_state(identity_veto=any_identity_veto(events))
        will record both update_state() and any_identity_veto() as steps.
        """
        # First, extract any calls nested in kwargs (before recording parent)
        for kw in call_node.keywords:
            if kw.value and isinstance(kw.value, ast.Call):
                nested_short, nested_full = extract_callee_name(kw.value)
                if nested_short not in self._SKIP_BUILTINS:
                    self._emit_step(
                        kw.value,
                        targets=[f"({kw.arg})"],
                        lineno=kw.value.lineno if hasattr(kw.value, 'lineno') else lineno,
                    )

        # Also extract calls nested in positional args
        for arg in call_node.args:
            if isinstance(arg, ast.Call):
                nested_short, nested_full = extract_callee_name(arg)
                if nested_short not in self._SKIP_BUILTINS:
                    self._emit_step(arg, targets=[], lineno=arg.lineno if hasattr(arg, 'lineno') else lineno)

        short, full = extract_callee_name(call_node)
        if short in self._SKIP_BUILTINS:
            return

        self._emit_step(call_node, targets, lineno)

    # Trivial builtins to skip
    _SKIP_BUILTINS = frozenset({
        "len", "list", "dict", "set", "tuple", "str", "int", "float",
        "bool", "print", "range", "enumerate", "zip", "sorted", "round",
        "min", "max", "any", "all", "isinstance", "hasattr", "type",
        "repr", "id", "format", "open", "super",
    })

    def _emit_step(self, call_node: ast.Call, targets: list[str], lineno: int):
        """Emit a single StepCall for a function call."""
        short, full = extract_callee_name(call_node)

        args = [unparse_node(a) for a in call_node.args]
        kwargs = {kw.arg: unparse_node(kw.value) for kw in call_node.keywords if kw.arg}

        label = extract_step_label(self.source_lines, lineno)
        if label and label not in self.step_labels:
            self.step_labels.append(label)

        # Use full nesting context (joined with " > " for readability)
        loop_ctx = " > ".join(self._loop_stack) if self._loop_stack else None
        if_ctx = " > ".join(self._if_stack) if self._if_stack else None

        self._order += 1
        step = StepCall(
            order=self._order,
            line=lineno,
            callee=short,
            full_callee=full,
            outputs=targets,
            args=args,
            kwargs=kwargs,
            inside_loop=loop_ctx,
            inside_if=if_ctx,
            step_label=label,
        )
        self.steps.append(step)

        if self._current_branch:
            self._current_branch.calls.append(step)
        if self._current_loop:
            self._current_loop.calls.append(step)


# ═══════════════════════════════════════════════════════════════════════
# FIND THE TARGET FUNCTION
# ═══════════════════════════════════════════════════════════════════════

def find_function(tree: ast.Module, name: str) -> ast.FunctionDef | None:
    """Find a function or method by name in the AST (searches classes too)."""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == name:
                return node
    return None


# ═══════════════════════════════════════════════════════════════════════
# DEPENDENCY GRAPH BUILDER
# ═══════════════════════════════════════════════════════════════════════

def build_dependency_graph(steps: list[StepCall]) -> dict:
    """
    Build an adjacency-list dependency graph.

    A step B depends on step A if any of A's outputs appear in B's args/kwargs.
    Also chains sequential calls where no explicit data dependency exists
    (implicit control-flow ordering).
    """
    # Map output variable -> step that produces it
    producers: dict[str, int] = {}
    for step in steps:
        for out in step.outputs:
            # Handle tuple unpacking: "a, b" -> ["a", "b"]
            for var in out.replace(" ", "").split(","):
                producers[var.strip()] = step.order

    # Build adjacency list
    graph: dict[str, list[str]] = {}
    node_labels: dict[str, str] = {}

    for step in steps:
        node_id = f"s{step.order}"
        label = step.callee
        if step.outputs:
            label = f"{', '.join(step.outputs)} = {label}"
        node_labels[node_id] = label
        graph[node_id] = []

    for step in steps:
        node_id = f"s{step.order}"
        deps_found = set()

        # Check if any arg references an output from a previous step
        all_arg_text = " ".join(step.args) + " " + " ".join(step.kwargs.values())
        for var, producer_order in producers.items():
            if producer_order < step.order and var in all_arg_text:
                deps_found.add(f"s{producer_order}")

        # If no explicit data dep, chain to previous step (control flow)
        if not deps_found and step.order > 1:
            deps_found.add(f"s{step.order - 1}")

        for dep in sorted(deps_found):
            if dep in graph:
                graph[dep].append(node_id)

    return {"nodes": node_labels, "edges": graph}


# ═══════════════════════════════════════════════════════════════════════
# MERMAID GENERATOR
# ═══════════════════════════════════════════════════════════════════════

def generate_mermaid(result: ExtractionResult, dep_graph: dict) -> str:
    """Generate a Mermaid flowchart from the extraction result."""
    lines = [
        "%%{ init: {'theme': 'base', 'themeVariables': {'primaryColor': '#E8F4FD', 'primaryTextColor': '#2D3436', 'primaryBorderColor': '#0984E3', 'lineColor': '#636E72', 'secondaryColor': '#F0FAF0', 'tertiaryColor': '#FFF5F5'}} }%%",
        "flowchart TD",
        f"    %% Auto-generated from {result.function_name}() in {Path(result.source_file).name}",
        f"    %% Lines {result.function_line}-{result.function_end_line} | {result.total_steps} steps",
        "",
    ]

    edges = dep_graph["edges"]

    # Track which steps are inside loops/conditions for subgraphs
    loop_steps: dict[str, list[str]] = {}  # loop_desc -> [node_ids]
    if_steps: dict[str, list[str]] = {}    # condition -> [node_ids]
    standalone: list[str] = []

    for step in result.steps:
        node_id = f"s{step.order}"
        if step.inside_loop:
            loop_steps.setdefault(step.inside_loop, []).append(node_id)
        elif step.inside_if:
            if_steps.setdefault(step.inside_if, []).append(node_id)
        else:
            standalone.append(node_id)

    # Emit standalone nodes with shapes
    for step in result.steps:
        node_id = f"s{step.order}"
        label = _mermaid_label(step)
        # Escape pipes for Mermaid
        label = label.replace("|", "\\|")

        if step.inside_loop or step.inside_if:
            continue  # Will be emitted inside subgraph

        lines.append(f"    {node_id}[{_quote(label)}]")

    # Emit loop subgraphs
    for i, (loop_desc, node_ids) in enumerate(loop_steps.items()):
        short_desc = loop_desc
        if len(short_desc) > 60:
            short_desc = short_desc[:57] + "..."
        lines.append("")
        lines.append(f"    subgraph loop{i}[\"LOOP: {_escape_mermaid(short_desc)}\"]")
        lines.append("        direction TB")
        for step in result.steps:
            nid = f"s{step.order}"
            if nid in node_ids:
                label = _mermaid_label(step)
                label = label.replace("|", "\\|")
                lines.append(f"        {nid}[{_quote(label)}]")
        lines.append("    end")

    # Emit conditional subgraphs
    for i, (cond, node_ids) in enumerate(if_steps.items()):
        short_cond = cond
        if len(short_cond) > 60:
            short_cond = short_cond[:57] + "..."
        lines.append("")
        lines.append(f"    subgraph if{i}[\"IF: {_escape_mermaid(short_cond)}\"]")
        lines.append("        direction TB")
        for step in result.steps:
            nid = f"s{step.order}"
            if nid in node_ids:
                label = _mermaid_label(step)
                label = label.replace("|", "\\|")
                lines.append(f"        {nid}[{_quote(label)}]")
        lines.append("    end")

    # Emit edges
    lines.append("")
    lines.append("    %% Dependencies")
    for source, targets in edges.items():
        for target in targets:
            lines.append(f"    {source} --> {target}")

    # Style
    lines.append("")
    lines.append("    %% Styles")
    for step in result.steps:
        nid = f"s{step.order}"
        if step.inside_loop:
            lines.append(f"    style {nid} fill:#FFF3E0,stroke:#E17055,stroke-width:1px")
        elif step.inside_if:
            lines.append(f"    style {nid} fill:#FFF5F5,stroke:#D63031,stroke-width:1px")
        else:
            lines.append(f"    style {nid} fill:#E8F4FD,stroke:#0984E3,stroke-width:2px")

    lines.append("")
    return "\n".join(lines)


def _mermaid_label(step: StepCall) -> str:
    """Build a node label for Mermaid."""
    parts = []
    if step.step_label:
        parts.append(step.step_label)
    if step.outputs:
        parts.append(f"{', '.join(step.outputs)} =")
    parts.append(f"{step.callee}()")
    label = " ".join(parts)
    # Add line reference
    label += f"  :L{step.line}"
    return label


def _quote(s: str) -> str:
    """Quote a Mermaid label, choosing appropriate brackets."""
    if '"' in s:
        return f"[\"{s.replace(chr(34), '#quot;')}\"]"
    return f'["{s}"]'


def _escape_mermaid(s: str) -> str:
    """Escape special chars for Mermaid labels."""
    return s.replace('"', "'").replace("[", "(").replace("]", ")")


# ═══════════════════════════════════════════════════════════════════════
# GRAPHVIZ GENERATOR
# ═══════════════════════════════════════════════════════════════════════

def generate_graphviz(result: ExtractionResult, dep_graph: dict) -> str:
    """Generate a Graphviz DOT digraph."""
    lines = [
        f'digraph "{result.function_name}" {{',
        f'    // Auto-generated from {result.function_name}() in {Path(result.source_file).name}',
        f'    // Lines {result.function_line}-{result.function_end_line} | {result.total_steps} steps',
        '',
        '    rankdir=TB;',
        '    node [shape=box, style="rounded,filled", fontname="Helvetica", fontsize=10];',
        '    edge [fontname="Helvetica", fontsize=8, color="#636E72"];',
        '',
    ]

    edges = dep_graph["edges"]

    # Collect loop/if membership
    loop_membership: dict[str, str] = {}
    if_membership: dict[str, str] = {}
    for step in result.steps:
        nid = f"s{step.order}"
        if step.inside_loop:
            loop_membership[nid] = step.inside_loop
        if step.inside_if:
            if_membership[nid] = step.inside_if

    # Group nodes by loop context into subgraphs
    loop_groups: dict[str, list[str]] = {}
    for nid, loop_desc in loop_membership.items():
        loop_groups.setdefault(loop_desc, []).append(nid)

    if_groups: dict[str, list[str]] = {}
    for nid, cond in if_membership.items():
        if nid not in loop_membership:
            if_groups.setdefault(cond, []).append(nid)

    # Emit standalone nodes
    for step in result.steps:
        nid = f"s{step.order}"
        if nid in loop_membership or nid in if_membership:
            continue
        label = _dot_label(step)
        lines.append(f'    {nid} [label="{label}", fillcolor="#E8F4FD"];')

    # Emit loop subgraphs
    for i, (loop_desc, nids) in enumerate(loop_groups.items()):
        short = loop_desc if len(loop_desc) <= 50 else loop_desc[:47] + "..."
        lines.append('')
        lines.append(f'    subgraph cluster_loop{i} {{')
        lines.append(f'        label="LOOP: {_dot_escape(short)}";')
        lines.append('        style=dashed;')
        lines.append('        color="#E17055";')
        lines.append('        fontcolor="#E17055";')
        for step in result.steps:
            nid = f"s{step.order}"
            if nid in nids:
                label = _dot_label(step)
                lines.append(f'        {nid} [label="{label}", fillcolor="#FFF3E0"];')
        lines.append('    }')

    # Emit if subgraphs
    for i, (cond, nids) in enumerate(if_groups.items()):
        short = cond if len(cond) <= 50 else cond[:47] + "..."
        lines.append('')
        lines.append(f'    subgraph cluster_if{i} {{')
        lines.append(f'        label="IF: {_dot_escape(short)}";')
        lines.append('        style=dashed;')
        lines.append('        color="#D63031";')
        lines.append('        fontcolor="#D63031";')
        for step in result.steps:
            nid = f"s{step.order}"
            if nid in nids:
                label = _dot_label(step)
                lines.append(f'        {nid} [label="{label}", fillcolor="#FFF5F5"];')
        lines.append('    }')

    # Emit edges
    lines.append('')
    for source, targets in edges.items():
        for target in targets:
            lines.append(f'    {source} -> {target};')

    lines.append('}')
    return "\n".join(lines)


def _dot_label(step: StepCall) -> str:
    """Build a Graphviz node label."""
    parts = []
    if step.step_label:
        parts.append(step.step_label)
    if step.outputs:
        parts.append(f"{', '.join(step.outputs)} =")
    parts.append(f"{step.callee}()")
    label = " ".join(parts)
    label += f"\\nL{step.line}"
    return _dot_escape(label)


def _dot_escape(s: str) -> str:
    """Escape for Graphviz labels."""
    return s.replace('"', '\\"').replace("\n", "\\n")


# ═══════════════════════════════════════════════════════════════════════
# MAIN LOGIC
# ═══════════════════════════════════════════════════════════════════════

def extract(filepath: str | Path, function_name: str = "_execute_cycle",
            output_dir: str | Path | None = None) -> ExtractionResult:
    """
    Main extraction entry point.

    Args:
        filepath:      Path to the Python source file
        function_name: Name of the function to extract
        output_dir:    Where to write artifacts (default: ./artifacts)

    Returns:
        ExtractionResult with all extracted data
    """
    filepath = Path(filepath)
    if output_dir is None:
        output_dir = filepath.parent / "artifacts"
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Read source
    source = filepath.read_text(encoding="utf-8")
    source_lines = source.splitlines()

    # Parse AST
    tree = ast.parse(source, filename=str(filepath))

    # Find the target function
    func_node = find_function(tree, function_name)
    if func_node is None:
        available = [
            n.name for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        print(f"ERROR: Function '{function_name}' not found in {filepath}")
        print(f"Available functions: {', '.join(sorted(available))}")
        sys.exit(1)

    print(f"Extracting {function_name}() from {filepath}")
    print(f"  Lines {func_node.lineno}-{func_node.end_lineno}")

    # Extract
    extractor = FunctionExtractor(source_lines)
    result = extractor.extract(func_node)
    result.source_file = str(filepath)

    print(f"  Found {result.total_steps} function calls")
    print(f"  Found {len(result.branches)} conditional branches")
    print(f"  Found {len(result.loops)} loops")
    if result.step_labels:
        print(f"  Step labels: {', '.join(result.step_labels[:8])}...")

    # Build dependency graph
    dep_graph = build_dependency_graph(result.steps)

    # --- Write artifacts ---

    # 1. Steps JSON
    steps_path = output_dir / "execute_cycle_steps.json"
    steps_data = {
        "source_file": result.source_file,
        "function": result.function_name,
        "lines": f"{result.function_line}-{result.function_end_line}",
        "total_steps": result.total_steps,
        "step_labels": result.step_labels,
        "steps": [
            {
                "order": s.order,
                "line": s.line,
                "callee": s.callee,
                "full_callee": s.full_callee,
                "outputs": s.outputs,
                "args": s.args,
                "kwargs": {k: v for k, v in s.kwargs.items()},
                "inside_loop": s.inside_loop,
                "inside_if": s.inside_if,
                "step_label": s.step_label,
            }
            for s in result.steps
        ],
        "branches": [
            {"line": b.line, "condition": b.condition, "call_count": len(b.calls)}
            for b in result.branches
        ],
        "loops": [
            {"line": loop.line, "target": loop.target, "iterable": loop.iterable,
             "call_count": len(loop.calls)}
            for loop in result.loops
        ],
    }
    steps_path.write_text(json.dumps(steps_data, indent=2), encoding="utf-8")
    print(f"\n  Written: {steps_path}")

    # 2. Dependency graph JSON
    deps_path = output_dir / "execute_cycle_deps.json"
    deps_path.write_text(json.dumps(dep_graph, indent=2), encoding="utf-8")
    print(f"  Written: {deps_path}")

    # 3. Mermaid
    mermaid = generate_mermaid(result, dep_graph)
    mmd_path = output_dir / "execute_cycle_graph.mmd"
    mmd_path.write_text(mermaid, encoding="utf-8")
    print(f"  Written: {mmd_path}")

    # 4. Graphviz
    dot = generate_graphviz(result, dep_graph)
    dot_path = output_dir / "execute_cycle_graph.dot"
    dot_path.write_text(dot, encoding="utf-8")
    print(f"  Written: {dot_path}")

    # Print summary table
    print(f"\n{'='*70}")
    print(f"  EXECUTION ORDER: {result.function_name}()")
    print(f"{'='*70}")
    for step in result.steps:
        prefix = ""
        if step.inside_loop:
            prefix = "  [LOOP] "
        elif step.inside_if:
            prefix = "  [IF]   "
        else:
            prefix = "         "

        out = f"{', '.join(step.outputs)} = " if step.outputs else ""
        label = f"  {step.step_label}  " if step.step_label else ""

        print(f"  {step.order:3d}. {prefix}{label}{out}{step.callee}()   :L{step.line}")

    print(f"{'='*70}")
    print(f"  Total: {result.total_steps} calls | "
          f"{len(result.branches)} branches | "
          f"{len(result.loops)} loops")
    print(f"{'='*70}")

    return result


# ═══════════════════════════════════════════════════════════════════════
# CLI
# ═══════════════════════════════════════════════════════════════════════

def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Extract execution flow from a Python function via AST",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""
        Examples:
          %(prog)s runtime.py
          %(prog)s runtime.py --function run
          %(prog)s runtime.py -o output/
          %(prog)s agents.py --function generate_all_proposals
        """),
    )

    parser.add_argument("file", help="Python source file to analyze")
    parser.add_argument(
        "--function", "-f", default="_execute_cycle",
        help="Function name to extract (default: _execute_cycle)",
    )
    parser.add_argument(
        "--output", "-o", default=None,
        help="Output directory for artifacts (default: ./artifacts)",
    )

    args = parser.parse_args()
    extract(args.file, args.function, args.output)


if __name__ == "__main__":
    main()
