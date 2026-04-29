# SPDX-License-Identifier: Apache-2.0
"""
CODE ORGANISM: COMPLEXITY ANALYSIS

Analyzes code complexity metrics.
Like measuring vital signs of the organism.
"""

from __future__ import annotations
import ast
import math
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class ComplexityMetrics:
    """Complexity metrics for a code unit."""
    name: str
    location: str

    # McCabe Cyclomatic Complexity
    cyclomatic: int = 1

    # Cognitive Complexity (how hard to understand)
    cognitive: int = 0

    # Halstead metrics
    vocabulary: int = 0          # n = n1 + n2 (unique operators + operands)
    length: int = 0              # N = N1 + N2 (total operators + operands)
    calculated_length: float = 0.0  # n1*log2(n1) + n2*log2(n2)
    volume: float = 0.0          # N * log2(n)
    difficulty: float = 0.0      # (n1/2) * (N2/n2)
    effort: float = 0.0          # D * V
    time_to_program: float = 0.0  # E / 18 (seconds)
    bugs_delivered: float = 0.0  # V / 3000

    # Maintainability Index (0-100, higher is better)
    maintainability_index: float = 100.0

    # Lines of code
    lines_of_code: int = 0
    logical_lines: int = 0       # Non-blank, non-comment lines
    comment_lines: int = 0
    blank_lines: int = 0

    # Nesting
    max_nesting_depth: int = 0
    avg_nesting_depth: float = 0.0


@dataclass
class ComplexityReport:
    """Full complexity report for a codebase."""
    file_path: str
    functions: list[ComplexityMetrics] = field(default_factory=list)
    classes: list[ComplexityMetrics] = field(default_factory=list)

    # Aggregate metrics
    total_lines: int = 0
    avg_cyclomatic: float = 0.0
    max_cyclomatic: int = 0
    avg_cognitive: float = 0.0
    avg_maintainability: float = 0.0

    def summarize(self) -> None:
        """Calculate aggregate metrics."""
        all_units = self.functions + self.classes

        if not all_units:
            return

        self.avg_cyclomatic = sum(u.cyclomatic for u in all_units) / len(all_units)
        self.max_cyclomatic = max(u.cyclomatic for u in all_units)
        self.avg_cognitive = sum(u.cognitive for u in all_units) / len(all_units)
        self.avg_maintainability = sum(u.maintainability_index for u in all_units) / len(all_units)

    @property
    def complexity_hotspots(self) -> list[ComplexityMetrics]:
        """Get functions with high complexity."""
        all_units = self.functions + self.classes
        return sorted(
            [u for u in all_units if u.cyclomatic > 10],
            key=lambda u: u.cyclomatic,
            reverse=True,
        )


