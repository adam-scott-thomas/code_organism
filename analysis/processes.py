"""
CODE ORGANISM: PROCESS / EXECUTION FLOW DETECTION

Detects execution flows through the call graph using BFS.
Identifies entry points (functions with no internal callers that
have callees) and traces paths through the code.
"""

from __future__ import annotations

from collections import deque
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..model.organism import Organism

from ..model.nodes import NodeType


# Node types that can participate in execution flows
_CALLABLE_TYPES = frozenset({
    NodeType.FUNCTION,
    NodeType.METHOD,
})

# Maximum constants
_MAX_DEPTH = 10
_MAX_BRANCH = 4
_MIN_STEPS = 3
_MAX_PROCESSES = 75


def detect_processes(organism: Organism) -> list[dict]:
    """Detect execution flows through the call graph.

    Algorithm:
    1. Build call adjacency from edges with edge_type == "call"
    2. Find entry points: functions/methods with no internal callers
       that DO have callees
    3. Score entry points by number of callees, sort descending
    4. BFS from each entry point, max depth 10, max branch factor 4
    5. Keep traces with >= 3 steps
    6. Deduplicate: remove traces that are subsets of longer traces
    7. Limit to 75 processes

    Args:
        organism: The organism to analyze.

    Returns:
        List of process dicts, each containing:
            - id: str            -- process identifier
            - name: str          -- auto-generated from entry + terminal
            - entry_point: str   -- node ID of the entry function
            - terminal: str      -- node ID of the last step
            - steps: list[dict]  -- ordered steps with step number, node_id, name
            - step_count: int    -- number of steps
    """
    if not organism.nodes:
        return []

    # ------------------------------------------------------------------
    # 0. Build name-resolution map
    # ------------------------------------------------------------------
    # The parser creates BUILTIN/EXTERNAL placeholder nodes for call
    # targets. When a real FUNCTION/METHOD/CLASS with the same name
    # exists, we resolve the placeholder to the real node so that
    # call chains connect properly.
    resolve: dict[str, str] = {}  # placeholder_id -> real_id
    _RESOLVABLE = frozenset({NodeType.BUILTIN, NodeType.EXTERNAL_MODULE})
    name_to_real: dict[str, str] = {}
    for node in organism.nodes.values():
        if node.node_type in _CALLABLE_TYPES or node.node_type == NodeType.CLASS:
            name_to_real[node.name] = node.id
    for node in organism.nodes.values():
        if node.node_type in _RESOLVABLE and node.name in name_to_real:
            real_id = name_to_real[node.name]
            if real_id != node.id:
                resolve[node.id] = real_id

    def _resolve(nid: str) -> str:
        return resolve.get(nid, nid)

    # ------------------------------------------------------------------
    # 1. Build call adjacency (forward: caller -> [callees])
    # ------------------------------------------------------------------
    # Only include edges between nodes that actually exist in the organism
    forward_adj: dict[str, list[str]] = {}
    callee_set: set[str] = set()  # nodes that are called by something internal

    for edge in organism.edges.values():
        if edge.edge_type != "call":
            continue
        src = _resolve(edge.source_id)
        tgt = _resolve(edge.target_id)
        # Both endpoints must exist in the organism
        if src not in organism.nodes or tgt not in organism.nodes:
            continue
        forward_adj.setdefault(src, []).append(tgt)
        callee_set.add(tgt)

    if not forward_adj:
        return []

    # ------------------------------------------------------------------
    # 2. Find entry points
    # ------------------------------------------------------------------
    # Entry point = has callees AND is not called by any internal node
    callable_ids = set()
    for node in organism.nodes.values():
        if node.node_type in _CALLABLE_TYPES:
            callable_ids.add(node.id)

    entry_points: list[str] = []
    for nid in callable_ids:
        has_callees = nid in forward_adj and len(forward_adj[nid]) > 0
        is_not_called = nid not in callee_set
        if has_callees and is_not_called:
            entry_points.append(nid)

    if not entry_points:
        # Fallback: use all nodes with callees, sorted by callee count
        entry_points = list(forward_adj.keys())

    # ------------------------------------------------------------------
    # 3. Score and sort entry points
    # ------------------------------------------------------------------
    entry_points.sort(key=lambda nid: len(forward_adj.get(nid, [])), reverse=True)

    # ------------------------------------------------------------------
    # 4. BFS from each entry point
    # ------------------------------------------------------------------
    all_traces: list[list[str]] = []

    for ep in entry_points:
        traces = _bfs_traces(ep, forward_adj, _MAX_DEPTH, _MAX_BRANCH)
        all_traces.extend(traces)

    # ------------------------------------------------------------------
    # 5. Filter: keep only traces with >= MIN_STEPS
    # ------------------------------------------------------------------
    all_traces = [t for t in all_traces if len(t) >= _MIN_STEPS]

    if not all_traces:
        return []

    # ------------------------------------------------------------------
    # 6. Deduplicate: remove traces that are subsets of longer ones
    # ------------------------------------------------------------------
    all_traces = _deduplicate_traces(all_traces)

    # ------------------------------------------------------------------
    # 7. Limit to MAX_PROCESSES
    # ------------------------------------------------------------------
    # Sort by length descending (prefer longer, more informative traces)
    all_traces.sort(key=len, reverse=True)
    all_traces = all_traces[:_MAX_PROCESSES]

    # ------------------------------------------------------------------
    # Build result dicts
    # ------------------------------------------------------------------
    processes: list[dict] = []
    for idx, trace in enumerate(all_traces):
        entry_node = organism.nodes.get(trace[0])
        terminal_node = organism.nodes.get(trace[-1])
        entry_name = entry_node.name if entry_node else trace[0][:8]
        terminal_name = terminal_node.name if terminal_node else trace[-1][:8]

        steps = []
        for step_idx, nid in enumerate(trace):
            node = organism.nodes.get(nid)
            steps.append({
                "step": step_idx,
                "node_id": nid,
                "name": node.name if node else nid[:8],
            })

        name = f"{entry_name} -> {terminal_name}"

        processes.append({
            "id": f"process_{idx}",
            "name": name,
            "entry_point": trace[0],
            "terminal": trace[-1],
            "steps": steps,
            "step_count": len(trace),
        })

    return processes


