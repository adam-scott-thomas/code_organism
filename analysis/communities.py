"""
CODE ORGANISM: COMMUNITY DETECTION

Detects functional communities within the code organism using
Leiden community detection (via igraph). Communities represent
clusters of tightly-coupled code that form logical subsystems.

Strategy:
  1. Build a graph from ALL edge types between structural nodes.
  2. Add co-location edges so nodes in the same module cluster together.
  3. Run Leiden with a low resolution (default 0.1) to produce broad clusters.
  4. Merge small communities into their nearest neighbor.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..model.organism import Organism

from ..model.nodes import NodeType

# Structural node types eligible for community membership
_STRUCTURAL_TYPES = frozenset({
    NodeType.MODULE,
    NodeType.CLASS,
    NodeType.FUNCTION,
    NodeType.METHOD,
})

# All edge types used for clustering (not just call/import/reference)
_CLUSTERING_EDGE_TYPES = frozenset({
    "call", "import", "reference", "inheritance", "composition",
    "import_type_only",
})

# Minimum community size — smaller communities get merged
_MIN_COMMUNITY_SIZE = 3


def detect_communities(
    organism: Organism,
    resolution: float = 0.1,
    min_community_size: int = _MIN_COMMUNITY_SIZE,
) -> list[dict]:
    """Detect functional communities in the code organism.

    Uses the Leiden algorithm (modularity objective) on a graph built
    from edges between structural nodes, augmented with co-location
    edges for nodes sharing a module.

    Args:
        organism: The organism to analyze.
        resolution: Leiden resolution parameter. Lower values produce
            fewer, larger communities. Default 0.1.
        min_community_size: Communities smaller than this are merged
            into their nearest neighbor.

    Returns:
        List of community dicts, each containing:
            - id: str          -- community identifier
            - name: str        -- auto-generated descriptive name
            - members: list    -- node IDs belonging to this community
            - cohesion: float  -- internal edge density (0.0-1.0)
            - keywords: list   -- representative keywords from member names
    """
    import igraph

    # ------------------------------------------------------------------
    # 1. Filter to structural nodes
    # ------------------------------------------------------------------
    structural_ids: list[str] = []
    for node in organism.nodes.values():
        if node.node_type in _STRUCTURAL_TYPES:
            structural_ids.append(node.id)

    if not structural_ids:
        return []

    # Single community when fewer than 3 structural nodes
    if len(structural_ids) < 3:
        members = structural_ids
        return [_build_community_dict(
            community_idx=0,
            member_ids=members,
            organism=organism,
            internal_edges=0,
        )]

    # ------------------------------------------------------------------
    # 2. Build igraph.Graph from edges
    # ------------------------------------------------------------------
    id_set = set(structural_ids)
    id_to_idx: dict[str, int] = {nid: i for i, nid in enumerate(structural_ids)}

    edge_set: set[tuple[int, int]] = set()

    # 2a. Add edges from organism (all clustering-relevant types)
    for edge in organism.edges.values():
        if edge.edge_type not in _CLUSTERING_EDGE_TYPES:
            continue
        src = edge.source_id
        tgt = edge.target_id
        if src in id_set and tgt in id_set:
            pair = (id_to_idx[src], id_to_idx[tgt])
            edge_set.add(pair)

    # 2b. Add co-location edges: structural nodes sharing a module
    #     prefix are likely related. This connects functions/classes
    #     defined in the same file even if they don't call each other.
    module_groups: dict[str, list[str]] = defaultdict(list)
    for nid in structural_ids:
        node = organism.nodes.get(nid)
        if node and node.qualified_name:
            # Module prefix = first dotted component (e.g. "cli" from "cli.main")
            parts = node.qualified_name.split(".")
            if len(parts) >= 2:
                module_prefix = parts[0]
            else:
                module_prefix = node.qualified_name
            module_groups[module_prefix].append(nid)

    for _mod, members in module_groups.items():
        if len(members) < 2:
            continue
        # Connect all members of the same module to each other
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = id_to_idx[members[i]], id_to_idx[members[j]]
                edge_set.add((min(a, b), max(a, b)))

    edge_list = list(edge_set)

    g = igraph.Graph(n=len(structural_ids), edges=edge_list, directed=False)

    # ------------------------------------------------------------------
    # 3. Run Leiden community detection
    # ------------------------------------------------------------------
    partition = g.community_leiden(
        objective_function="modularity",
        resolution=resolution,
        n_iterations=10,
    )

    # ------------------------------------------------------------------
    # 4. Group members by community
    # ------------------------------------------------------------------
    community_members: dict[int, list[str]] = {}
    for vtx_idx, comm_idx in enumerate(partition.membership):
        community_members.setdefault(comm_idx, []).append(structural_ids[vtx_idx])

    # ------------------------------------------------------------------
    # 5. Merge small communities into nearest neighbor
    # ------------------------------------------------------------------
    membership = list(partition.membership)  # mutable copy
    membership = _merge_small_communities(
        membership=membership,
        structural_ids=structural_ids,
        graph=g,
        min_size=min_community_size,
    )

    # Rebuild community groups from merged membership
    community_members = {}
    for vtx_idx, comm_idx in enumerate(membership):
        community_members.setdefault(comm_idx, []).append(structural_ids[vtx_idx])

    # ------------------------------------------------------------------
    # 6. Count internal edges per community (using original organism edges)
    # ------------------------------------------------------------------
    internal_edge_counts: dict[int, int] = Counter()
    for edge in organism.edges.values():
        if edge.edge_type not in _CLUSTERING_EDGE_TYPES:
            continue
        src = edge.source_id
        tgt = edge.target_id
        if src in id_set and tgt in id_set:
            src_comm = membership[id_to_idx[src]]
            tgt_comm = membership[id_to_idx[tgt]]
            if src_comm == tgt_comm:
                internal_edge_counts[src_comm] += 1

    # ------------------------------------------------------------------
    # 7. Build result dicts with sequential IDs
    # ------------------------------------------------------------------
    communities: list[dict] = []
    for new_idx, comm_idx in enumerate(sorted(community_members)):
        members = community_members[comm_idx]
        communities.append(_build_community_dict(
            community_idx=new_idx,
            member_ids=members,
            organism=organism,
            internal_edges=internal_edge_counts.get(comm_idx, 0),
        ))

    return communities


def _merge_small_communities(
    membership: list[int],
    structural_ids: list[str],
    graph,  # igraph.Graph
    min_size: int,
) -> list[int]:
    """Merge communities smaller than min_size into their nearest neighbor.

    For each small community, find the large community that shares the
    most edges with it and merge into that one. If a small community has
    no edges to any large community, merge it into the largest community.
    """
    # Count community sizes
    comm_sizes: Counter[int] = Counter(membership)

    # Identify small and large communities
    small_comms = {c for c, sz in comm_sizes.items() if sz < min_size}
    if not small_comms:
        return membership

    large_comms = {c for c in comm_sizes if c not in small_comms}
    if not large_comms:
        # All communities are small — just return as-is
        return membership

    # For each small community, find the best large community to merge into
    merge_target: dict[int, int] = {}
    for sc in small_comms:
        # Count edges from this small community to each large community
        neighbor_counts: Counter[int] = Counter()
        sc_members = [i for i, c in enumerate(membership) if c == sc]
        for vtx in sc_members:
            for neighbor in graph.neighbors(vtx):
                n_comm = membership[neighbor]
                if n_comm in large_comms:
                    neighbor_counts[n_comm] += 1

        if neighbor_counts:
            merge_target[sc] = neighbor_counts.most_common(1)[0][0]
        else:
            # No edges to any large community — merge into largest
            largest = max(large_comms, key=lambda c: comm_sizes[c])
            merge_target[sc] = largest

    # Apply merges
    result = list(membership)
    for i, comm in enumerate(result):
        if comm in merge_target:
            result[i] = merge_target[comm]

    return result


# ======================================================================
# Helpers
# ======================================================================

def _build_community_dict(
    community_idx: int,
    member_ids: list[str],
    organism: Organism,
    internal_edges: int,
) -> dict:
    """Build a community result dict from member node IDs."""

    # Cohesion = internal_edges / possible_edges
    n = len(member_ids)
    possible = n * (n - 1) // 2 if n >= 2 else 1
    cohesion = min(1.0, internal_edges / possible) if possible > 0 else 0.0

    # Collect member names for naming / keywords
    names: list[str] = []
    for nid in member_ids:
        node = organism.nodes.get(nid)
        if node:
            names.append(node.name)

    keywords = _extract_keywords(names)
    name = _generate_community_name(names, community_idx)

    return {
        "id": f"community_{community_idx}",
        "name": name,
        "members": member_ids,
        "cohesion": cohesion,
        "keywords": keywords,
    }


def _extract_keywords(names: list[str], max_keywords: int = 5) -> list[str]:
    """Extract representative keywords from member names.

    Splits camelCase and snake_case names into tokens, counts
    frequency, and returns the top tokens.
    """
    import re

    token_counts: Counter[str] = Counter()
    for name in names:
        # Split snake_case
        parts = name.split("_")
        for part in parts:
            # Split camelCase
            sub_parts = re.findall(r"[A-Z]?[a-z]+|[A-Z]+(?=[A-Z]|$)", part)
            if sub_parts:
                for sp in sub_parts:
                    token = sp.lower()
                    if len(token) > 1:  # skip single-char tokens
                        token_counts[token] += 1
            elif len(part) > 1:
                token_counts[part.lower()] += 1

    # Filter out very common / generic tokens
    generic = {"self", "init", "get", "set", "the", "and", "for", "def", "class"}
    for g in generic:
        token_counts.pop(g, None)

    return [tok for tok, _ in token_counts.most_common(max_keywords)]


def _generate_community_name(names: list[str], idx: int) -> str:
    """Generate a descriptive name for a community.

    Uses the most distinctive member name as the basis, falling back
    to a numeric identifier.
    """
    if not names:
        return f"Community {idx}"

    # Prefer class or module names (tend to be more descriptive)
    # Filter out dunder names
    candidates = [n for n in names if not n.startswith("__")]
    if not candidates:
        candidates = names

    # Pick the longest name as most descriptive
    candidates.sort(key=len, reverse=True)
    base = candidates[0]

    if len(names) == 1:
        return base
    return f"{base} group"
