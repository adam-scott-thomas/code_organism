"""
CODE ORGANISM: COMMUNITY DETECTION

Detects functional communities within the code organism using
Leiden community detection (via igraph). Communities represent
clusters of tightly-coupled code that form logical subsystems.
"""

from __future__ import annotations

from collections import Counter
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


def detect_communities(
    organism: Organism,
    resolution: float = 1.0,
) -> list[dict]:
    """Detect functional communities in the code organism.

    Uses the Leiden algorithm (modularity objective) on a graph built
    from call, import, and reference edges between structural nodes.

    Args:
        organism: The organism to analyze.
        resolution: Leiden resolution parameter. Higher values produce
            more, smaller communities.

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

    edge_list: list[tuple[int, int]] = []
    for edge in organism.edges.values():
        if edge.edge_type not in ("call", "import", "reference"):
            continue
        src = edge.source_id
        tgt = edge.target_id
        if src in id_set and tgt in id_set:
            edge_list.append((id_to_idx[src], id_to_idx[tgt]))

    g = igraph.Graph(n=len(structural_ids), edges=edge_list, directed=True)

    # Leiden works on undirected graphs for modularity
    g_undirected = g.as_undirected(mode="collapse")

    # ------------------------------------------------------------------
    # 3. Run Leiden community detection
    # ------------------------------------------------------------------
    partition = g_undirected.community_leiden(
        objective_function="modularity",
        resolution=resolution,
        n_iterations=2,
    )

    # ------------------------------------------------------------------
    # 4. Build result dicts
    # ------------------------------------------------------------------
    # Group members by community index
    community_members: dict[int, list[str]] = {}
    for vtx_idx, comm_idx in enumerate(partition.membership):
        community_members.setdefault(comm_idx, []).append(structural_ids[vtx_idx])

    # Count internal edges per community
    internal_edge_counts: dict[int, int] = Counter()
    for edge in organism.edges.values():
        if edge.edge_type not in ("call", "import", "reference"):
            continue
        src = edge.source_id
        tgt = edge.target_id
        if src in id_set and tgt in id_set:
            src_comm = partition.membership[id_to_idx[src]]
            tgt_comm = partition.membership[id_to_idx[tgt]]
            if src_comm == tgt_comm:
                internal_edge_counts[src_comm] += 1

    communities: list[dict] = []
    for comm_idx in sorted(community_members):
        members = community_members[comm_idx]
        communities.append(_build_community_dict(
            community_idx=comm_idx,
            member_ids=members,
            organism=organism,
            internal_edges=internal_edge_counts.get(comm_idx, 0),
        ))

    return communities


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
