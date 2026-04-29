# SPDX-License-Identifier: Apache-2.0
"""
CODE ORGANISM VISUALIZER

See the soul of software.

A 3D visualization system that renders code as a living organism,
revealing its true architectural beauty or exposing its cancerous patterns.

Usage:
    from code_organism import Organism

    # Analyze a file
    org = Organism.from_file("my_script.py")

    # Visualize in 3D
    org.visualize()

    # Record and playback execution
    from code_organism import record_execution, render_playback

    with record_execution(org) as session:
        # Run your code
        my_function()

    # Play it back
    render_playback(session)
"""

from .analysis.communities import detect_communities
from .analysis.impact import analyze_impact
from .analysis.processes import detect_processes
from .graph.store import GraphStore
from .health import (
    ComplexityAnalyzer,
    MalwareAnalyzer,
    PatternDetector,
    analyze_complexity,
    analyze_for_malware,
    detect_patterns,
)
from .model import (
    Edge,
    ExecutionFrame,
    ExecutionTrace,
    FlowParticle,
    HealthStatus,
    Metrics,
    NodeType,
    Organism,
    OrganismNode,
    OrganismStats,
    Position,
)
from .parser import parse_file, parse_source
from .renderer import (
    OrganismRenderer,
    PlaybackRenderer,
    render_organism,
    render_playback,
    render_playback_file,
)
from .timeline import (
    ExecutionRecorder,
    PlaybackState,
    RecordingSession,
    TimelineController,
    TimelinePlayer,
    record_execution,
)
from .tracer import Tracer, trace_execution, trace_function

__version__ = "2.0.0"

__all__ = [
    # Core Model
    "Organism",
    "OrganismNode",
    "Edge",
    "FlowParticle",
    "NodeType",
    "HealthStatus",
    "Metrics",
    "Position",
    "OrganismStats",
    "ExecutionFrame",
    "ExecutionTrace",
    # Parser
    "parse_file",
    "parse_source",
    # Static Renderer
    "OrganismRenderer",
    "render_organism",
    # Playback Renderer
    "PlaybackRenderer",
    "render_playback",
    "render_playback_file",
    # Timeline
    "ExecutionRecorder",
    "RecordingSession",
    "record_execution",
    "TimelinePlayer",
    "PlaybackState",
    "TimelineController",
    # Tracer
    "Tracer",
    "trace_execution",
    "trace_function",
    # Health Analysis
    "MalwareAnalyzer",
    "analyze_for_malware",
    "PatternDetector",
    "detect_patterns",
    "ComplexityAnalyzer",
    "analyze_complexity",
    # Graph Storage
    "GraphStore",
    # Analysis
    "detect_communities",
    "detect_processes",
    "analyze_impact",
]
