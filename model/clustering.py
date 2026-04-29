# SPDX-License-Identifier: Apache-2.0
"""
CODE ORGANISM: HIERARCHICAL CLUSTERING

Implements community detection for massive codebases (4-5M+ nodes).
Uses Louvain algorithm to group nodes by connectivity patterns,
creating a hierarchical view that can be progressively loaded.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field

from .nodes import Edge, NodeType
from .nodes import OrganismNode as Node


@dataclass
class ClusterNode:
    """
    A cluster representing a group of related code nodes.

    Clusters form a hierarchy:
    - Level 0: ~50-100 super-clusters (major subsystems)
    - Level 1: ~1,000-5,000 clusters (modules/packages)
    - Level 2: ~50,000 clusters (classes + key functions)
    - Level 3+: Individual nodes
    """
    id: str
    name: str
    level: int
    child_ids: list[str] = field(default_factory=list)
    child_count: int = 0

    # Aggregate statistics
    total_nodes: int = 0
    total_lines: int = 0
    total_functions: int = 0
    total_classes: int = 0

    # Health aggregates
    healthy_count: int = 0
    stressed_count: int = 0
    inflamed_count: int = 0
    necrotic_count: int = 0
    cancerous_count: int = 0

    # Visual properties
    size: float = 1.0
    color: tuple[float, float, float] = (0.5, 0.5, 0.8)

    # Position (set by layout engine)
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0

    @property
    def health_score(self) -> float:
        """Overall health as percentage (0-100)."""
        if self.total_nodes == 0:
            return 100.0
        return (self.healthy_count / self.total_nodes) * 100

    @property
    def dominant_health(self) -> str:
        """Most common health status in cluster."""
        counts = {
            'healthy': self.healthy_count,
            'stressed': self.stressed_count,
            'inflamed': self.inflamed_count,
            'necrotic': self.necrotic_count,
            'cancerous': self.cancerous_count,
        }
        return max(counts, key=lambda k: counts[k])

    def to_dict(self) -> dict:
        """Serialize for JSON transmission."""
        return {
            'id': self.id,
            'name': self.name,
            'type': 'cluster',
            'level': self.level,
            'child_count': self.child_count,
            'total_nodes': self.total_nodes,
            'total_lines': self.total_lines,
            'total_functions': self.total_functions,
            'total_classes': self.total_classes,
            'health': self.dominant_health,
            'health_score': self.health_score,
            'size': self.size,
            'color': list(self.color),
            'x': self.x,
            'y': self.y,
            'z': self.z,
            'expandable': self.child_count > 0,
        }


@dataclass
class ClusterEdge:
    """Edge between clusters, representing aggregated connections."""
    id: str
    source_id: str
    target_id: str
    weight: float = 1.0  # Number of underlying edges
    edge_types: dict[str, int] = field(default_factory=dict)  # Type counts

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'source': self.source_id,
            'target': self.target_id,
            'weight': self.weight,
            'type': max(self.edge_types, key=lambda k: self.edge_types[k]) if self.edge_types else 'call',
        }


class HierarchicalClusterer:
    """
    Builds a hierarchical clustering of code nodes using community detection.

    Uses the Louvain algorithm to find densely connected communities,
    then recursively applies it to create multiple levels of abstraction.
    """

    def __init__(self, nodes: dict[str, Node], edges: dict[str, Edge]):
        self.nodes = nodes
        self.edges = edges

        # Build adjacency structure
        self.adjacency: dict[str, set[str]] = defaultdict(set)
        self.edge_lookup: dict[tuple[str, str], Edge] = {}

        for edge in edges.values():
            self.adjacency[edge.source_id].add(edge.target_id)
            self.adjacency[edge.target_id].add(edge.source_id)
            self.edge_lookup[(edge.source_id, edge.target_id)] = edge
            self.edge_lookup[(edge.target_id, edge.source_id)] = edge

        # Clustering results
        self.levels: list[dict[str, ClusterNode]] = []
        self.node_to_cluster: dict[int, dict[str, str]] = {}  # level -> node_id -> cluster_id
        self.cluster_children: dict[str, list[str]] = {}  # cluster_id -> child_ids

    def compute_hierarchy(self, target_top_level_count: int = 100, resolution: float = 1.0) -> int:
        """
        Build hierarchical clustering until reaching target top-level count.

        Uses module/file structure first, then Louvain for finer clustering.

        Args:
            target_top_level_count: Desired number of clusters at top level
            resolution: Higher values create more, smaller clusters (default 1.0)

        Returns:
            Number of levels created
        """
        # First level: cluster by module/file path
        module_clusters = self._cluster_by_module()
        if module_clusters:
            self.levels.append(module_clusters)
            for cluster_id, cluster in module_clusters.items():
                self.cluster_children[cluster_id] = cluster.child_ids
                for child_id in cluster.child_ids:
                    if 0 not in self.node_to_cluster:
                        self.node_to_cluster[0] = {}
                    self.node_to_cluster[0][child_id] = cluster_id

        # If still too many clusters, apply Louvain to reduce
        current_nodes = set(module_clusters.keys()) if module_clusters else set(self.nodes.keys())
        current_adjacency = self._build_cluster_adjacency(
            module_clusters,
            {n: i for i, n in enumerate(self.nodes.keys())},  # dummy partition
            self.adjacency
        ) if module_clusters else self.adjacency.copy()

        level = 1 if module_clusters else 0

        while len(current_nodes) > target_top_level_count and level < 10:
            # Run Louvain with low resolution to create fewer, larger clusters
            partition = self._louvain_partition(current_nodes, current_adjacency, 0.5)

            num_communities = len(set(partition.values()))
            if num_communities >= len(current_nodes) * 0.9:
                break  # Can't reduce further

            clusters = self._create_clusters_from_partition(partition, level)
            self.levels.append(clusters)

            for cluster_id, cluster in clusters.items():
                self.cluster_children[cluster_id] = cluster.child_ids
                for child_id in cluster.child_ids:
                    if level not in self.node_to_cluster:
                        self.node_to_cluster[level] = {}
                    self.node_to_cluster[level][child_id] = cluster_id

            current_nodes = set(clusters.keys())
            current_adjacency = self._build_cluster_adjacency(clusters, partition, current_adjacency)
            level += 1

        # Create root if needed
        if len(current_nodes) > 1:
            final = ClusterNode(
                id=self._generate_id('root'),
                name='Root',
                level=level,
                child_ids=list(current_nodes),
                child_count=len(current_nodes),
            )
            self._aggregate_stats(final, current_nodes, level - 1)
            self.levels.append({'root': final})
            self.cluster_children['root'] = list(current_nodes)

        return len(self.levels)

    def _cluster_by_module(self) -> dict[str, ClusterNode]:
        """Create initial clusters based on file/directory structure."""
        # Group nodes by their source file directory
        module_to_nodes: dict[str, list[str]] = defaultdict(list)

        for node_id, node in self.nodes.items():
            # Extract directory from position (file path)
            position = getattr(node, 'position', None)
            if position:
                # Position format: "path/to/file.py:line:col"
                pos_str = str(position)
                file_path = pos_str.split(':')[0] if ':' in pos_str else pos_str

                # Get directory name (first level)
                parts = file_path.replace('\\', '/').split('/')
                # Use the first directory/file as the module
                if len(parts) >= 2:
                    module = parts[0]  # Top-level directory
                else:
                    module = parts[0].replace('.py', '') if parts else 'unknown'
            else:
                # Fallback to qualified name
                module = node.name.split('.')[0]

            module_to_nodes[module].append(node_id)

        # Create cluster for each module
        clusters = {}
        for i, (module, node_ids) in enumerate(module_to_nodes.items()):
            cluster_id = self._generate_id(f'mod_{i}')
            cluster = ClusterNode(
                id=cluster_id,
                name=module,
                level=0,
                child_ids=node_ids,
                child_count=len(node_ids),
            )
            self._aggregate_stats(cluster, node_ids, 0)

            import math
            cluster.size = 1.0 + math.log10(max(1, cluster.total_nodes)) * 0.5
            cluster.color = self._health_to_color(cluster.dominant_health)

            clusters[cluster_id] = cluster

        return clusters

    def _louvain_partition(
        self,
        nodes: set[str],
        adjacency: dict[str, set[str]],
        resolution: float = 1.0
    ) -> dict[str, int]:
        """
        Louvain community detection algorithm.

        Args:
            nodes: Set of node IDs to partition
            adjacency: Adjacency structure
            resolution: Higher values create more, smaller communities

        Returns mapping of node_id -> community_id.
        """
        # Initialize: each node in its own community
        node_list = list(nodes)
        node_to_community = {n: i for i, n in enumerate(node_list)}
        community_to_nodes: dict[int, set[str]] = {i: {n} for i, n in enumerate(node_list)}

        # Compute initial modularity components
        m = sum(len(adj) for adj in adjacency.values()) / 2  # Total edges
        if m == 0:
            return node_to_community

        k = {n: len(adjacency.get(n, set()) & nodes) for n in nodes}  # Degree within subgraph

        improved = True
        iterations = 0
        max_iterations = 20

        while improved and iterations < max_iterations:
            improved = False
            iterations += 1

            for node in node_list:
                current_comm = node_to_community[node]

                # Find neighboring communities
                neighbor_comms = set()
                for neighbor in adjacency.get(node, set()):
                    if neighbor in node_to_community:
                        neighbor_comms.add(node_to_community[neighbor])

                if not neighbor_comms:
                    continue

                # Calculate modularity gain for moving to each neighbor community
                best_comm = current_comm
                best_gain: float = 0.0

                for target_comm in neighbor_comms:
                    if target_comm == current_comm:
                        continue

                    gain = self._modularity_gain(
                        node, current_comm, target_comm,
                        community_to_nodes, adjacency, k, m, nodes, resolution
                    )

                    if gain > best_gain:
                        best_gain = gain
                        best_comm = target_comm

                # Move node if there's improvement
                if best_comm != current_comm:
                    community_to_nodes[current_comm].discard(node)
                    community_to_nodes[best_comm].add(node)
                    node_to_community[node] = best_comm
                    improved = True

        # Renumber communities to be contiguous
        unique_comms = sorted(set(node_to_community.values()))
        comm_remap = {old: new for new, old in enumerate(unique_comms)}
        return {n: comm_remap[c] for n, c in node_to_community.items()}

    def _modularity_gain(
        self,
        node: str,
        from_comm: int,
        to_comm: int,
        community_to_nodes: dict[int, set[str]],
        adjacency: dict[str, set[str]],
        k: dict[str, int],
        m: float,
        nodes: set[str],
        resolution: float = 1.0
    ) -> float:
        """Calculate modularity gain from moving node between communities.

        Resolution parameter: higher values penalize large communities,
        creating more, smaller clusters.
        """
        if m == 0:
            return 0

        # Edges from node to target community
        ki_in = sum(1 for n in community_to_nodes[to_comm]
                   if n in adjacency.get(node, set()))

        # Edges from node to source community (excluding self)
        ki_out = sum(1 for n in community_to_nodes[from_comm]
                    if n != node and n in adjacency.get(node, set()))

        # Sum of degrees in target community
        sigma_tot = sum(k.get(n, 0) for n in community_to_nodes[to_comm])

        # Sum of degrees in source community (excluding node)
        sigma_from = sum(k.get(n, 0) for n in community_to_nodes[from_comm] if n != node)

        ki = k.get(node, 0)

        # Modularity gain formula with resolution parameter
        # Higher resolution increases penalty for large communities
        gain = (ki_in - ki_out) / m - resolution * ki * (sigma_tot - sigma_from) / (2 * m * m)
        return gain

    def _create_clusters_from_partition(
        self,
        partition: dict[str, int],
        level: int
    ) -> dict[str, ClusterNode]:
        """Create ClusterNode objects from a partition."""
        # Group nodes by community
        communities: dict[int, list[str]] = defaultdict(list)
        for node_id, comm_id in partition.items():
            communities[comm_id].append(node_id)

        clusters = {}
        for comm_id, member_ids in communities.items():
            cluster_id = self._generate_id(f'c{level}_{comm_id}')

            # Determine cluster name from member names
            name = self._determine_cluster_name(member_ids, level)

            cluster = ClusterNode(
                id=cluster_id,
                name=name,
                level=level,
                child_ids=member_ids,
                child_count=len(member_ids),
            )

            # Aggregate statistics from children
            self._aggregate_stats(cluster, member_ids, level)

            # Set size based on total nodes (log scale)
            import math
            cluster.size = 1.0 + math.log10(max(1, cluster.total_nodes)) * 0.5

            # Set color based on health
            cluster.color = self._health_to_color(cluster.dominant_health)

            clusters[cluster_id] = cluster

        return clusters

    def _aggregate_stats(
        self,
        cluster: ClusterNode,
        child_ids: list[str] | set[str],
        child_level: int
    ) -> None:
        """Aggregate statistics from child nodes/clusters."""
        if child_level == 0:
            # Children are actual nodes
            for node_id in child_ids:
                node = self.nodes.get(node_id)
                if not node:
                    continue

                cluster.total_nodes += 1
                cluster.total_lines += getattr(node, 'lines', 0)

                if node.node_type == NodeType.FUNCTION:
                    cluster.total_functions += 1
                elif node.node_type == NodeType.CLASS:
                    cluster.total_classes += 1

                health = getattr(node, 'health', None)
                if health:
                    health_name = health.value if hasattr(health, 'value') else str(health)
                    if health_name == 'healthy':
                        cluster.healthy_count += 1
                    elif health_name == 'stressed':
                        cluster.stressed_count += 1
                    elif health_name == 'inflamed':
                        cluster.inflamed_count += 1
                    elif health_name == 'necrotic':
                        cluster.necrotic_count += 1
                    elif health_name == 'cancerous':
                        cluster.cancerous_count += 1
                    else:
                        cluster.healthy_count += 1  # Default to healthy
                else:
                    cluster.healthy_count += 1
        else:
            # Children are clusters from previous level
            prev_level = self.levels[child_level - 1] if child_level > 0 else {}
            for child_id in child_ids:
                child = prev_level.get(child_id)
                if not child:
                    continue

                cluster.total_nodes += child.total_nodes
                cluster.total_lines += child.total_lines
                cluster.total_functions += child.total_functions
                cluster.total_classes += child.total_classes
                cluster.healthy_count += child.healthy_count
                cluster.stressed_count += child.stressed_count
                cluster.inflamed_count += child.inflamed_count
                cluster.necrotic_count += child.necrotic_count
                cluster.cancerous_count += child.cancerous_count

    def _build_cluster_adjacency(
        self,
        clusters: dict[str, ClusterNode],
        partition: dict[str, int],
        old_adjacency: dict[str, set[str]]
    ) -> dict[str, set[str]]:
        """Build adjacency structure between clusters based on their member connections."""
        # Map community ID to cluster ID
        comm_to_cluster = {}
        for cluster in clusters.values():
            # Find which community this cluster corresponds to
            if cluster.child_ids:
                first_child = cluster.child_ids[0]
                if first_child in partition:
                    comm_id = partition[first_child]
                    comm_to_cluster[comm_id] = cluster.id

        # Build cluster adjacency
        cluster_adjacency: dict[str, set[str]] = defaultdict(set)

        for node_id, neighbors in old_adjacency.items():
            if node_id not in partition:
                continue
            node_comm = partition[node_id]
            node_cluster = comm_to_cluster.get(node_comm)
            if not node_cluster:
                continue

            for neighbor_id in neighbors:
                if neighbor_id not in partition:
                    continue
                neighbor_comm = partition[neighbor_id]
                neighbor_cluster = comm_to_cluster.get(neighbor_comm)
                if neighbor_cluster and neighbor_cluster != node_cluster:
                    cluster_adjacency[node_cluster].add(neighbor_cluster)

        return cluster_adjacency

    def _contract_adjacency(
        self,
        partition: dict[str, int],
        adjacency: dict[str, set[str]]
    ) -> dict[str, set[str]]:
        """Contract graph by merging nodes in same community."""
        # Map old node IDs to new cluster IDs
        comm_to_id = {}
        for comm in partition.values():
            if comm not in comm_to_id:
                comm_to_id[comm] = self._generate_id(f'contracted_{comm}')

        node_to_new = {n: comm_to_id[c] for n, c in partition.items()}

        # Build contracted adjacency
        new_adjacency: dict[str, set[str]] = defaultdict(set)
        for node, neighbors in adjacency.items():
            if node not in node_to_new:
                continue
            new_node = node_to_new[node]
            for neighbor in neighbors:
                if neighbor not in node_to_new:
                    continue
                new_neighbor = node_to_new[neighbor]
                if new_node != new_neighbor:
                    new_adjacency[new_node].add(new_neighbor)

        return new_adjacency

    def _determine_cluster_name(self, member_ids: list[str], level: int) -> str:
        """Determine a meaningful name for a cluster."""
        if level == 0:
            # Use most common module/package prefix
            names = []
            for node_id in member_ids[:10]:  # Sample first 10
                node = self.nodes.get(node_id)
                if node:
                    names.append(node.name)

            if names:
                # Find common prefix
                if len(names) == 1:
                    return names[0]

                prefix = names[0]
                for name in names[1:]:
                    while prefix and not name.startswith(prefix):
                        prefix = prefix[:-1]

                if prefix and len(prefix) > 3:
                    return f"{prefix}*"

                return names[0].split('.')[0] if '.' in names[0] else names[0][:20]

        return f"Cluster-{len(member_ids)}"

    def _health_to_color(self, health: str) -> tuple[float, float, float]:
        """Convert health status to RGB color."""
        colors = {
            'healthy': (0.4, 0.8, 0.4),    # Green
            'stressed': (0.8, 0.8, 0.2),   # Yellow
            'inflamed': (0.8, 0.5, 0.2),   # Orange
            'necrotic': (0.4, 0.4, 0.4),   # Gray
            'cancerous': (0.8, 0.2, 0.2),  # Red
        }
        return colors.get(health, (0.5, 0.5, 0.8))

    def _generate_id(self, prefix: str) -> str:
        """Generate unique ID."""
        import time
        data = f"{prefix}_{time.time_ns()}"
        return hashlib.md5(data.encode()).hexdigest()[:16]

    def get_level(self, level: int) -> dict[str, ClusterNode]:
        """Get all clusters at a specific level."""
        if level < 0 or level >= len(self.levels):
            return {}
        # Levels are stored bottom-up, so reverse index
        return self.levels[-(level + 1)]

    def get_top_level(self) -> dict[str, ClusterNode]:
        """Get the top-most level (fewest clusters)."""
        if not self.levels:
            return {}
        return self.levels[-1]

    def get_children(self, cluster_id: str) -> list[str]:
        """Get child IDs for a cluster."""
        return self.cluster_children.get(cluster_id, [])

    def get_cluster_edges(self, clusters: dict[str, ClusterNode]) -> list[ClusterEdge]:
        """Get edges between clusters at a level."""
        edges = []
        seen = set()

        for cluster in clusters.values():
            for child_id in cluster.child_ids:
                # Find edges from children to other clusters
                for neighbor_id in self.adjacency.get(child_id, set()):
                    # Find which cluster the neighbor belongs to
                    for other_cluster in clusters.values():
                        if other_cluster.id == cluster.id:
                            continue
                        if neighbor_id in other_cluster.child_ids:
                            edge_key = tuple(sorted([cluster.id, other_cluster.id]))
                            if edge_key not in seen:
                                seen.add(edge_key)
                                edges.append(ClusterEdge(
                                    id=self._generate_id('ce'),
                                    source_id=cluster.id,
                                    target_id=other_cluster.id,
                                    weight=1.0,
                                ))
                            break

        return edges
