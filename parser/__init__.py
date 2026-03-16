"""
Code Organism Parser

Extracts anatomical structure from source code.

- Python files are parsed via the built-in ``ast`` module (ast_walker).
- Other supported languages use tree-sitter (tree_sitter_parser).
- The ``dispatcher`` module selects the right backend automatically.
"""

from .ast_walker import parse_file as parse_python_file, parse_source, CodeAnatomist, WalkContext
from .tree_sitter_parser import TreeSitterParser, LANGUAGE_MAP
from .dispatcher import parse_file

__all__ = [
    # Dispatcher (preferred entry point)
    "parse_file",
    # Python-specific
    "parse_python_file",
    "parse_source",
    "CodeAnatomist",
    "WalkContext",
    # Multi-language
    "TreeSitterParser",
    "LANGUAGE_MAP",
]
