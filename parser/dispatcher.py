# SPDX-License-Identifier: Apache-2.0
"""
CODE ORGANISM: PARSER DISPATCHER

Routes source files to the correct parser based on file extension:

    .py   -> ast_walker.py  (CodeAnatomist, Python AST)
    .js/.ts/.java/.go/.rs/.c/.cpp/...  -> tree_sitter_parser.py
    other -> empty result

Also provides a second-pass cross-file call resolver that retargets
BUILTIN placeholder edges to real definitions found in other files.
"""

from __future__ import annotations

import logging
from pathlib import Path

from ..model.nodes import Edge, NodeType, OrganismNode
from .ast_walker import parse_file as _parse_python
from .tree_sitter_parser import LANGUAGE_MAP, get_parser as _get_ts_parser

logger = logging.getLogger(__name__)


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


def resolve_cross_file_calls(
    all_nodes: list[OrganismNode],
    all_edges: list[Edge],
) -> list[Edge]:
    """Second pass: resolve EXTERNAL/BUILTIN call targets to actual definitions across files.

    For each call edge pointing to a BUILTIN node, check if there is a real
    Function, Method, or Class node with the same name defined elsewhere in
    the project.  If so, retarget the edge and remove the now-orphaned
    BUILTIN placeholder.

    This is intentionally conservative:
    - Only retargets ``call`` edges (not imports or references).
    - Only resolves when there is exactly one candidate with the matching
      name to avoid ambiguous resolution.
    - When a BUILTIN node has no remaining inbound edges after retargeting,
      it is removed from *all_nodes* in-place.

    Args:
        all_nodes: Combined node list from all parsed files (mutated in-place
            to remove orphaned BUILTIN nodes).
        all_edges: Combined edge list from all parsed files (mutated in-place
            to retarget resolved edges).

    Returns:
        The same *all_edges* list (for convenience; it is also mutated in-place).
    """
    # Build index: name -> list of (node_id, node_type) for real definitions
    # "Real" = FUNCTION, METHOD, or CLASS (not BUILTIN, not EXTERNAL_MODULE)
    _REAL_TYPES = {NodeType.FUNCTION, NodeType.METHOD, NodeType.CLASS}
    name_to_real: dict[str, list[str]] = {}
    for node in all_nodes:
        if node.node_type in _REAL_TYPES:
            name_to_real.setdefault(node.name, []).append(node.id)

    # Build index: node_id -> node for quick lookup
    node_by_id: dict[str, OrganismNode] = {n.id: n for n in all_nodes}

    # Identify BUILTIN node IDs
    builtin_ids: set[str] = {
        n.id for n in all_nodes if n.node_type == NodeType.BUILTIN
    }

    resolved_count = 0

    for edge in all_edges:
        if edge.edge_type != "call":
            continue
        if edge.target_id not in builtin_ids:
            continue

        builtin_node = node_by_id.get(edge.target_id)
        if builtin_node is None:
            continue

        candidates = name_to_real.get(builtin_node.name, [])
        if len(candidates) == 1:
            # Unambiguous resolution -- retarget the edge
            old_target = edge.target_id
            new_target = candidates[0]
            edge.target_id = new_target
            # Recompute the edge ID to stay consistent
            edge.id = Edge.generate_id(edge.source_id, new_target, edge.edge_type)
            resolved_count += 1
            logger.debug(
                "Resolved cross-file call: %s -> %s (was BUILTIN %s)",
                edge.source_id[:8], new_target[:8], builtin_node.name,
            )

    # Clean up orphaned BUILTIN nodes (no remaining inbound edges)
    remaining_targets = {e.target_id for e in all_edges}
    orphaned = [
        n for n in all_nodes
        if n.node_type == NodeType.BUILTIN and n.id not in remaining_targets
    ]
    for orphan in orphaned:
        all_nodes.remove(orphan)

    if resolved_count:
        logger.info(
            "Cross-file resolution: retargeted %d call edge(s), "
            "removed %d orphaned BUILTIN node(s)",
            resolved_count, len(orphaned),
        )

    return all_edges
