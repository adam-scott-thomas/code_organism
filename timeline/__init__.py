# SPDX-License-Identifier: Apache-2.0
"""
Code Organism Timeline & Playback

Controls for recording, replaying, and navigating execution traces.
"""

from .controls import (
    ControlBinding,
    ControlCommand,
    TimelineController,
    create_controller,
)
from .player import (
    PlaybackEvent,
    PlaybackPosition,
    PlaybackState,
    TimelinePlayer,
)
from .recorder import (
    ExecutionRecorder,
    RecordingContext,
    RecordingMetadata,
    RecordingSession,
    record_execution,
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
