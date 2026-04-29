"""Tests for model/clustering.py — Louvain + module-based hierarchical clustering."""

from __future__ import annotations

import pytest

from Code_Organism.model.clustering import (
    ClusterEdge,
    ClusterNode,
    HierarchicalClusterer,
)
from Code_Organism.model.nodes import (
    Edge,
    HealthStatus,
    NodeType,
    OrganismNode,
    Position,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _node(
    nid: str,
    name: str,
    node_type: NodeType = NodeType.FUNCTION,
    file: str = "src/mod.py",
    health: HealthStatus = HealthStatus.HEALTHY,
    line: int = 1,
) -> OrganismNode:
    n = OrganismNode(
        id=nid,
        name=name,
        node_type=node_type,
        qualified_name=name,
        position=Position(file=file, line=line, column=0),
    )
    n.health = health
    return n


def _edge(eid: str, source: str, target: str, etype: str = "call") -> Edge:
    return Edge(id=eid, source_id=source, target_id=target, edge_type=etype)


# ---------------------------------------------------------------------------
# ClusterNode
# ---------------------------------------------------------------------------


def test_cluster_node_health_score_empty():
    c = ClusterNode(id="c1", name="C", level=0)
    assert c.health_score == 100.0


def test_cluster_node_health_score_partial():
    c = ClusterNode(
        id="c1", name="C", level=0,
        total_nodes=10, healthy_count=7,
    )
    assert c.health_score == 70.0


def test_cluster_node_dominant_health_picks_max():
    c = ClusterNode(
        id="c1", name="C", level=0,
        healthy_count=2, stressed_count=5, inflamed_count=1,
    )
    assert c.dominant_health == "stressed"


def test_cluster_node_dominant_health_all_zero_returns_a_status():
    c = ClusterNode(id="c1", name="C", level=0)
    # max() returns one of the keys when all values equal — anything is fine
    assert c.dominant_health in (
        "healthy", "stressed", "inflamed", "necrotic", "cancerous",
    )


def test_cluster_node_to_dict_shape():
    c = ClusterNode(
        id="c1", name="alpha", level=2,
        child_ids=["a", "b"], child_count=2,
        total_nodes=2, healthy_count=2,
    )
    d = c.to_dict()
    assert d["id"] == "c1"
    assert d["name"] == "alpha"
    assert d["type"] == "cluster"
    assert d["level"] == 2
    assert d["child_count"] == 2
    assert d["expandable"] is True
    assert d["health"] == "healthy"
    assert d["color"] == [0.5, 0.5, 0.8]  # default


def test_cluster_node_to_dict_not_expandable_when_empty():
    c = ClusterNode(id="c1", name="empty", level=0, child_count=0)
    assert c.to_dict()["expandable"] is False


# ---------------------------------------------------------------------------
# ClusterEdge
# ---------------------------------------------------------------------------


def test_cluster_edge_to_dict_with_edge_types():
    e = ClusterEdge(
        id="e1", source_id="a", target_id="b", weight=3.0,
        edge_types={"call": 2, "import": 1},
    )
    d = e.to_dict()
    assert d["source"] == "a"
    assert d["target"] == "b"
    assert d["weight"] == 3.0
    assert d["type"] == "call"  # most-common type wins


def test_cluster_edge_to_dict_empty_types_defaults_to_call():
    e = ClusterEdge(id="e1", source_id="a", target_id="b")
    assert e.to_dict()["type"] == "call"


# ---------------------------------------------------------------------------
# HierarchicalClusterer construction + adjacency
# ---------------------------------------------------------------------------


@pytest.fixture
def small_graph():
    """Three nodes: a-b, b-c, a-c — tightly connected triangle."""
    nodes = {
        "a": _node("a", "alpha", file="pkgA/x.py"),
        "b": _node("b", "beta",  file="pkgA/y.py"),
        "c": _node("c", "gamma", file="pkgB/z.py"),
    }
    edges = {
        "ab": _edge("ab", "a", "b"),
        "bc": _edge("bc", "b", "c"),
        "ac": _edge("ac", "a", "c"),
    }
    return nodes, edges


def test_clusterer_init_builds_adjacency(small_graph):
    nodes, edges = small_graph
    h = HierarchicalClusterer(nodes, edges)
    assert h.adjacency["a"] == {"b", "c"}
    assert h.adjacency["b"] == {"a", "c"}
    assert h.adjacency["c"] == {"a", "b"}


def test_clusterer_init_records_edge_lookup_both_directions(small_graph):
    nodes, edges = small_graph
    h = HierarchicalClusterer(nodes, edges)
    assert ("a", "b") in h.edge_lookup
    assert ("b", "a") in h.edge_lookup


# ---------------------------------------------------------------------------
# _cluster_by_module
# ---------------------------------------------------------------------------


def test_cluster_by_module_groups_by_top_directory(small_graph):
    nodes, edges = small_graph
    h = HierarchicalClusterer(nodes, edges)
    clusters = h._cluster_by_module()
    # Two top-level directories: pkgA, pkgB
    names = sorted(c.name for c in clusters.values())
    assert "pkgA" in names
    assert "pkgB" in names


def test_cluster_by_module_aggregates_nodes_per_module(small_graph):
    nodes, edges = small_graph
    h = HierarchicalClusterer(nodes, edges)
    clusters = h._cluster_by_module()
    pkga = next(c for c in clusters.values() if c.name == "pkgA")
    assert pkga.total_nodes == 2  # a + b


# ---------------------------------------------------------------------------
# _aggregate_stats — level 0 (children are real nodes)
# ---------------------------------------------------------------------------


def test_aggregate_stats_level0_counts_health():
    nodes = {
        "h1": _node("h1", "f1", health=HealthStatus.HEALTHY),
        "h2": _node("h2", "f2", health=HealthStatus.STRESSED),
        "h3": _node("h3", "f3", health=HealthStatus.INFLAMED),
        "h4": _node("h4", "f4", health=HealthStatus.NECROTIC),
        "h5": _node("h5", "f5", health=HealthStatus.CANCEROUS),
    }
    h = HierarchicalClusterer(nodes, {})
    cluster = ClusterNode(id="c", name="x", level=0)
    h._aggregate_stats(cluster, list(nodes.keys()), 0)
    assert cluster.total_nodes == 5
    assert cluster.healthy_count == 1
    assert cluster.stressed_count == 1
    assert cluster.inflamed_count == 1
    assert cluster.necrotic_count == 1
    assert cluster.cancerous_count == 1


def test_aggregate_stats_level0_counts_function_and_class():
    nodes = {
        "fn": _node("fn", "f", node_type=NodeType.FUNCTION),
        "cl": _node("cl", "C", node_type=NodeType.CLASS),
    }
    h = HierarchicalClusterer(nodes, {})
    cluster = ClusterNode(id="c", name="x", level=0)
    h._aggregate_stats(cluster, ["fn", "cl"], 0)
    assert cluster.total_functions == 1
    assert cluster.total_classes == 1


def test_aggregate_stats_level0_skips_unknown_ids():
    nodes = {"a": _node("a", "f")}
    h = HierarchicalClusterer(nodes, {})
    cluster = ClusterNode(id="c", name="x", level=0)
    h._aggregate_stats(cluster, ["a", "missing"], 0)
    assert cluster.total_nodes == 1


# ---------------------------------------------------------------------------
# _aggregate_stats — level > 0 (children are clusters)
# ---------------------------------------------------------------------------


def test_aggregate_stats_higher_level_sums_child_clusters():
    h = HierarchicalClusterer({}, {})
    child = ClusterNode(
        id="c0", name="leaf", level=0,
        total_nodes=4, total_lines=100,
        total_functions=2, total_classes=1,
        healthy_count=3, stressed_count=1,
    )
    h.levels.append({"c0": child})

    parent = ClusterNode(id="p", name="root", level=1)
    h._aggregate_stats(parent, ["c0"], 1)
    assert parent.total_nodes == 4
    assert parent.total_lines == 100
    assert parent.total_functions == 2
    assert parent.total_classes == 1
    assert parent.healthy_count == 3
    assert parent.stressed_count == 1


# ---------------------------------------------------------------------------
# _louvain_partition + _modularity_gain
# ---------------------------------------------------------------------------


def test_louvain_partition_returns_partition_for_each_node(small_graph):
    nodes, edges = small_graph
    h = HierarchicalClusterer(nodes, edges)
    partition = h._louvain_partition({"a", "b", "c"}, h.adjacency)
    assert set(partition.keys()) == {"a", "b", "c"}
    assert all(isinstance(v, int) for v in partition.values())


def test_louvain_partition_returns_initial_when_no_edges():
    nodes = {"a": _node("a", "x"), "b": _node("b", "y")}
    h = HierarchicalClusterer(nodes, {})
    # No edges → m == 0 path returns initial assignment
    partition = h._louvain_partition({"a", "b"}, h.adjacency)
    assert set(partition.keys()) == {"a", "b"}


def test_modularity_gain_zero_when_no_edges_in_graph():
    h = HierarchicalClusterer({}, {})
    gain = h._modularity_gain(
        node="a", from_comm=0, to_comm=1,
        community_to_nodes={0: {"a"}, 1: {"b"}},
        adjacency={},
        k={"a": 0, "b": 0},
        m=0.0,
        nodes={"a", "b"},
    )
    assert gain == 0


# ---------------------------------------------------------------------------
# _create_clusters_from_partition
# ---------------------------------------------------------------------------


def test_create_clusters_from_partition_groups_by_community(small_graph):
    nodes, edges = small_graph
    h = HierarchicalClusterer(nodes, edges)
    # Partition is over real node IDs, so this is a level-0 grouping
    partition = {"a": 0, "b": 0, "c": 1}
    clusters = h._create_clusters_from_partition(partition, level=0)
    assert len(clusters) == 2
    sizes = sorted(c.child_count for c in clusters.values())
    assert sizes == [1, 2]


# ---------------------------------------------------------------------------
# _build_cluster_adjacency
# ---------------------------------------------------------------------------


def test_build_cluster_adjacency_links_clusters_via_member_edges(small_graph):
    nodes, edges = small_graph
    h = HierarchicalClusterer(nodes, edges)
    partition = {"a": 0, "b": 0, "c": 1}
    clusters = h._create_clusters_from_partition(partition, level=0)
    adj = h._build_cluster_adjacency(clusters, partition, h.adjacency)
    # The two clusters share the edges b-c and a-c — they must be adjacent
    cluster_ids = list(clusters.keys())
    assert any(other in adj[cid] for cid in cluster_ids for other in cluster_ids if other != cid)


# ---------------------------------------------------------------------------
# _contract_adjacency
# ---------------------------------------------------------------------------


def test_contract_adjacency_collapses_communities():
    h = HierarchicalClusterer({}, {})
    partition = {"a": 0, "b": 0, "c": 1, "d": 1}
    adjacency = {
        "a": {"b", "c"},
        "b": {"a", "d"},
        "c": {"a", "d"},
        "d": {"b", "c"},
    }
    contracted = h._contract_adjacency(partition, adjacency)
    # Two communities → two contracted nodes, each adjacent to the other
    assert len(contracted) == 2


# ---------------------------------------------------------------------------
# _determine_cluster_name
# ---------------------------------------------------------------------------


def test_determine_cluster_name_single_member_returns_its_name():
    nodes = {"a": _node("a", "alpha")}
    h = HierarchicalClusterer(nodes, {})
    assert h._determine_cluster_name(["a"], level=0) == "alpha"


def test_determine_cluster_name_common_prefix():
    nodes = {
        "a": _node("a", "service.users"),
        "b": _node("b", "service.orders"),
    }
    h = HierarchicalClusterer(nodes, {})
    name = h._determine_cluster_name(["a", "b"], level=0)
    assert name.startswith("service.")  # common prefix detection


def test_determine_cluster_name_higher_level_uses_count():
    h = HierarchicalClusterer({}, {})
    name = h._determine_cluster_name(["x", "y", "z"], level=2)
    assert name == "Cluster-3"


# ---------------------------------------------------------------------------
# _health_to_color
# ---------------------------------------------------------------------------


def test_health_to_color_known_statuses():
    h = HierarchicalClusterer({}, {})
    assert h._health_to_color("healthy") == (0.4, 0.8, 0.4)
    assert h._health_to_color("cancerous") == (0.8, 0.2, 0.2)


def test_health_to_color_unknown_falls_back_to_default():
    h = HierarchicalClusterer({}, {})
    assert h._health_to_color("nonsense") == (0.5, 0.5, 0.8)


# ---------------------------------------------------------------------------
# _generate_id
# ---------------------------------------------------------------------------


def test_generate_id_is_short_hex():
    h = HierarchicalClusterer({}, {})
    out = h._generate_id("test")
    assert len(out) == 16
    assert all(c in "0123456789abcdef" for c in out)


# ---------------------------------------------------------------------------
# get_level / get_top_level / get_children
# ---------------------------------------------------------------------------


def test_get_level_returns_empty_for_out_of_range():
    h = HierarchicalClusterer({}, {})
    assert h.get_level(0) == {}
    assert h.get_level(99) == {}


def test_get_top_level_returns_empty_when_no_levels():
    h = HierarchicalClusterer({}, {})
    assert h.get_top_level() == {}


def test_get_children_returns_empty_for_unknown_cluster():
    h = HierarchicalClusterer({}, {})
    assert h.get_children("nope") == []


# ---------------------------------------------------------------------------
# compute_hierarchy — end-to-end smoke
# ---------------------------------------------------------------------------


def test_compute_hierarchy_smoke(small_graph):
    nodes, edges = small_graph
    h = HierarchicalClusterer(nodes, edges)
    n_levels = h.compute_hierarchy(target_top_level_count=1)
    assert n_levels >= 1
    assert h.get_top_level()  # not empty
    assert len(h.cluster_children) >= len(h.levels[0])
