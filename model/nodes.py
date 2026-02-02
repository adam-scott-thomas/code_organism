"""
CODE ORGANISM: NODE DEFINITIONS

Every piece of code maps to an anatomical structure.
These are the cells, tissues, and organs of the code organism.
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional, Any
from datetime import datetime
import hashlib


class NodeType(Enum):
    """The type of anatomical structure this node represents."""

    # SKELETAL SYSTEM (Structure)
    MODULE = "module"              # A Python file - like a bone
    PACKAGE = "package"            # A directory with __init__ - like a bone cluster

    # ORGAN SYSTEMS (Functional Units)
    CLASS = "class"                # A class definition - like an organ
    FUNCTION = "function"          # A function - like a tissue
    METHOD = "method"              # A method - tissue within an organ

    # CELLULAR LEVEL (Fine Detail)
    VARIABLE = "variable"          # A variable - like a cell
    PARAMETER = "parameter"        # A function parameter - input receptor
    ATTRIBUTE = "attribute"        # A class attribute - organ property

    # CONNECTIVE TISSUE (Relationships)
    IMPORT = "import"              # An import statement - ligament
    CALL = "call"                  # A function call - nerve signal
    REFERENCE = "reference"        # A variable reference - blood vessel

    # EXTERNAL SYSTEMS (Dependencies)
    EXTERNAL_MODULE = "external"   # Third-party import - symbiotic organism
    BUILTIN = "builtin"            # Python builtin - fundamental chemistry


class HealthStatus(Enum):
    """The health state of a code structure."""

    HEALTHY = "healthy"            # Clean, well-structured
    STRESSED = "stressed"          # High complexity, needs attention
    INFLAMED = "inflamed"          # Circular dependencies, tight coupling
    NECROTIC = "necrotic"          # Dead code, unreachable
    CANCEROUS = "cancerous"        # Obfuscated, malicious patterns
    UNKNOWN = "unknown"            # Not yet analyzed


@dataclass
class Position:
    """Position in source code."""
    file: str
    line: int
    column: int
    end_line: Optional[int] = None
    end_column: Optional[int] = None

    def __str__(self) -> str:
        return f"{self.file}:{self.line}:{self.column}"


@dataclass
class Metrics:
    """Complexity and health metrics for a node."""

    # Complexity metrics
    cyclomatic_complexity: int = 0      # Branching complexity
    cognitive_complexity: int = 0       # Human comprehension difficulty
    lines_of_code: int = 0              # Size
    depth: int = 0                      # Nesting depth

    # Coupling metrics
    afferent_coupling: int = 0          # Incoming dependencies (who uses me)
    efferent_coupling: int = 0          # Outgoing dependencies (who I use)
    instability: float = 0.0            # Efferent / (Afferent + Efferent)

    # Health indicators
    halstead_difficulty: float = 0.0    # Halstead difficulty metric
    maintainability_index: float = 100.0  # 0-100, higher is better

    # Dynamic metrics (populated during tracing)
    call_count: int = 0                 # Times called during trace
    total_time_ms: float = 0.0          # Total execution time
    avg_time_ms: float = 0.0            # Average execution time
    memory_allocated: int = 0           # Bytes allocated
    exceptions_raised: int = 0          # Errors during execution

    def health_score(self) -> float:
        """
        Calculate overall health score 0.0 (dead) to 1.0 (perfect).
        """
        score = 1.0

        # Penalize high complexity
        if self.cyclomatic_complexity > 10:
            score -= min(0.3, (self.cyclomatic_complexity - 10) * 0.03)

        # Penalize deep nesting
        if self.depth > 4:
            score -= min(0.2, (self.depth - 4) * 0.05)

        # Penalize high instability with high afferent coupling
        # (many depend on something unstable = fragile)
        if self.instability > 0.8 and self.afferent_coupling > 5:
            score -= 0.2

        # Reward maintainability
        score += (self.maintainability_index / 100) * 0.2 - 0.1

        return max(0.0, min(1.0, score))


@dataclass
class OrganismNode:
    """
    A single node in the code organism.

    This is the fundamental building block - like a cell that can
    differentiate into various tissue types based on its role.
    """

    # Identity
    id: str                              # Unique identifier
    name: str                            # Human-readable name
    node_type: NodeType                  # What kind of structure
    qualified_name: str                  # Full dotted path (e.g., "module.Class.method")

    # Location
    position: Optional[Position] = None  # Where in source code

    # Relationships (populated during graph building)
    parent_id: Optional[str] = None      # Containing structure
    children_ids: list[str] = field(default_factory=list)  # Contained structures

    # Connections (populated during graph building)
    imports: list[str] = field(default_factory=list)      # What this imports
    imported_by: list[str] = field(default_factory=list)  # What imports this
    calls: list[str] = field(default_factory=list)        # Functions this calls
    called_by: list[str] = field(default_factory=list)    # Functions that call this
    references: list[str] = field(default_factory=list)   # Variables this references
    referenced_by: list[str] = field(default_factory=list)  # What references this

    # Content
    source_code: Optional[str] = None    # The actual source (optional)
    docstring: Optional[str] = None      # Documentation
    signature: Optional[str] = None      # For functions: the signature

    # Type information
    type_annotation: Optional[str] = None  # Type hint if present
    return_type: Optional[str] = None    # For functions: return type

    # Metrics and health
    metrics: Metrics = field(default_factory=Metrics)
    health: HealthStatus = HealthStatus.UNKNOWN
    health_notes: list[str] = field(default_factory=list)

    # Visualization properties
    color: Optional[tuple[float, float, float]] = None  # RGB 0-1
    size: float = 1.0                    # Relative size
    glow: float = 0.0                    # 0-1, for highlighting activity
    pulse_rate: float = 0.0              # For animation, Hz

    # Metadata
    created_at: datetime = field(default_factory=datetime.utcnow)
    analyzed_at: Optional[datetime] = None

    def __post_init__(self):
        """Set default visualization properties based on type."""
        if self.color is None:
            self.color = self._default_color()
        if self.size == 1.0:
            self.size = self._default_size()

    def _default_color(self) -> tuple[float, float, float]:
        """Default color based on node type."""
        colors = {
            # Skeletal - white/gray (bone)
            NodeType.MODULE: (0.9, 0.9, 0.95),
            NodeType.PACKAGE: (0.85, 0.85, 0.9),

            # Organs - rich colors
            NodeType.CLASS: (0.8, 0.2, 0.2),      # Red (heart/muscle)
            NodeType.FUNCTION: (0.2, 0.6, 0.8),   # Blue (veins)
            NodeType.METHOD: (0.6, 0.3, 0.7),     # Purple (capillaries)

            # Cellular - subtle
            NodeType.VARIABLE: (0.3, 0.8, 0.3),   # Green (cells)
            NodeType.PARAMETER: (0.8, 0.7, 0.2),  # Yellow (receptors)
            NodeType.ATTRIBUTE: (0.7, 0.5, 0.3),  # Orange (properties)

            # Connective - neutral
            NodeType.IMPORT: (0.5, 0.5, 0.5),     # Gray
            NodeType.CALL: (0.4, 0.4, 0.6),       # Blue-gray
            NodeType.REFERENCE: (0.4, 0.6, 0.4),  # Green-gray

            # External - foreign
            NodeType.EXTERNAL_MODULE: (0.6, 0.4, 0.8),  # Alien purple
            NodeType.BUILTIN: (0.2, 0.2, 0.2),    # Dark (fundamental)
        }
        return colors.get(self.node_type, (0.5, 0.5, 0.5))

    def _default_size(self) -> float:
        """Default size based on node type."""
        sizes = {
            NodeType.PACKAGE: 3.0,
            NodeType.MODULE: 2.0,
            NodeType.CLASS: 1.5,
            NodeType.FUNCTION: 1.0,
            NodeType.METHOD: 0.8,
            NodeType.VARIABLE: 0.3,
            NodeType.PARAMETER: 0.25,
            NodeType.ATTRIBUTE: 0.35,
            NodeType.IMPORT: 0.1,
            NodeType.CALL: 0.1,
            NodeType.REFERENCE: 0.05,
            NodeType.EXTERNAL_MODULE: 1.0,
            NodeType.BUILTIN: 0.5,
        }
        return sizes.get(self.node_type, 1.0)

    def update_health(self) -> None:
        """Update health status based on metrics and patterns."""
        score = self.metrics.health_score()

        # Check for specific conditions
        self.health_notes.clear()

        # Dead code detection
        if (self.node_type in (NodeType.FUNCTION, NodeType.METHOD)
            and len(self.called_by) == 0
            and self.name != "__init__"
            and not self.name.startswith("_")):
            self.health = HealthStatus.NECROTIC
            self.health_notes.append("Never called - dead code")
            return

        # Circular dependency (simplified check)
        if self.id in self.imports or self.id in self.calls:
            self.health = HealthStatus.INFLAMED
            self.health_notes.append("Self-referential - circular dependency")
            return

        # Score-based health
        if score >= 0.8:
            self.health = HealthStatus.HEALTHY
        elif score >= 0.6:
            self.health = HealthStatus.STRESSED
            self.health_notes.append(f"Moderate complexity (score: {score:.2f})")
        elif score >= 0.3:
            self.health = HealthStatus.INFLAMED
            self.health_notes.append(f"High complexity (score: {score:.2f})")
        else:
            self.health = HealthStatus.CANCEROUS
            self.health_notes.append(f"Critical complexity (score: {score:.2f})")

        self.analyzed_at = datetime.utcnow()

    def set_activity(self, level: float) -> None:
        """
        Set the activity level for visualization (0.0 to 1.0).
        Higher activity = more glow and faster pulse.
        """
        self.glow = min(1.0, level)
        self.pulse_rate = level * 2.0  # 0-2 Hz

    @staticmethod
    def generate_id(qualified_name: str, node_type: NodeType) -> str:
        """Generate a unique ID for a node."""
        content = f"{node_type.value}:{qualified_name}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class Edge:
    """
    A connection between two nodes in the organism.

    Like blood vessels, nerves, or ligaments connecting
    different parts of the body.
    """

    id: str                              # Unique identifier
    source_id: str                       # Origin node
    target_id: str                       # Destination node
    edge_type: str                       # "import", "call", "reference", etc.

    # Properties
    weight: float = 1.0                  # Strength of connection
    bidirectional: bool = False          # Two-way connection

    # Dynamic properties (from tracing)
    flow_count: int = 0                  # Times data flowed through
    last_flow_time: Optional[datetime] = None
    avg_data_size: int = 0               # Average bytes transferred

    # Visualization
    color: Optional[tuple[float, float, float]] = None
    thickness: float = 1.0
    animated: bool = False               # Show flow animation
    flow_speed: float = 1.0              # Animation speed multiplier

    def __post_init__(self):
        if self.color is None:
            self.color = self._default_color()

    def _default_color(self) -> tuple[float, float, float]:
        """Default color based on edge type."""
        colors = {
            "import": (0.7, 0.7, 0.7),      # Gray - structural
            "call": (0.3, 0.5, 0.9),        # Blue - neural
            "reference": (0.3, 0.8, 0.3),   # Green - vascular
            "inheritance": (0.9, 0.3, 0.3), # Red - genetic
            "composition": (0.8, 0.6, 0.2), # Orange - containment
        }
        return colors.get(self.edge_type, (0.5, 0.5, 0.5))

    @staticmethod
    def generate_id(source_id: str, target_id: str, edge_type: str) -> str:
        """Generate a unique ID for an edge."""
        content = f"{edge_type}:{source_id}->{target_id}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]


@dataclass
class FlowParticle:
    """
    A particle representing data flowing through the organism.

    Like a blood cell carrying oxygen, or a nerve impulse
    carrying a signal. Used for animation during execution playback.
    """

    id: str                              # Unique identifier
    edge_id: str                         # Which edge this flows through

    # Position (0.0 = at source, 1.0 = at target)
    position: float = 0.0
    speed: float = 1.0                   # Units per second

    # What it's carrying
    data_type: Optional[str] = None      # Type of data being transferred
    data_preview: Optional[str] = None   # String preview of data
    data_size: int = 0                   # Bytes

    # Visualization
    color: tuple[float, float, float] = (1.0, 1.0, 1.0)  # White default
    size: float = 0.2
    trail_length: float = 0.1            # How long the trail behind particle

    # Lifecycle
    created_at: datetime = field(default_factory=datetime.utcnow)
    lifetime_seconds: float = 5.0        # How long before particle dies

    def update(self, dt: float) -> bool:
        """
        Update particle position. Returns False if particle should be removed.

        Args:
            dt: Time delta in seconds

        Returns:
            True if particle is still alive, False if it should be removed
        """
        self.position += self.speed * dt

        # Check if reached destination or expired
        age = (datetime.utcnow() - self.created_at).total_seconds()

        if self.position >= 1.0 or age > self.lifetime_seconds:
            return False

        return True

    def set_color_by_type(self) -> None:
        """Set color based on data type being carried."""
        type_colors = {
            "int": (0.3, 0.5, 1.0),       # Blue - simple numeric
            "float": (0.2, 0.6, 0.9),     # Light blue - floating
            "str": (0.3, 0.8, 0.3),       # Green - text
            "bool": (1.0, 1.0, 0.3),      # Yellow - binary
            "list": (0.8, 0.4, 0.8),      # Purple - collection
            "dict": (0.9, 0.5, 0.2),      # Orange - mapping
            "None": (0.5, 0.5, 0.5),      # Gray - null
            "Exception": (1.0, 0.2, 0.2), # Red - error!
        }

        if self.data_type:
            base_type = self.data_type.split("[")[0]  # Handle generics
            self.color = type_colors.get(base_type, (1.0, 1.0, 1.0))
