# SPDX-License-Identifier: Apache-2.0
"""
CODE ORGANISM: CODE PATTERN DETECTION

Detects common anti-patterns and code smells.
These are not necessarily malicious, but indicate
poor code health - like detecting chronic conditions
in the organism.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from enum import Enum


class PatternSeverity(Enum):
    """Severity of a code pattern."""
    INFO = "info"          # Just informational
    WARNING = "warning"    # Should be addressed
    ERROR = "error"        # Serious issue


@dataclass
class Pattern:
    """A detected code pattern."""
    name: str
    severity: PatternSeverity
    description: str
    location: str
    suggestion: str
    category: str


@dataclass
class PatternDetectionResult:
    """Result of pattern detection."""
    patterns: list[Pattern] = field(default_factory=list)

    @property
    def info_count(self) -> int:
        return sum(1 for p in self.patterns if p.severity == PatternSeverity.INFO)

    @property
    def warning_count(self) -> int:
        return sum(1 for p in self.patterns if p.severity == PatternSeverity.WARNING)

    @property
    def error_count(self) -> int:
        return sum(1 for p in self.patterns if p.severity == PatternSeverity.ERROR)


class PatternDetector(ast.NodeVisitor):
    """
    Detects code patterns and anti-patterns.

    Like a health screening - we're looking for conditions
    that indicate the code could be healthier.
    """

    def __init__(self, filename: str, source: str):
        self.filename = filename
        self.source = source
        self.lines = source.splitlines()
        self.result = PatternDetectionResult()

        # Context tracking
        self._in_class = False
        self._in_function = False
        self._function_depth = 0
        self._current_function_lines = 0
        self._current_function_args = 0

    def analyze(self) -> PatternDetectionResult:
        """Run pattern detection."""
        try:
            tree = ast.parse(self.source, self.filename)
            self.visit(tree)
        except SyntaxError as e:
            self.result.patterns.append(Pattern(
                name="syntax_error",
                severity=PatternSeverity.ERROR,
                description=f"Syntax error: {e.msg}",
                location=f"{self.filename}:{e.lineno}",
                suggestion="Fix the syntax error",
                category="syntax",
            ))

        # Post-analysis patterns
        self._check_file_patterns()

        return self.result

    def _add_pattern(self, name: str, severity: PatternSeverity,
                     description: str, node: ast.AST,
                     suggestion: str, category: str) -> None:
        """Add a detected pattern."""
        self.result.patterns.append(Pattern(
            name=name,
            severity=severity,
            description=description,
            location=f"{self.filename}:{node.lineno}",
            suggestion=suggestion,
            category=category,
        ))

    # =========================================================================
    # FUNCTION PATTERNS
    # =========================================================================

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._check_function(node)
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._check_function(node)
        self.generic_visit(node)

    def _check_function(self, node) -> None:
        """Check a function for patterns."""
        # Long function
        lines = (node.end_lineno or node.lineno) - node.lineno
        if lines > 50:
            self._add_pattern(
                "long_function",
                PatternSeverity.WARNING,
                f"Function '{node.name}' is {lines} lines long",
                node,
                "Consider breaking into smaller functions",
                "complexity",
            )

        # Too many arguments
        arg_count = len(node.args.args) + len(node.args.kwonlyargs)
        if arg_count > 5:
            self._add_pattern(
                "too_many_arguments",
                PatternSeverity.WARNING,
                f"Function '{node.name}' has {arg_count} arguments",
                node,
                "Consider using a configuration object or breaking up the function",
                "complexity",
            )

        # Missing docstring
        if not ast.get_docstring(node):
            if not node.name.startswith("_"):
                self._add_pattern(
                    "missing_docstring",
                    PatternSeverity.INFO,
                    f"Function '{node.name}' has no docstring",
                    node,
                    "Add a docstring to document the function",
                    "documentation",
                )

        # Check for deep nesting
        max_depth = self._get_max_nesting_depth(node)
        if max_depth > 4:
            self._add_pattern(
                "deep_nesting",
                PatternSeverity.WARNING,
                f"Function '{node.name}' has nesting depth of {max_depth}",
                node,
                "Reduce nesting by extracting functions or using early returns",
                "complexity",
            )

        # Check for bare except
        for child in ast.walk(node):
            if isinstance(child, ast.ExceptHandler):
                if child.type is None:
                    self._add_pattern(
                        "bare_except",
                        PatternSeverity.WARNING,
                        "Bare 'except:' catches all exceptions",
                        child,
                        "Catch specific exceptions instead",
                        "error_handling",
                    )

    def _get_max_nesting_depth(self, node: ast.AST) -> int:
        """Calculate maximum nesting depth in a function."""
        max_depth = 0

        def walk_depth(n: ast.AST, depth: int) -> None:
            nonlocal max_depth
            max_depth = max(max_depth, depth)

            for child in ast.iter_child_nodes(n):
                if isinstance(child, (ast.If, ast.For, ast.While, ast.With,
                                     ast.Try, ast.AsyncFor, ast.AsyncWith)):
                    walk_depth(child, depth + 1)
                else:
                    walk_depth(child, depth)

        walk_depth(node, 0)
        return max_depth

    # =========================================================================
    # CLASS PATTERNS
    # =========================================================================

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Check a class for patterns."""
        # Missing docstring
        if not ast.get_docstring(node):
            self._add_pattern(
                "missing_class_docstring",
                PatternSeverity.INFO,
                f"Class '{node.name}' has no docstring",
                node,
                "Add a docstring to document the class",
                "documentation",
            )

        # Count methods
        methods = [n for n in node.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]
        if len(methods) > 20:
            self._add_pattern(
                "god_class",
                PatternSeverity.WARNING,
                f"Class '{node.name}' has {len(methods)} methods (God class)",
                node,
                "Consider splitting into multiple classes",
                "design",
            )

        # Check for __init__ with too much logic
        for method in methods:
            if method.name == "__init__":
                lines = (method.end_lineno or method.lineno) - method.lineno
                if lines > 30:
                    self._add_pattern(
                        "complex_init",
                        PatternSeverity.WARNING,
                        f"__init__ is {lines} lines long",
                        method,
                        "Move initialization logic to separate methods",
                        "complexity",
                    )

        self.generic_visit(node)

    # =========================================================================
    # VARIABLE PATTERNS
    # =========================================================================

    def visit_Name(self, node: ast.Name) -> None:
        """Check variable names."""
        name = node.id

        # Single letter names (except common ones)
        if len(name) == 1 and name not in ('i', 'j', 'k', 'n', 'x', 'y', 'z', '_'):
            self._add_pattern(
                "single_letter_variable",
                PatternSeverity.INFO,
                f"Single-letter variable name '{name}'",
                node,
                "Use descriptive variable names",
                "naming",
            )

        self.generic_visit(node)

    # =========================================================================
    # EXPRESSION PATTERNS
    # =========================================================================

    def visit_Compare(self, node: ast.Compare) -> None:
        """Check comparison patterns."""
        # Check for `== True` or `== False`
        for op, comparator in zip(node.ops, node.comparators, strict=False):
            if isinstance(op, ast.Eq):
                if isinstance(comparator, ast.Constant):
                    if comparator.value is True:
                        self._add_pattern(
                            "compare_to_true",
                            PatternSeverity.INFO,
                            "Comparing to True explicitly",
                            node,
                            "Use 'if x:' instead of 'if x == True:'",
                            "style",
                        )
                    elif comparator.value is False:
                        self._add_pattern(
                            "compare_to_false",
                            PatternSeverity.INFO,
                            "Comparing to False explicitly",
                            node,
                            "Use 'if not x:' instead of 'if x == False:'",
                            "style",
                        )

        self.generic_visit(node)

    def visit_BoolOp(self, node: ast.BoolOp) -> None:
        """Check boolean operations."""
        # Long boolean expressions
        if len(node.values) > 3:
            self._add_pattern(
                "long_boolean_expression",
                PatternSeverity.INFO,
                f"Boolean expression with {len(node.values)} terms",
                node,
                "Consider extracting to a named variable or function",
                "complexity",
            )

        self.generic_visit(node)

    # =========================================================================
    # IMPORT PATTERNS
    # =========================================================================

    def visit_Import(self, node: ast.Import) -> None:
        """Check import patterns."""
        # Star imports are handled in ImportFrom
        # Check for multiple imports on one line
        if len(node.names) > 3:
            self._add_pattern(
                "many_imports_one_line",
                PatternSeverity.INFO,
                f"Multiple imports on one line ({len(node.names)} modules)",
                node,
                "Put each import on its own line",
                "style",
            )

        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Check from...import patterns."""
        # Star imports
        for alias in node.names:
            if alias.name == "*":
                self._add_pattern(
                    "star_import",
                    PatternSeverity.WARNING,
                    f"Star import from '{node.module}'",
                    node,
                    "Import specific names instead of using *",
                    "imports",
                )

        self.generic_visit(node)

    # =========================================================================
    # FILE-LEVEL PATTERNS
    # =========================================================================

    def _check_file_patterns(self) -> None:
        """Check file-level patterns."""
        # Long file
        if len(self.lines) > 500:
            self.result.patterns.append(Pattern(
                name="long_file",
                severity=PatternSeverity.WARNING,
                description=f"File is {len(self.lines)} lines long",
                location=f"{self.filename}:1",
                suggestion="Consider splitting into multiple modules",
                category="organization",
            ))

        # Check for TODO/FIXME comments
        for i, line in enumerate(self.lines, 1):
            if re.search(r'\b(TODO|FIXME|XXX|HACK)\b', line, re.IGNORECASE):
                self.result.patterns.append(Pattern(
                    name="todo_comment",
                    severity=PatternSeverity.INFO,
                    description="TODO/FIXME comment found",
                    location=f"{self.filename}:{i}",
                    suggestion="Address the TODO or create a ticket",
                    category="documentation",
                ))

        # Check for print statements (debugging left in)
        for i, line in enumerate(self.lines, 1):
            if re.match(r'^\s*print\s*\(', line):
                self.result.patterns.append(Pattern(
                    name="print_statement",
                    severity=PatternSeverity.INFO,
                    description="Print statement found",
                    location=f"{self.filename}:{i}",
                    suggestion="Use logging instead of print for production code",
                    category="debugging",
                ))


def detect_patterns(source: str, filename: str = "<string>") -> PatternDetectionResult:
    """
    Detect code patterns in source code.

    Args:
        source: Python source code
        filename: Filename for error messages

    Returns:
        PatternDetectionResult with all detected patterns
    """
    detector = PatternDetector(filename, source)
    return detector.analyze()
