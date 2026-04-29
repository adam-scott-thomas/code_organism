# SPDX-License-Identifier: Apache-2.0
"""
CODE ORGANISM: IMPACT / BLAST RADIUS ANALYSIS

Analyzes the impact of changing a symbol by traversing the
dependency graph upstream (who depends on me?) or downstream
(what do I depend on?).
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..model.organism import Organism


def analyze_impact(
    organism: Organism,
    target_id: str,
    direction: str = "upstream",
    max_depth: int = 3,
) -> dict:
    """Analyze the impact of changing a symbol.

    Performs a BFS from *target_id* in the specified direction,
    collecting affected nodes grouped by depth level.

    Args:
        organism: The organism to analyze.
        target_id: Node ID of the symbol being changed.
        direction: "upstream" follows edges backward (who calls/imports me?),
                   "downstream" follows edges forward (what do I call/import?).
        max_depth: Maximum depth to traverse (default 3).

    Returns:
        Dict keyed by depth label ("depth_1", "depth_2", ...),
        each containing a list of dicts with:
            - node_id: str
            - name: str
            - file: str
            - edge_type: str  (the edge type that connected this node)
    """
    if target_id not in organism.nodes:
        return {f"depth_{d}": [] for d in range(1, max_depth + 1)}

    # ------------------------------------------------------------------
    # 1. Build adjacency in the desired direction
    # ------------------------------------------------------------------
    adj: dict[str, list[tuple[str, str]]] = {}  # node_id -> [(neighbor_id, edge_type)]

    for edge in organism.edges.values():
        if direction == "upstream":
            # Follow edges backward: who points TO target?
            # edge: source -> target, so neighbor of target is source
            adj.setdefault(edge.target_id, []).append((edge.source_id, edge.edge_type))
        else:
            # Follow edges forward: what does target point TO?
            adj.setdefault(edge.source_id, []).append((edge.target_id, edge.edge_type))

    # ------------------------------------------------------------------
    # 2. BFS by depth level
    # ------------------------------------------------------------------
    result: dict[str, list[dict]] = {}
    visited: set[str] = {target_id}
    current_frontier: set[str] = {target_id}

    for depth in range(1, max_depth + 1):
        next_frontier: set[str] = set()
        depth_entries: list[dict] = []

        for node_id in current_frontier:
            for neighbor_id, edge_type in adj.get(node_id, []):
                if neighbor_id in visited:
                    continue
                visited.add(neighbor_id)
                next_frontier.add(neighbor_id)

                neighbor = organism.nodes.get(neighbor_id)
                if neighbor:
                    file_path = ""
                    if neighbor.position:
                        file_path = neighbor.position.file
                    depth_entries.append({
                        "node_id": neighbor_id,
                        "name": neighbor.name,
                        "file": file_path,
                        "edge_type": edge_type,
                    })

        result[f"depth_{depth}"] = depth_entries
        current_frontier = next_frontier

        if not current_frontier:
            # Fill remaining depths with empty lists
            for remaining in range(depth + 1, max_depth + 1):
                result[f"depth_{remaining}"] = []
            break

    return result