class ComplexityAnalyzer(ast.NodeVisitor):
    """
    Analyzes code complexity.

    Measures the "vital signs" of code health:
    - How complex is it? (cyclomatic complexity)
    - How hard to understand? (cognitive complexity)
    - How maintainable? (maintainability index)
    """

    def __init__(self, filename: str, source: str):
        self.filename = filename
        self.source = source
        self.lines = source.splitlines()
        self.report = ComplexityReport(file_path=filename)

        # Tracking state
        self._current_metrics: Optional[ComplexityMetrics] = None
        self._nesting_depth = 0
        self._nesting_depths: list[int] = []

    def analyze(self) -> ComplexityReport:
        """Run complexity analysis."""
        # Count lines
        self._count_lines()

        # Parse and analyze
        try:
            tree = ast.parse(self.source, self.filename)
            self.visit(tree)
        except SyntaxError:
            pass

        self.report.summarize()
        return self.report

    def _count_lines(self) -> None:
        """Count different types of lines."""
        total = 0
        blank = 0
        comment = 0
        logical = 0

        in_multiline_string = False

        for line in self.lines:
            total += 1
            stripped = line.strip()

            if not stripped:
                blank += 1
            elif stripped.startswith('#'):
                comment += 1
            elif stripped.startswith('"""') or stripped.startswith("'''"):
                comment += 1
                if stripped.count('"""') == 1 or stripped.count("'''") == 1:
                    in_multiline_string = not in_multiline_string
            elif in_multiline_string:
                comment += 1
            else:
                logical += 1

        self.report.total_lines = total

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._analyze_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._analyze_function(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        metrics = ComplexityMetrics(
            name=node.name,
            location=f"{self.filename}:{node.lineno}",
        )

        # Count lines
        if node.end_lineno:
            metrics.lines_of_code = node.end_lineno - node.lineno + 1

        # Class complexity is sum of method complexities
        for child in node.body:
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method_metrics = self._compute_function_metrics(child)
                metrics.cyclomatic += method_metrics.cyclomatic
                metrics.cognitive += method_metrics.cognitive

        # Maintainability
        metrics.maintainability_index = self._compute_maintainability(
            metrics.cyclomatic,
            metrics.lines_of_code,
            0,  # Would need Halstead for full calculation
        )

        self.report.classes.append(metrics)
        self.generic_visit(node)

    def _analyze_function(self, node) -> None:
        """Analyze a function definition."""
        metrics = self._compute_function_metrics(node)
        self.report.functions.append(metrics)

    def _compute_function_metrics(self, node) -> ComplexityMetrics:
        """Compute all metrics for a function."""
        metrics = ComplexityMetrics(
            name=node.name,
            location=f"{self.filename}:{node.lineno}",
        )

        # Lines of code
        if node.end_lineno:
            metrics.lines_of_code = node.end_lineno - node.lineno + 1

        # Cyclomatic complexity
        metrics.cyclomatic = self._compute_cyclomatic(node)

        # Cognitive complexity
        metrics.cognitive = self._compute_cognitive(node)

        # Nesting depth
        self._nesting_depths = []
        self._compute_nesting_depth(node, 0)
        if self._nesting_depths:
            metrics.max_nesting_depth = max(self._nesting_depths)
            metrics.avg_nesting_depth = sum(self._nesting_depths) / len(self._nesting_depths)

        # Halstead metrics
        halstead = self._compute_halstead(node)
        metrics.vocabulary = halstead.get("vocabulary", 0)
        metrics.length = halstead.get("length", 0)
        metrics.volume = halstead.get("volume", 0)
        metrics.difficulty = halstead.get("difficulty", 0)
        metrics.effort = halstead.get("effort", 0)
        metrics.bugs_delivered = halstead.get("bugs", 0)

        # Maintainability Index
        metrics.maintainability_index = self._compute_maintainability(
            metrics.cyclomatic,
            metrics.lines_of_code,
            metrics.volume,
        )

        return metrics

    def _compute_cyclomatic(self, node: ast.AST) -> int:
        """
        Compute McCabe cyclomatic complexity.

        CC = 1 + number of decision points
        """
        complexity = 1

        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)):
                complexity += 1
            elif isinstance(child, ast.ExceptHandler):
                complexity += 1
            elif isinstance(child, ast.BoolOp):
                # Each 'and'/'or' adds a path
                complexity += len(child.values) - 1
            elif isinstance(child, ast.IfExp):  # Ternary
                complexity += 1
            elif isinstance(child, ast.comprehension):
                complexity += 1
                complexity += len(child.ifs)
            elif isinstance(child, ast.Assert):
                complexity += 1

        return complexity

    def _compute_cognitive(self, node: ast.AST) -> int:
        """
        Compute cognitive complexity.

        Unlike cyclomatic complexity, this measures how hard
        code is for a human to understand.
        """
        complexity = 0
        nesting = 0

        def walk(n: ast.AST, nesting_level: int) -> int:
            nonlocal complexity

            increment = 0
            nesting_increment = 0

            # Structural increments
            if isinstance(n, (ast.If, ast.IfExp)):
                increment += 1 + nesting_level  # +1 base, +nesting
                nesting_increment = 1
            elif isinstance(n, (ast.For, ast.AsyncFor, ast.While)):
                increment += 1 + nesting_level
                nesting_increment = 1
            elif isinstance(n, ast.ExceptHandler):
                increment += 1 + nesting_level
                nesting_increment = 1
            elif isinstance(n, ast.With):
                nesting_increment = 1

            # Boolean operators
            elif isinstance(n, ast.BoolOp):
                increment += len(n.values) - 1

            # Recursion
            elif isinstance(n, ast.Call):
                if isinstance(n.func, ast.Name):
                    # Check if calling itself (simple recursion detection)
                    # Would need context for full detection
                    pass

            # Break/continue interrupts linear flow
            elif isinstance(n, (ast.Break, ast.Continue)):
                increment += 1

            complexity += increment

            # Recurse with updated nesting
            for child in ast.iter_child_nodes(n):
                walk(child, nesting_level + nesting_increment)

        walk(node, 0)
        return complexity

    def _compute_nesting_depth(self, node: ast.AST, depth: int) -> None:
        """Compute nesting depths throughout the function."""
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.With,
                                 ast.Try, ast.AsyncFor, ast.AsyncWith)):
                self._nesting_depths.append(depth + 1)
                self._compute_nesting_depth(child, depth + 1)
            else:
                self._compute_nesting_depth(child, depth)

    def _compute_halstead(self, node: ast.AST) -> dict:
        """
        Compute Halstead complexity metrics.

        Halstead's metrics measure the "size" of code in terms
        of operators and operands.
        """
        operators = set()
        operands = set()
        operator_count = 0
        operand_count = 0

        for child in ast.walk(node):
            # Operators
            if isinstance(child, ast.BinOp):
                op_name = type(child.op).__name__
                operators.add(op_name)
                operator_count += 1
            elif isinstance(child, ast.UnaryOp):
                op_name = type(child.op).__name__
                operators.add(op_name)
                operator_count += 1
            elif isinstance(child, ast.BoolOp):
                op_name = type(child.op).__name__
                operators.add(op_name)
                operator_count += len(child.values) - 1
            elif isinstance(child, ast.Compare):
                for op in child.ops:
                    op_name = type(op).__name__
                    operators.add(op_name)
                    operator_count += 1
            elif isinstance(child, ast.Call):
                operators.add("()")
                operator_count += 1
            elif isinstance(child, ast.Subscript):
                operators.add("[]")
                operator_count += 1
            elif isinstance(child, ast.Attribute):
                operators.add(".")
                operator_count += 1

            # Operands
            elif isinstance(child, ast.Name):
                operands.add(child.id)
                operand_count += 1
            elif isinstance(child, ast.Constant):
                operands.add(str(child.value))
                operand_count += 1

        n1 = len(operators)  # Unique operators
        n2 = len(operands)   # Unique operands
        N1 = operator_count  # Total operators
        N2 = operand_count   # Total operands

        n = n1 + n2  # Vocabulary
        N = N1 + N2  # Length

        if n == 0 or n2 == 0:
            return {
                "vocabulary": n,
                "length": N,
                "volume": 0,
                "difficulty": 0,
                "effort": 0,
                "bugs": 0,
            }

        # Calculated length
        calc_length = n1 * math.log2(max(n1, 1)) + n2 * math.log2(max(n2, 1))

        # Volume
        volume = N * math.log2(max(n, 1))

        # Difficulty
        difficulty = (n1 / 2) * (N2 / max(n2, 1))

        # Effort
        effort = difficulty * volume

        # Time (in seconds)
        time_to_program = effort / 18

        # Bugs delivered (estimate)
        bugs = volume / 3000

        return {
            "vocabulary": n,
            "length": N,
            "calculated_length": calc_length,
            "volume": volume,
            "difficulty": difficulty,
            "effort": effort,
            "time": time_to_program,
            "bugs": bugs,
        }

    def _compute_maintainability(self, cyclomatic: int, loc: int, volume: float) -> float:
        """
        Compute Maintainability Index.

        MI = 171 - 5.2 * ln(V) - 0.23 * CC - 16.2 * ln(LOC)

        Normalized to 0-100 scale.
        """
        if loc == 0:
            return 100.0

        # Handle edge cases
        v = max(volume, 1)
        cc = cyclomatic
        lines = max(loc, 1)

        # Original MI formula
        mi = 171 - 5.2 * math.log(v) - 0.23 * cc - 16.2 * math.log(lines)

        # Normalize to 0-100
        mi = max(0, mi * 100 / 171)

        return round(mi, 2)


def analyze_complexity(source: str, filename: str = "<string>") -> ComplexityReport:
    """
    Analyze complexity of source code.

    Args:
        source: Python source code
        filename: Filename for error messages

    Returns:
        ComplexityReport with all metrics
    """
    analyzer = ComplexityAnalyzer(filename, source)
    return analyzer.analyze()
