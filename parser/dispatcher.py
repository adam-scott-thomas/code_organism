"""
CODE ORGANISM: PARSER DISPATCHER

Routes source files to the correct parser based on file extension:

    .py   -> ast_walker.py  (CodeAnatomist, Python AST)
    .js/.ts/.java/.go/.rs/.c/.cpp/...  -> tree_sitter_parser.py
    other -> empty result
"""

from __future__ import annotations

from pathlib import Path

from ..model.nodes import Edge, OrganismNode
from .ast_walker import parse_file as _parse_python
from .tree_sitter_parser import LANGUAGE_MAP, get_parser as _get_ts_parser


def parse_file(filepath: str) -> tuple[list[OrganismNode], list[Edge]]:
    """
    Parse *filepath* using the appropriate backend.

    Returns ``(nodes, edges)`` -- always the same shape, regardless of
    language.  Unsupported extensions produce ``([], [])``.
    """
    ext = Path(filepath).suffix.lower()

    if ext == ".py":
        return _parse_python(Path(filepath))

    if ext in LANGUAGE_MAP:
        return _get_ts_parser().parse_file(filepath)

    return [], []
