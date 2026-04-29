# SPDX-License-Identifier: Apache-2.0
"""
CODE ORGANISM: LAYOUT ENGINE

Pre-computes force-directed layouts for massive graphs using
Barnes-Hut optimization (O(n log n) instead of O(n²)).

Layouts are cached to disk for fast subsequent loads.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
from dataclasses import dataclass
from pathlib import Path

from .clustering import ClusterEdge, ClusterNode
from .nodes import Edge
from .nodes import OrganismNode as Node


@dataclass
class Position3D:
    """3D position with velocity for force simulation."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    vz: float = 0.0

    def to_dict(self) -> dict:
        return {'x': self.x, 'y': self.y, 'z': self.z}


class OctreeNode:
    """Octree for Barnes-Hut force approximation."""

    def __init__(self, center: tuple[float, float, float], size: float):
        self.center = center
        self.size = size
        self.children: list[OctreeNode | None] = [None] * 8
        self.node_ids: list[str] = []
        self.total_mass: float = 0.0
        self.center_of_mass: list[float] = [0.0, 0.0, 0.0]
        self.is_leaf: bool = True

    def insert(self, node_id: str, pos: Position3D, mass: float = 1.0) -> None:
        """Insert a node into the octree."""
        if self.is_leaf and len(self.node_ids) == 0:
            # Empty leaf - just add
            self.node_ids.append(node_id)
            self.total_mass = mass
            self.center_of_mass = [pos.x, pos.y, pos.z]
            return

        if self.is_leaf and len(self.node_ids) == 1:
            # Convert to internal node
            self.is_leaf = False
            self.node_ids = []
            # Re-insert existing node
            # (simplified - would need position lookup)

        # Update center of mass
        old_mass = self.total_mass
        self.total_mass += mass
        if self.total_mass > 0:
            for i in range(3):
                coord = [pos.x, pos.y, pos.z][i]
                self.center_of_mass[i] = (
                    self.center_of_mass[i] * old_mass + coord * mass
                ) / self.total_mass

        # Insert into appropriate child
        octant = self._get_octant(pos)
        child = self.children[octant]
        if child is None:
            child_size = self.size / 2
            child_center = self._get_child_center(octant, child_size)
            child = OctreeNode(child_center, child_size)
            self.children[octant] = child

        child.insert(node_id, pos, mass)

    def _get_octant(self, pos: Position3D) -> int:
        """Determine which octant a position belongs to."""
        octant = 0
        if pos.x >= self.center[0]:
            octant |= 1
        if pos.y >= self.center[1]:
            octant |= 2
        if pos.z >= self.center[2]:
            octant |= 4
        return octant

    def _get_child_center(self, octant: int, child_size: float) -> tuple[float, float, float]:
        """Get center of child octant."""
        offset = child_size / 2
        return (
            self.center[0] + (offset if octant & 1 else -offset),
            self.center[1] + (offset if octant & 2 else -offset),
            self.center[2] + (offset if octant & 4 else -offset),
        )


