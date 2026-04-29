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

from .model import (
    Organism,
    OrganismNode,
    Edge,
    FlowParticle,
    NodeType,
    HealthStatus,
    Metrics,
    Position,
    OrganismStats,
    ExecutionFrame,
    ExecutionTrace,
)

from .parser import parse_file, parse_source

from .renderer import (
    OrganismRenderer,
    render_organism,
    PlaybackRenderer,
    render_playback,
    render_playback_file,
)

from .timeline import (
    ExecutionRecorder,
    RecordingSession,
    record_execution,
    TimelinePlayer,
    PlaybackState,
    TimelineController,
)

from .tracer import Tracer, trace_execution, trace_function

from .health import (
    MalwareAnalyzer,
    analyze_for_malware,
    PatternDetector,
    detect_patterns,
    ComplexityAnalyzer,
    analyze_complexity,
)

from .graph.store import GraphStore
from .analysis.communities import detect_communities
from .analysis.processes import detect_processes
from .analysis.impact import analyze_impact

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
