"""
Code Organism Parser

Extracts anatomical structure from Python source code.
"""

from .ast_walker import parse_file, parse_source, CodeAnatomist, WalkContext

__all__ = [
    "parse_file",
    "parse_source",
    "CodeAnatomist",
    "WalkContext",
]
