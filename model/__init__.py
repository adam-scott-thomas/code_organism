"""
Code Organism Model

The data structures representing a living codebase.
"""

from .nodes import (
    OrganismNode,
    Edge,
    FlowParticle,
    NodeType,
    HealthStatus,
    Metrics,
    Position,
)

from .organism import (
    Organism,
    OrganismStats,
    ExecutionFrame,
    ExecutionTrace,
)

from .clustering import (
    HierarchicalClusterer,
    ClusterNode,
    ClusterEdge,
)

from .layout import (
    LayoutEngine,
    Position3D,
)

__all__ = [
    # Nodes
    "OrganismNode",
    "Edge",
    "FlowParticle",
    "NodeType",
    "HealthStatus",
    "Metrics",
    "Position",
    # Organism
    "Organism",
    "OrganismStats",
    "ExecutionFrame",
    "ExecutionTrace",
    # Clustering
    "HierarchicalClusterer",
    "ClusterNode",
    "ClusterEdge",
    # Layout
    "LayoutEngine",
    "Position3D",
]
