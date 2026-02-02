"""
Code Organism Timeline & Playback

Controls for recording, replaying, and navigating execution traces.
"""

from .recorder import (
    ExecutionRecorder,
    RecordingSession,
    RecordingMetadata,
    RecordingContext,
    record_execution,
)

from .player import (
    TimelinePlayer,
    PlaybackState,
    PlaybackEvent,
    PlaybackPosition,
)

from .controls import (
    TimelineController,
    ControlCommand,
    ControlBinding,
    create_controller,
)

from .visualizer import (
    TimelineVisualizer,
    TimelineVisualizerConfig,
)

__all__ = [
    # Recording
    "ExecutionRecorder",
    "RecordingSession",
    "RecordingMetadata",
    "RecordingContext",
    "record_execution",
    # Playback
    "TimelinePlayer",
    "PlaybackState",
    "PlaybackEvent",
    "PlaybackPosition",
    # Controls
    "TimelineController",
    "ControlCommand",
    "ControlBinding",
    "create_controller",
    # Visualization
    "TimelineVisualizer",
    "TimelineVisualizerConfig",
]
