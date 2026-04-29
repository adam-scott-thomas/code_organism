# SPDX-License-Identifier: Apache-2.0
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

# Stop words filtered out during keyword / label extraction
_STOP_WORDS = frozenset({
    # Articles / prepositions / conjunctions
    "the", "a", "an", "of", "to", "for", "in", "on", "at", "by",
    "and", "or", "not", "with", "from", "into",
    # Python keywords / builtins that appear as name fragments
    "def", "class", "self", "cls", "args", "kwargs", "none", "true", "false",
    "type", "str", "int", "list", "dict", "bool", "float", "any", "all",
    # Very common verb prefixes in code names
    "test", "tests", "get", "set", "is", "has", "are", "was", "do", "does",
    "init", "main", "return", "returns", "run", "runs", "add", "del", "pop",
    "put", "try", "end", "use", "call", "finds", "find", "make", "takes",
    # Generic nouns that don't add meaning
    "result", "results", "data", "value", "values", "item", "items",
    "node", "nodes", "new", "old", "obj", "func", "attr", "var", "param",
    "key", "val", "tmp", "temp", "err", "error", "num", "idx", "max", "min",
    "len", "map", "name", "file", "path", "info", "config", "option",
    "input", "output", "arg", "ret", "res", "src", "dst", "buf",
    # Test-specific terms
    "empty", "valid", "invalid", "should", "when", "then", "given",
    "mock", "stub", "fake", "fixture", "assert", "expect", "check",
    "default", "post", "pre",
})


def _split_name(name: str) -> list[str]:
    """Split camelCase and snake_case names into individual terms.

    Examples:
        "parseAST"     -> ["parse", "AST"]
        "snake_case"   -> ["snake", "case"]
        "FileProcessor" -> ["File", "Processor"]
    """
    import re
    # Insert space before uppercase runs: camelCase -> camel Case
    spaced = re.sub(r'([a-z])([A-Z])', r'\1 \2', name)
    # Also split runs of uppercase before a lowercase: XMLParser -> XML Parser
    spaced = re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1 \2', spaced)
    # Split on underscore and space
    return [t for t in re.split(r'[_\s]+', spaced) if t]


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

    # Collect member nodes for naming / keywords
    member_nodes: list = []
    for nid in member_ids:
        node = organism.nodes.get(nid)
        if node:
            member_nodes.append(node)

    keywords = _extract_keywords(member_nodes)
    name = _generate_community_name(member_nodes, community_idx)

    return {
        "id": f"community_{community_idx}",
        "name": name,
        "members": member_ids,
        "cohesion": cohesion,
        "keywords": keywords,
    }


def _extract_keywords(nodes: list, max_keywords: int = 5) -> list[str]:
    """Extract representative keywords from community member nodes.

    Splits camelCase and snake_case names into tokens, counts
    frequency across all members, filters stop words, and returns
    the top tokens.
    """
    token_counts: Counter[str] = Counter()
    for node in nodes:
        terms = _split_name(node.name)
        for t in terms:
            tok = t.lower()
            if len(tok) > 1 and tok not in _STOP_WORDS:
                token_counts[tok] += 1

    return [tok for tok, _ in token_counts.most_common(max_keywords)]