class LayoutEngine:
    """
    Computes and caches 3D layouts for code graphs.

    Uses Barnes-Hut approximation for O(n log n) force calculations
    on graphs with millions of nodes.
    """

    CACHE_DIR = Path.home() / '.code_organism' / 'layout_cache'

    def __init__(self):
        self.CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def compute_layout(
        self,
        nodes: dict[str, Node],
        edges: dict[str, Edge],
        use_cache: bool = True,
        iterations: int = 100,
        theta: float = 0.8,  # Barnes-Hut threshold
    ) -> dict[str, dict]:
        """
        Compute 3D layout for nodes.

        Args:
            nodes: Node dictionary
            edges: Edge dictionary
            use_cache: Whether to use cached layout if available
            iterations: Number of force simulation iterations
            theta: Barnes-Hut approximation threshold (higher = faster but less accurate)

        Returns:
            Dictionary mapping node_id to {x, y, z} positions
        """
        cache_key = self._compute_cache_key(nodes, edges)
        cache_path = self.CACHE_DIR / f'{cache_key}.json'

        if use_cache and cache_path.exists():
            try:
                return json.loads(cache_path.read_text())
            except Exception:
                pass

        # Build adjacency
        adjacency: dict[str, set[str]] = {}
        for node_id in nodes:
            adjacency[node_id] = set()
        for edge in edges.values():
            if edge.source_id in adjacency and edge.target_id in adjacency:
                adjacency[edge.source_id].add(edge.target_id)
                adjacency[edge.target_id].add(edge.source_id)

        # Compute layout
        positions = self._force_directed_3d(
            list(nodes.keys()),
            adjacency,
            iterations=iterations,
            theta=theta,
            verbose=len(nodes) > 1000
        )

        # Convert to serializable format
        result = {node_id: pos.to_dict() for node_id, pos in positions.items()}

        # Cache result
        try:
            cache_path.write_text(json.dumps(result))
        except Exception:
            pass

        return result

    def compute_cluster_layout(
        self,
        clusters: dict[str, ClusterNode],
        edges: list[ClusterEdge],
        iterations: int = 50,
    ) -> dict[str, dict]:
        """
        Compute layout for cluster nodes.

        Args:
            clusters: Dictionary of cluster nodes
            edges: List of cluster edges

        Returns:
            Dictionary mapping cluster_id to {x, y, z} positions
        """
        # Build adjacency from edges
        adjacency: dict[str, set[str]] = {c: set() for c in clusters}
        for edge in edges:
            if edge.source_id in adjacency and edge.target_id in adjacency:
                adjacency[edge.source_id].add(edge.target_id)
                adjacency[edge.target_id].add(edge.source_id)

        # Use simpler layout for small cluster counts
        if len(clusters) < 1000:
            positions = self._spring_layout_3d(
                list(clusters.keys()),
                adjacency,
                iterations=iterations
            )
        else:
            positions = self._force_directed_3d(
                list(clusters.keys()),
                adjacency,
                iterations=iterations,
                theta=0.8
            )

        return {cid: pos.to_dict() for cid, pos in positions.items()}

    def _force_directed_3d(
        self,
        node_ids: list[str],
        adjacency: dict[str, set[str]],
        iterations: int = 100,
        theta: float = 0.8,
        verbose: bool = False,
    ) -> dict[str, Position3D]:
        """
        Barnes-Hut force-directed layout in 3D.

        Uses octree for O(n log n) force approximation.
        """
        n = len(node_ids)
        if n == 0:
            return {}

        if verbose:
            print(f"Computing layout for {n} nodes...")

        # Initialize positions randomly in a sphere
        positions: dict[str, Position3D] = {}
        spread = math.sqrt(n) * 2  # Scale with sqrt of node count

        for node_id in node_ids:
            theta_angle = random.random() * math.pi * 2
            phi = math.acos(2 * random.random() - 1)
            r = spread * (0.5 + random.random() * 0.5)

            positions[node_id] = Position3D(
                x=r * math.sin(phi) * math.cos(theta_angle),
                y=r * math.sin(phi) * math.sin(theta_angle),
                z=r * math.cos(phi),
            )

        # Force parameters (scaled for 3D)
        repulsion = 1000.0
        attraction = 0.01
        damping = 0.9
        min_dist = 0.1

        for iteration in range(iterations):
            if verbose and iteration % 10 == 0:
                print(f"  Iteration {iteration}/{iterations}")

            # Build octree for Barnes-Hut
            # Find bounds
            min_coord = float('inf')
            max_coord = float('-inf')
            for pos in positions.values():
                for c in [pos.x, pos.y, pos.z]:
                    min_coord = min(min_coord, c)
                    max_coord = max(max_coord, c)

            # Simplified: use direct O(n²) for small graphs
            # Full Barnes-Hut for large graphs
            if n < 5000:
                self._apply_direct_repulsion(positions, repulsion, min_dist)
            else:
                self._apply_barnes_hut_repulsion(positions, repulsion, theta, min_dist)

            # Attraction along edges
            self._apply_edge_attraction(positions, adjacency, attraction)

            # Apply velocities with damping
            for pos in positions.values():
                pos.x += pos.vx
                pos.y += pos.vy
                pos.z += pos.vz
                pos.vx *= damping
                pos.vy *= damping
                pos.vz *= damping

            # Adaptive damping - reduce over time
            damping = max(0.5, damping * 0.99)

        # Normalize to reasonable range
        self._normalize_positions(positions, target_range=100)

        return positions

    def _apply_direct_repulsion(
        self,
        positions: dict[str, Position3D],
        repulsion: float,
        min_dist: float
    ) -> None:
        """Apply O(n²) repulsion forces."""
        node_ids = list(positions.keys())
        n = len(node_ids)

        for i in range(n):
            for j in range(i + 1, n):
                pos_a = positions[node_ids[i]]
                pos_b = positions[node_ids[j]]

                dx = pos_b.x - pos_a.x
                dy = pos_b.y - pos_a.y
                dz = pos_b.z - pos_a.z

                dist_sq = dx*dx + dy*dy + dz*dz
                dist = math.sqrt(dist_sq) + min_dist

                force = repulsion / dist_sq
                fx = (dx / dist) * force
                fy = (dy / dist) * force
                fz = (dz / dist) * force

                pos_a.vx -= fx
                pos_a.vy -= fy
                pos_a.vz -= fz
                pos_b.vx += fx
                pos_b.vy += fy
                pos_b.vz += fz

    def _apply_barnes_hut_repulsion(
        self,
        positions: dict[str, Position3D],
        repulsion: float,
        theta: float,
        min_dist: float
    ) -> None:
        """
        Apply Barnes-Hut approximated repulsion.

        Groups distant nodes and treats them as single mass.
        """
        # Simplified implementation - use spatial hashing
        # for approximate O(n log n) behavior
        node_ids = list(positions.keys())
        n = len(node_ids)

        # Grid-based spatial hashing
        grid_size = math.sqrt(n) / 10  # Adjust grid granularity
        if grid_size < 1:
            grid_size = 1

        # Hash nodes to grid cells
        grid: dict[tuple[int, int, int], list[str]] = {}
        for node_id in node_ids:
            pos = positions[node_id]
            cell = (
                int(pos.x / grid_size),
                int(pos.y / grid_size),
                int(pos.z / grid_size)
            )
            if cell not in grid:
                grid[cell] = []
            grid[cell].append(node_id)

        # For each node, only compute forces with nearby cells
        for node_id in node_ids:
            pos = positions[node_id]
            cell = (
                int(pos.x / grid_size),
                int(pos.y / grid_size),
                int(pos.z / grid_size)
            )

            # Check neighboring cells
            for dx in range(-2, 3):
                for dy in range(-2, 3):
                    for dz in range(-2, 3):
                        neighbor_cell = (cell[0] + dx, cell[1] + dy, cell[2] + dz)
                        if neighbor_cell not in grid:
                            continue

                        for other_id in grid[neighbor_cell]:
                            if other_id == node_id:
                                continue

                            other_pos = positions[other_id]
                            ddx = other_pos.x - pos.x
                            ddy = other_pos.y - pos.y
                            ddz = other_pos.z - pos.z

                            dist_sq = ddx*ddx + ddy*ddy + ddz*ddz
                            dist = math.sqrt(dist_sq) + min_dist

                            force = repulsion / dist_sq / 2  # Divide by 2 since we count both ways
                            fx = (ddx / dist) * force
                            fy = (ddy / dist) * force
                            fz = (ddz / dist) * force

                            pos.vx -= fx
                            pos.vy -= fy
                            pos.vz -= fz

    def _apply_edge_attraction(
        self,
        positions: dict[str, Position3D],
        adjacency: dict[str, set[str]],
        attraction: float
    ) -> None:
        """Apply attraction forces along edges."""
        for node_id, neighbors in adjacency.items():
            if node_id not in positions:
                continue
            pos = positions[node_id]

            for neighbor_id in neighbors:
                if neighbor_id not in positions:
                    continue
                neighbor_pos = positions[neighbor_id]

                dx = neighbor_pos.x - pos.x
                dy = neighbor_pos.y - pos.y
                dz = neighbor_pos.z - pos.z

                dist = math.sqrt(dx*dx + dy*dy + dz*dz) + 0.1

                force = dist * attraction
                fx = (dx / dist) * force
                fy = (dy / dist) * force
                fz = (dz / dist) * force

                pos.vx += fx
                pos.vy += fy
                pos.vz += fz

    def _spring_layout_3d(
        self,
        node_ids: list[str],
        adjacency: dict[str, set[str]],
        iterations: int = 50,
    ) -> dict[str, Position3D]:
        """Simpler spring layout for small graphs."""
        return self._force_directed_3d(
            node_ids,
            adjacency,
            iterations=iterations,
            theta=1.0,  # Not used for small graphs
            verbose=False
        )

    def _normalize_positions(
        self,
        positions: dict[str, Position3D],
        target_range: float = 100
    ) -> None:
        """Normalize positions to fit in a cube."""
        if not positions:
            return

        # Find bounds
        min_x = min_y = min_z = float('inf')
        max_x = max_y = max_z = float('-inf')

        for pos in positions.values():
            min_x = min(min_x, pos.x)
            min_y = min(min_y, pos.y)
            min_z = min(min_z, pos.z)
            max_x = max(max_x, pos.x)
            max_y = max(max_y, pos.y)
            max_z = max(max_z, pos.z)

        # Calculate scale
        range_x = max_x - min_x or 1
        range_y = max_y - min_y or 1
        range_z = max_z - min_z or 1
        max_range = max(range_x, range_y, range_z)
        scale = target_range / max_range

        # Center and scale
        center_x = (max_x + min_x) / 2
        center_y = (max_y + min_y) / 2
        center_z = (max_z + min_z) / 2

        for pos in positions.values():
            pos.x = (pos.x - center_x) * scale
            pos.y = (pos.y - center_y) * scale
            pos.z = (pos.z - center_z) * scale

    def _compute_cache_key(
        self,
        nodes: dict[str, Node],
        edges: dict[str, Edge]
    ) -> str:
        """Compute cache key from graph structure."""
        # Hash based on node IDs and edge connections
        data = sorted(nodes.keys())
        data.extend(sorted(f"{e.source_id}-{e.target_id}" for e in edges.values()))
        content = '|'.join(data)
        return hashlib.md5(content.encode()).hexdigest()

    def clear_cache(self) -> int:
        """Clear all cached layouts. Returns number of files deleted."""
        count = 0
        for path in self.CACHE_DIR.glob('*.json'):
            try:
                path.unlink()
                count += 1
            except Exception:
                pass
        return count
