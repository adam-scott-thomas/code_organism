"""
CODE ORGANISM: THE LIVING CODE MODEL

The complete organism - a living representation of a codebase.
Contains all nodes, edges, and the machinery to trace its heartbeat.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional, Iterator, Callable, Any
from pathlib import Path
from datetime import datetime
import json

from .nodes import (
    OrganismNode,
    Edge,
    FlowParticle,
    NodeType,
    HealthStatus,
    Metrics,
    Position,
)


@dataclass
class OrganismStats:
    """Aggregate statistics about the organism."""

    # Counts
    total_nodes: int = 0
    total_edges: int = 0
    total_modules: int = 0
    total_classes: int = 0
    total_functions: int = 0
    total_lines: int = 0

    # Complexity
    avg_complexity: float = 0.0
    max_complexity: int = 0
    complexity_hotspots: list[str] = field(default_factory=list)

    # Health
    healthy_nodes: int = 0
    stressed_nodes: int = 0
    inflamed_nodes: int = 0
    necrotic_nodes: int = 0
    cancerous_nodes: int = 0

    # Structure
    max_depth: int = 0
    circular_dependencies: int = 0
    external_dependencies: int = 0

    def health_summary(self) -> dict[str, float]:
        """Get health as percentages."""
        total = self.total_nodes or 1
        return {
            "healthy": self.healthy_nodes / total,
            "stressed": self.stressed_nodes / total,
            "inflamed": self.inflamed_nodes / total,
            "necrotic": self.necrotic_nodes / total,
            "cancerous": self.cancerous_nodes / total,
        }


@dataclass
class ExecutionFrame:
    """A single frame in the execution timeline."""

    timestamp: datetime
    frame_index: int

    # What happened
    node_id: str                         # Which node was active
    event_type: str                      # "enter", "exit", "read", "write", "call", "return", "exception"
    event_data: dict = field(default_factory=dict)

    # State snapshot
    local_vars: dict = field(default_factory=dict)  # Variable values at this point
    call_stack: list[str] = field(default_factory=list)  # Stack of active function IDs

    # Performance
    elapsed_ns: int = 0                  # Nanoseconds since trace start
    memory_bytes: int = 0                # Current memory usage


@dataclass
class ExecutionTrace:
    """A complete execution trace of the organism."""

    trace_id: str
    started_at: datetime
    ended_at: Optional[datetime] = None

    # Frames
    frames: list[ExecutionFrame] = field(default_factory=list)

    # Playback state
    current_frame: int = 0
    playback_speed: float = 1.0          # 1.0 = realtime
    is_playing: bool = False

    # Statistics
    total_calls: int = 0
    total_exceptions: int = 0
    peak_memory: int = 0
    total_runtime_ns: int = 0

    def add_frame(self, frame: ExecutionFrame) -> None:
        """Add a frame to the trace."""
        self.frames.append(frame)

        # Update stats
        if frame.event_type == "call":
            self.total_calls += 1
        elif frame.event_type == "exception":
            self.total_exceptions += 1

        if frame.memory_bytes > self.peak_memory:
            self.peak_memory = frame.memory_bytes

    def get_frame(self, index: int) -> Optional[ExecutionFrame]:
        """Get a specific frame."""
        if 0 <= index < len(self.frames):
            return self.frames[index]
        return None

    def seek(self, position: float) -> int:
        """
        Seek to a position (0.0 to 1.0) in the trace.
        Returns the frame index.
        """
        if not self.frames:
            return 0

        self.current_frame = int(position * (len(self.frames) - 1))
        return self.current_frame

    def step_forward(self) -> Optional[ExecutionFrame]:
        """Move one frame forward."""
        if self.current_frame < len(self.frames) - 1:
            self.current_frame += 1
            return self.frames[self.current_frame]
        return None

    def step_backward(self) -> Optional[ExecutionFrame]:
        """Move one frame backward."""
        if self.current_frame > 0:
            self.current_frame -= 1
            return self.frames[self.current_frame]
        return None


class Organism:
    """
    The complete code organism.

    A living, breathing representation of a codebase that can be
    analyzed statically, traced dynamically, and visualized in 3D.
    """

    def __init__(self, name: str = "unnamed"):
        self.name = name
        self.created_at = datetime.utcnow()

        # The anatomy
        self.nodes: dict[str, OrganismNode] = {}
        self.edges: dict[str, Edge] = {}

        # Indices for fast lookup
        self._nodes_by_type: dict[NodeType, list[str]] = {t: [] for t in NodeType}
        self._nodes_by_file: dict[str, list[str]] = {}
        self._nodes_by_name: dict[str, list[str]] = {}

        # Root nodes (entry points)
        self.root_ids: list[str] = []

        # Dynamic state
        self.particles: list[FlowParticle] = []
        self.active_trace: Optional[ExecutionTrace] = None
        self.traces: list[ExecutionTrace] = []

        # Computed stats
        self._stats: Optional[OrganismStats] = None
        self._stats_dirty = True

    # =========================================================================
    # CONSTRUCTION
    # =========================================================================

    @classmethod
    def from_file(cls, filepath: str | Path) -> "Organism":
        """Create an organism from a single Python file."""
        from ..parser.ast_walker import parse_file

        filepath = Path(filepath)
        organism = cls(name=filepath.stem)

        # Parse the file
        nodes, edges = parse_file(filepath)

        # Add to organism
        for node in nodes:
            organism.add_node(node)
        for edge in edges:
            organism.add_edge(edge)

        # The module is a root
        for node in nodes:
            if node.node_type == NodeType.MODULE:
                organism.root_ids.append(node.id)

        organism.analyze_health()
        return organism

    @classmethod
    def from_directory(cls, dirpath: str | Path, pattern: str = "**/*.py") -> "Organism":
        """Create an organism from a directory of Python files."""
        from ..parser.ast_walker import parse_file

        dirpath = Path(dirpath)
        organism = cls(name=dirpath.name)

        # Find all Python files
        for filepath in dirpath.glob(pattern):
            if filepath.is_file():
                try:
                    nodes, edges = parse_file(filepath)
                    for node in nodes:
                        organism.add_node(node)
                    for edge in edges:
                        organism.add_edge(edge)

                    # Package __init__.py files are roots
                    if filepath.name == "__init__.py":
                        for node in nodes:
                            if node.node_type == NodeType.MODULE:
                                organism.root_ids.append(node.id)

                except Exception as e:
                    print(f"Warning: Failed to parse {filepath}: {e}")

        # If no __init__.py found, use all modules as roots
        if not organism.root_ids:
            organism.root_ids = organism._nodes_by_type[NodeType.MODULE].copy()

        organism.analyze_health()
        return organism

    @classmethod
    def from_source(cls, source: str, filename: str = "<string>") -> "Organism":
        """Create an organism from source code string."""
        from ..parser.ast_walker import parse_source

        organism = cls(name=filename)

        nodes, edges = parse_source(source, filename)

        for node in nodes:
            organism.add_node(node)
        for edge in edges:
            organism.add_edge(edge)

        for node in nodes:
            if node.node_type == NodeType.MODULE:
                organism.root_ids.append(node.id)

        organism.analyze_health()
        return organism

    # =========================================================================
    # NODE MANAGEMENT
    # =========================================================================

    def add_node(self, node: OrganismNode) -> None:
        """Add a node to the organism."""
        self.nodes[node.id] = node
        self._nodes_by_type[node.node_type].append(node.id)

        if node.position and node.position.file:
            if node.position.file not in self._nodes_by_file:
                self._nodes_by_file[node.position.file] = []
            self._nodes_by_file[node.position.file].append(node.id)

        if node.name not in self._nodes_by_name:
            self._nodes_by_name[node.name] = []
        self._nodes_by_name[node.name].append(node.id)

        self._stats_dirty = True

    def get_node(self, node_id: str) -> Optional[OrganismNode]:
        """Get a node by ID."""
        return self.nodes.get(node_id)

    def get_nodes_by_type(self, node_type: NodeType) -> Iterator[OrganismNode]:
        """Iterate over all nodes of a specific type."""
        for node_id in self._nodes_by_type[node_type]:
            yield self.nodes[node_id]

    def get_nodes_by_file(self, filepath: str) -> Iterator[OrganismNode]:
        """Iterate over all nodes in a specific file."""
        for node_id in self._nodes_by_file.get(filepath, []):
            yield self.nodes[node_id]

    def find_nodes(self, name: str) -> list[OrganismNode]:
        """Find nodes by name (may return multiple)."""
        return [self.nodes[nid] for nid in self._nodes_by_name.get(name, [])]

    # =========================================================================
    # EDGE MANAGEMENT
    # =========================================================================

    def add_edge(self, edge: Edge) -> None:
        """Add an edge to the organism."""
        self.edges[edge.id] = edge

        # Update node connection lists
        source = self.nodes.get(edge.source_id)
        target = self.nodes.get(edge.target_id)

        if source and target:
            if edge.edge_type == "import":
                source.imports.append(edge.target_id)
                target.imported_by.append(edge.source_id)
            elif edge.edge_type == "call":
                source.calls.append(edge.target_id)
                target.called_by.append(edge.source_id)
            elif edge.edge_type == "reference":
                source.references.append(edge.target_id)
                target.referenced_by.append(edge.source_id)

        self._stats_dirty = True

    def get_edge(self, edge_id: str) -> Optional[Edge]:
        """Get an edge by ID."""
        return self.edges.get(edge_id)

    def get_edges_from(self, node_id: str) -> Iterator[Edge]:
        """Get all edges originating from a node."""
        for edge in self.edges.values():
            if edge.source_id == node_id:
                yield edge

    def get_edges_to(self, node_id: str) -> Iterator[Edge]:
        """Get all edges pointing to a node."""
        for edge in self.edges.values():
            if edge.target_id == node_id:
                yield edge

    # =========================================================================
    # ANALYSIS
    # =========================================================================

    def analyze_health(self) -> None:
        """Analyze the health of all nodes."""
        for node in self.nodes.values():
            node.update_health()
        self._stats_dirty = True

    def find_circular_dependencies(self) -> list[list[str]]:
        """Find all circular dependency chains."""
        cycles = []
        visited = set()
        path = []

        def dfs(node_id: str) -> None:
            if node_id in path:
                # Found a cycle
                cycle_start = path.index(node_id)
                cycles.append(path[cycle_start:])
                return

            if node_id in visited:
                return

            visited.add(node_id)
            path.append(node_id)

            node = self.nodes.get(node_id)
            if node:
                for target_id in node.imports + node.calls:
                    dfs(target_id)

            path.pop()

        for node_id in self.nodes:
            dfs(node_id)

        return cycles

    def find_dead_code(self) -> list[OrganismNode]:
        """Find unreachable/unused code."""
        dead = []
        for node in self.nodes.values():
            if node.health == HealthStatus.NECROTIC:
                dead.append(node)
        return dead

    def find_complexity_hotspots(self, threshold: int = 10) -> list[OrganismNode]:
        """Find nodes with high cyclomatic complexity."""
        hotspots = []
        for node in self.nodes.values():
            if node.metrics.cyclomatic_complexity >= threshold:
                hotspots.append(node)
        return sorted(hotspots, key=lambda n: n.metrics.cyclomatic_complexity, reverse=True)

    @property
    def stats(self) -> OrganismStats:
        """Get aggregate statistics (computed lazily)."""
        if self._stats_dirty or self._stats is None:
            self._compute_stats()
        return self._stats

    def _compute_stats(self) -> None:
        """Compute aggregate statistics."""
        stats = OrganismStats()

        stats.total_nodes = len(self.nodes)
        stats.total_edges = len(self.edges)
        stats.total_modules = len(self._nodes_by_type[NodeType.MODULE])
        stats.total_classes = len(self._nodes_by_type[NodeType.CLASS])
        stats.total_functions = len(self._nodes_by_type[NodeType.FUNCTION]) + \
                                len(self._nodes_by_type[NodeType.METHOD])

        # Complexity
        complexities = []
        for node in self.nodes.values():
            c = node.metrics.cyclomatic_complexity
            complexities.append(c)
            if c > stats.max_complexity:
                stats.max_complexity = c
            if c >= 10:
                stats.complexity_hotspots.append(node.qualified_name)
            stats.total_lines += node.metrics.lines_of_code

            # Depth
            if node.metrics.depth > stats.max_depth:
                stats.max_depth = node.metrics.depth

            # Health counts
            if node.health == HealthStatus.HEALTHY:
                stats.healthy_nodes += 1
            elif node.health == HealthStatus.STRESSED:
                stats.stressed_nodes += 1
            elif node.health == HealthStatus.INFLAMED:
                stats.inflamed_nodes += 1
            elif node.health == HealthStatus.NECROTIC:
                stats.necrotic_nodes += 1
            elif node.health == HealthStatus.CANCEROUS:
                stats.cancerous_nodes += 1

        if complexities:
            stats.avg_complexity = sum(complexities) / len(complexities)

        # External dependencies
        stats.external_dependencies = len(self._nodes_by_type[NodeType.EXTERNAL_MODULE])

        # Circular dependencies
        stats.circular_dependencies = len(self.find_circular_dependencies())

        self._stats = stats
        self._stats_dirty = False

    # =========================================================================
    # TRACING
    # =========================================================================

    def start_trace(self, trace_id: Optional[str] = None) -> ExecutionTrace:
        """Start a new execution trace."""
        from datetime import datetime
        import uuid

        trace = ExecutionTrace(
            trace_id=trace_id or str(uuid.uuid4())[:8],
            started_at=datetime.utcnow(),
        )
        self.active_trace = trace
        self.traces.append(trace)
        return trace

    def stop_trace(self) -> Optional[ExecutionTrace]:
        """Stop the current trace."""
        if self.active_trace:
            self.active_trace.ended_at = datetime.utcnow()
            if self.active_trace.frames:
                self.active_trace.total_runtime_ns = \
                    self.active_trace.frames[-1].elapsed_ns
            trace = self.active_trace
            self.active_trace = None
            return trace
        return None

    def record_frame(self, frame: ExecutionFrame) -> None:
        """Record a frame to the active trace."""
        if self.active_trace:
            self.active_trace.add_frame(frame)

            # Spawn a flow particle for visualization
            node = self.nodes.get(frame.node_id)
            if node and frame.event_type == "call":
                # Find edges from caller to this function
                for edge_id in node.called_by:
                    edge = self.get_edge(edge_id)
                    if edge:
                        particle = FlowParticle(
                            id=f"p-{len(self.particles)}",
                            edge_id=edge.id,
                            data_type=frame.event_data.get("return_type"),
                            data_size=frame.event_data.get("data_size", 0),
                        )
                        particle.set_color_by_type()
                        self.particles.append(particle)

    # =========================================================================
    # VISUALIZATION
    # =========================================================================

    def update_particles(self, dt: float) -> None:
        """Update all flow particles. Called each frame."""
        self.particles = [p for p in self.particles if p.update(dt)]

    def set_node_activity(self, node_id: str, level: float) -> None:
        """Set the activity level of a node (for highlighting)."""
        node = self.nodes.get(node_id)
        if node:
            node.set_activity(level)

    def get_layout_data(self) -> dict:
        """
        Get data formatted for 3D layout engine.

        Returns a dict with nodes and edges in a format
        suitable for force-directed graph layout.
        """
        return {
            "nodes": [
                {
                    "id": node.id,
                    "name": node.name,
                    "type": node.node_type.value,
                    "size": node.size,
                    "color": node.color,
                    "health": node.health.value,
                    "glow": node.glow,
                }
                for node in self.nodes.values()
            ],
            "edges": [
                {
                    "id": edge.id,
                    "source": edge.source_id,
                    "target": edge.target_id,
                    "type": edge.edge_type,
                    "weight": edge.weight,
                    "color": edge.color,
                }
                for edge in self.edges.values()
            ],
            "particles": [
                {
                    "id": p.id,
                    "edge": p.edge_id,
                    "position": p.position,
                    "color": p.color,
                    "size": p.size,
                }
                for p in self.particles
            ],
        }

    # =========================================================================
    # HIERARCHICAL / LARGE-SCALE VISUALIZATION
    # =========================================================================

    def get_hierarchical_layout_data(
        self,
        level: int = 0,
        max_nodes: int = 5000,
    ) -> dict:
        """
        Get hierarchical data for large-scale visualization.

        For massive codebases (millions of nodes), returns clustered data
        that can be progressively expanded.

        Args:
            level: Detail level (0 = top overview, higher = more detail)
            max_nodes: Maximum nodes to return at this level

        Returns:
            Dict with cluster nodes, edges, and positions
        """
        from .clustering import HierarchicalClusterer
        from .layout import LayoutEngine

        # Check if we need clustering
        if len(self.nodes) <= max_nodes:
            # Small enough to show directly
            layout_engine = LayoutEngine()
            positions = layout_engine.compute_layout(self.nodes, self.edges)

            return {
                "nodes": [
                    {
                        "id": node.id,
                        "name": node.name,
                        "type": node.node_type.value,
                        "size": node.size,
                        "color": node.color,
                        "health": node.health.value,
                        "expandable": False,
                        **positions.get(node.id, {"x": 0, "y": 0, "z": 0}),
                    }
                    for node in self.nodes.values()
                ],
                "edges": [
                    {
                        "id": edge.id,
                        "source": edge.source_id,
                        "target": edge.target_id,
                        "type": edge.edge_type,
                        "weight": edge.weight,
                    }
                    for edge in self.edges.values()
                ],
                "total_nodes": len(self.nodes),
                "level": 0,
                "is_clustered": False,
            }

        # Need hierarchical clustering
        if not hasattr(self, '_clusterer') or self._clusterer is None:
            self._clusterer = HierarchicalClusterer(self.nodes, self.edges)
            self._num_levels = self._clusterer.compute_hierarchy(
                target_top_level_count=100
            )
            self._layout_engine = LayoutEngine()

        # Get clusters at requested level
        clusters = self._clusterer.get_level(level)
        if not clusters:
            clusters = self._clusterer.get_top_level()

        # Get edges between clusters
        cluster_edges = self._clusterer.get_cluster_edges(clusters)

        # Compute layout for clusters
        positions = self._layout_engine.compute_cluster_layout(clusters, cluster_edges)

        # Apply positions to clusters
        for cluster_id, pos in positions.items():
            if cluster_id in clusters:
                clusters[cluster_id].x = pos['x']
                clusters[cluster_id].y = pos['y']
                clusters[cluster_id].z = pos['z']

        return {
            "nodes": [c.to_dict() for c in clusters.values()],
            "edges": [e.to_dict() for e in cluster_edges],
            "total_nodes": len(self.nodes),
            "level": level,
            "num_levels": getattr(self, '_num_levels', 1),
            "is_clustered": True,
        }

    def get_cluster_children(self, cluster_id: str) -> dict:
        """
        Get children of a cluster for drill-down expansion.

        Args:
            cluster_id: ID of cluster to expand

        Returns:
            Dict with child nodes/clusters, edges, and positions
        """
        if not hasattr(self, '_clusterer') or self._clusterer is None:
            return {"nodes": [], "edges": [], "error": "No clustering computed"}

        child_ids = self._clusterer.get_children(cluster_id)
        if not child_ids:
            return {"nodes": [], "edges": [], "error": "Cluster not found"}

        # Determine if children are leaf nodes or clusters
        # Check if child_ids are actual node IDs
        are_leaf_nodes = all(cid in self.nodes for cid in child_ids)

        if are_leaf_nodes:
            # Return actual nodes
            nodes_data = []
            for node_id in child_ids:
                node = self.nodes.get(node_id)
                if node:
                    nodes_data.append({
                        "id": node.id,
                        "name": node.name,
                        "type": node.node_type.value,
                        "size": node.size,
                        "color": node.color,
                        "health": node.health.value,
                        "expandable": False,
                    })

            # Get edges between these nodes
            edges_data = []
            node_set = set(child_ids)
            for edge in self.edges.values():
                if edge.source_id in node_set and edge.target_id in node_set:
                    edges_data.append({
                        "id": edge.id,
                        "source": edge.source_id,
                        "target": edge.target_id,
                        "type": edge.edge_type,
                    })

            # Compute layout
            if nodes_data:
                sub_nodes = {n['id']: self.nodes[n['id']] for n in nodes_data if n['id'] in self.nodes}
                sub_edges = {e['id']: self.edges[e['id']] for e in edges_data if e['id'] in self.edges}
                positions = self._layout_engine.compute_layout(sub_nodes, sub_edges)

                for node_data in nodes_data:
                    pos = positions.get(node_data['id'], {})
                    node_data['x'] = pos.get('x', 0)
                    node_data['y'] = pos.get('y', 0)
                    node_data['z'] = pos.get('z', 0)

            return {
                "parent_id": cluster_id,
                "nodes": nodes_data,
                "edges": edges_data,
                "is_leaf": True,
            }
        else:
            # Children are clusters - find them in levels
            child_clusters = {}
            for level_clusters in self._clusterer.levels:
                for cid in child_ids:
                    if cid in level_clusters:
                        child_clusters[cid] = level_clusters[cid]

            cluster_edges = self._clusterer.get_cluster_edges(child_clusters)
            positions = self._layout_engine.compute_cluster_layout(
                child_clusters, cluster_edges
            )

            for cid, pos in positions.items():
                if cid in child_clusters:
                    child_clusters[cid].x = pos['x']
                    child_clusters[cid].y = pos['y']
                    child_clusters[cid].z = pos['z']

            return {
                "parent_id": cluster_id,
                "nodes": [c.to_dict() for c in child_clusters.values()],
                "edges": [e.to_dict() for e in cluster_edges],
                "is_leaf": False,
            }

    # =========================================================================
    # SERIALIZATION
    # =========================================================================

    def to_dict(self) -> dict:
        """Serialize organism to dictionary."""
        return {
            "name": self.name,
            "created_at": self.created_at.isoformat(),
            "nodes": {nid: self._node_to_dict(n) for nid, n in self.nodes.items()},
            "edges": {eid: self._edge_to_dict(e) for eid, e in self.edges.items()},
            "root_ids": self.root_ids,
            "stats": self._stats_to_dict() if self._stats else None,
        }

    def _node_to_dict(self, node: OrganismNode) -> dict:
        """Serialize a node to dictionary."""
        return {
            "id": node.id,
            "name": node.name,
            "type": node.node_type.value,
            "qualified_name": node.qualified_name,
            "position": {
                "file": node.position.file,
                "line": node.position.line,
                "column": node.position.column,
            } if node.position else None,
            "parent_id": node.parent_id,
            "children_ids": node.children_ids,
            "imports": node.imports,
            "calls": node.calls,
            "docstring": node.docstring,
            "signature": node.signature,
            "metrics": {
                "cyclomatic_complexity": node.metrics.cyclomatic_complexity,
                "lines_of_code": node.metrics.lines_of_code,
                "depth": node.metrics.depth,
            },
            "health": node.health.value,
            "health_notes": node.health_notes,
            "color": node.color,
            "size": node.size,
        }

    def _edge_to_dict(self, edge: Edge) -> dict:
        """Serialize an edge to dictionary."""
        return {
            "id": edge.id,
            "source_id": edge.source_id,
            "target_id": edge.target_id,
            "edge_type": edge.edge_type,
            "weight": edge.weight,
            "color": edge.color,
        }

    def _stats_to_dict(self) -> dict:
        """Serialize stats to dictionary."""
        return {
            "total_nodes": self._stats.total_nodes,
            "total_edges": self._stats.total_edges,
            "total_modules": self._stats.total_modules,
            "total_classes": self._stats.total_classes,
            "total_functions": self._stats.total_functions,
            "total_lines": self._stats.total_lines,
            "avg_complexity": self._stats.avg_complexity,
            "max_complexity": self._stats.max_complexity,
            "healthy_pct": self._stats.health_summary()["healthy"],
            "circular_dependencies": self._stats.circular_dependencies,
        }

    def to_json(self, indent: int = 2) -> str:
        """Serialize organism to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, filepath: str | Path) -> None:
        """Save organism to a JSON file."""
        with open(filepath, "w") as f:
            f.write(self.to_json())

    @classmethod
    def load(cls, filepath: str | Path) -> "Organism":
        """Load organism from a JSON file."""
        with open(filepath) as f:
            data = json.load(f)

        organism = cls(name=data["name"])
        # TODO: Implement full deserialization
        return organism