# ======================================================================
# Internal helpers
# ======================================================================

def _bfs_traces(
    start: str,
    adj: dict[str, list[str]],
    max_depth: int,
    max_branch: int,
) -> list[list[str]]:
    """BFS from *start*, collecting all maximal paths.

    At each node we follow up to *max_branch* callees (sorted by
    their own callee count so we prefer richer paths). We stop at
    *max_depth* or when there are no more callees.

    Returns a list of traces (each trace is a list of node IDs).
    """
    # Each queue entry: (current_path,)
    queue: deque[list[str]] = deque()
    queue.append([start])

    completed: list[list[str]] = []

    while queue:
        path = queue.popleft()
        current = path[-1]
        depth = len(path)

        if depth > max_depth:
            completed.append(path)
            continue

        children = adj.get(current, [])
        if not children:
            completed.append(path)
            continue

        # Avoid revisiting nodes already in the path (cycle prevention)
        visited = set(path)
        children = [c for c in children if c not in visited]

        if not children:
            completed.append(path)
            continue

        # Sort children: prefer those with more callees (richer paths)
        children.sort(key=lambda c: len(adj.get(c, [])), reverse=True)

        # Limit branch factor
        children = children[:max_branch]

        for child in children:
            queue.append(path + [child])

    return completed


def _deduplicate_traces(traces: list[list[str]]) -> list[list[str]]:
    """Remove traces that are strict subsets of longer traces.

    A trace A is a subset of trace B if every node in A appears in B
    in the same order (i.e., A is a subsequence of B).
    """
    # Sort longest first
    traces.sort(key=len, reverse=True)

    # Convert to tuples for set membership and comparison
    trace_tuples = [tuple(t) for t in traces]
    kept: list[tuple[str, ...]] = []

    for candidate in trace_tuples:
        is_subset = False
        for longer in kept:
            if len(longer) > len(candidate) and _is_subsequence(candidate, longer):
                is_subset = True
                break
        if not is_subset:
            kept.append(candidate)

    return [list(t) for t in kept]


def _is_subsequence(short: tuple[str, ...], long: tuple[str, ...]) -> bool:
    """Check if *short* is a subsequence of *long*."""
    it = iter(long)
    return all(item in it for item in short)