def _common_path_label(nodes: list) -> str | None:
    """Try to derive a community label from shared file paths.

    If all (or most) members share a common module/directory prefix
    in their qualified_name, return a human-readable title from it.
    Returns None if no useful commonality is found.
    """
    # Gather qualified-name path prefixes (everything before the last component)
    # e.g. "analysis.communities.detect_communities" -> "analysis.communities"
    path_parts_list: list[list[str]] = []
    for node in nodes:
        if not node.qualified_name:
            continue
        parts = node.qualified_name.split(".")
        if len(parts) >= 2:
            # Use all parts except the last (the symbol itself)
            path_parts_list.append(parts[:-1])

    if not path_parts_list:
        return None

    # Find common prefix across all paths
    if len(path_parts_list) == 1:
        common = path_parts_list[0]
    else:
        common = list(path_parts_list[0])
        for parts in path_parts_list[1:]:
            new_common = []
            for a, b in zip(common, parts, strict=False):
                if a == b:
                    new_common.append(a)
                else:
                    break
            common = new_common

    if not common:
        # No shared prefix across all members. Check if a majority share one.
        # Count the first path component frequency.
        first_component: Counter[str] = Counter()
        for parts in path_parts_list:
            first_component[parts[0]] += 1
        most_common_dir, count = first_component.most_common(1)[0]
        if count >= len(nodes) * 0.5:
            common = [most_common_dir]
        else:
            return None

    # Convert path components to a readable label
    # e.g. ["analysis", "communities"] -> "Analysis Communities"
    # But skip very generic single-char or short components
    label_parts = []
    for part in common:
        # Expand underscores and camelCase
        terms = _split_name(part)
        for t in terms:
            if t.lower() not in _STOP_WORDS and len(t) > 1:
                label_parts.append(t.title())

    if not label_parts:
        return None

    # Cap at 3 words
    label = " ".join(label_parts[:3])
    return label if label else None


def _common_terms_label(nodes: list) -> str | None:
    """Try to derive a community label from common terms in member names.

    Splits all member names, counts term frequency, and picks terms
    that appear in >30% of members. Returns a 2-3 word title or None.
    """
    if not nodes:
        return None

    all_terms: list[str] = []
    # Track which terms appear in each node (for threshold calculation)
    node_term_sets: list[set[str]] = []

    for node in nodes:
        terms = _split_name(node.name)
        node_terms: set[str] = set()
        for t in terms:
            tok = t.lower()
            if len(tok) > 2 and tok not in _STOP_WORDS:
                all_terms.append(tok)
                node_terms.add(tok)
        node_term_sets.append(node_terms)

    if not all_terms:
        return None

    # Count how many nodes each term appears in
    term_node_count: Counter[str] = Counter()
    for term_set in node_term_sets:
        for t in term_set:
            term_node_count[t] += 1

    # Threshold: term must appear in at least 30% of members (min 2)
    threshold = max(2, int(len(nodes) * 0.3))
    common = [
        term for term, count in term_node_count.most_common(5)
        if count >= threshold
    ]

    if common:
        return " ".join(t.title() for t in common[:3])

    return None


def _generate_community_name(nodes: list, idx: int) -> str:
    """Generate a concise, descriptive name for a community.

    Naming strategy (in priority order):
      1. File-path commonality — if members share a module/directory,
         use that (e.g. "Parser", "Health Analysis").
      2. Common term extraction — frequent meaningful terms across
         member names (e.g. "Validate Format").
      3. Single-node shortcut — if the community is a lone class or
         module, use its name directly.
      4. Fallback — "Group N".
    """
    if not nodes:
        return f"Group {idx}"

    # Strategy 1: File-path based naming
    label = _common_path_label(nodes)
    if label:
        return label

    # Strategy 2: Common terms from member names
    label = _common_terms_label(nodes)
    if label:
        return label

    # Strategy 3: If there's exactly one node, use its name
    if len(nodes) == 1:
        return nodes[0].name

    # Strategy 3b: If there's a single class or module, prefer its name
    from ..model.nodes import NodeType as _NT
    classes = [n for n in nodes if n.node_type == _NT.CLASS]
    modules = [n for n in nodes if n.node_type == _NT.MODULE]
    if len(classes) == 1:
        return classes[0].name
    if len(modules) == 1:
        terms = _split_name(modules[0].name)
        readable = [t.title() for t in terms if t.lower() not in _STOP_WORDS and len(t) > 1]
        if readable:
            return " ".join(readable[:3])

    # Strategy 4: Fallback
    return f"Group {idx}"
