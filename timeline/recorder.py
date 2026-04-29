"""
CODE ORGANISM: EXECUTION RECORDER

Records execution traces for later playback.
Like a flight recorder for code - capturing every
moment of the organism's life.
"""

from __future__ import annotations
import json
import time
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Any, Callable
import gzip

from ..model.organism import Organism, ExecutionFrame, ExecutionTrace
from ..tracer.instrumenter import Tracer


@dataclass
class RecordingMetadata:
    """Metadata about a recording session."""
    session_id: str
    organism_id: str
    organism_name: str
    started_at: str
    ended_at: Optional[str] = None
    total_frames: int = 0
    duration_ns: int = 0
    file_count: int = 0
    node_count: int = 0
    edge_count: int = 0

    # Playback hints
    avg_frame_interval_ns: int = 0
    min_frame_interval_ns: int = 0
    max_frame_interval_ns: int = 0


@dataclass
class RecordingSession:
    """A complete recording session."""
    metadata: RecordingMetadata
    organism_snapshot: dict  # Serialized organism state
    frames: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "metadata": asdict(self.metadata),
            "organism": self.organism_snapshot,
            "frames": self.frames,
        }

    @classmethod
    def from_dict(cls, data: dict) -> RecordingSession:
        metadata = RecordingMetadata(**data["metadata"])
        return cls(
            metadata=metadata,
            organism_snapshot=data["organism"],
            frames=data["frames"],
        )

    def save(self, filepath: Path, compress: bool = True) -> None:
        """Save recording to file."""
        data = json.dumps(self.to_dict(), indent=2)

        if compress:
            filepath = filepath.with_suffix(".corg.gz")
            with gzip.open(filepath, "wt", encoding="utf-8") as f:
                f.write(data)
        else:
            filepath = filepath.with_suffix(".corg")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(data)

    @classmethod
    def load(cls, filepath: Path) -> RecordingSession:
        """Load recording from file."""
        if filepath.suffix == ".gz":
            with gzip.open(filepath, "rt", encoding="utf-8") as f:
                data = json.load(f)
        else:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)

        return cls.from_dict(data)


class ExecutionRecorder:
    """
    Records code execution for later playback.

    Think of this as a video recorder for the organism's
    internal processes - we capture every heartbeat,
    every signal, every flow of data.
    """

    def __init__(self, organism: Organism):
        self.organism = organism
        self.session: Optional[RecordingSession] = None
        self.tracer: Optional[Tracer] = None
        self._recording = False
        self._lock = threading.Lock()
        self._frame_callback: Optional[Callable[[ExecutionFrame], None]] = None

    def start(self, session_id: Optional[str] = None) -> RecordingSession:
        """Start recording execution."""
        if self._recording:
            raise RuntimeError("Already recording")

        # Generate session ID if not provided
        if session_id is None:
            session_id = f"rec_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

        # Create metadata
        metadata = RecordingMetadata(
            session_id=session_id,
            organism_id=self.organism.id,
            organism_name=self.organism.name,
            started_at=datetime.now(timezone.utc).isoformat(),
            file_count=len(set(n.position.file for n in self.organism.nodes.values() if n.position)),
            node_count=len(self.organism.nodes),
            edge_count=len(self.organism.edges),
        )

        # Snapshot organism state
        organism_snapshot = self.organism.to_dict()

        # Create session
        self.session = RecordingSession(
            metadata=metadata,
            organism_snapshot=organism_snapshot,
        )

        # Start tracer
        self.tracer = Tracer(self.organism)
        self.tracer.start(session_id)

        # Hook into frame recording
        original_record = self.organism.record_frame

        def hooked_record(frame: ExecutionFrame) -> None:
            original_record(frame)
            self._on_frame(frame)

        self.organism.record_frame = hooked_record
        self._original_record = original_record

        self._recording = True
        return self.session

    def stop(self) -> RecordingSession:
        """Stop recording and return the session."""
        if not self._recording:
            raise RuntimeError("Not recording")

        self._recording = False

        # Stop tracer
        if self.tracer:
            self.tracer.stop()

        # Restore original record function
        self.organism.record_frame = self._original_record

        # Finalize metadata
        if self.session:
            self.session.metadata.ended_at = datetime.now(timezone.utc).isoformat()
            self.session.metadata.total_frames = len(self.session.frames)

            # Calculate timing stats
            if len(self.session.frames) >= 2:
                intervals = []
                for i in range(1, len(self.session.frames)):
                    prev_ns = self.session.frames[i-1].get("elapsed_ns", 0)
                    curr_ns = self.session.frames[i].get("elapsed_ns", 0)
                    intervals.append(curr_ns - prev_ns)

                if intervals:
                    self.session.metadata.avg_frame_interval_ns = sum(intervals) // len(intervals)
                    self.session.metadata.min_frame_interval_ns = min(intervals)
                    self.session.metadata.max_frame_interval_ns = max(intervals)

            if self.session.frames:
                self.session.metadata.duration_ns = self.session.frames[-1].get("elapsed_ns", 0)

        return self.session

    def _on_frame(self, frame: ExecutionFrame) -> None:
        """Handle a new execution frame."""
        with self._lock:
            if self.session:
                # Serialize frame
                frame_data = {
                    "timestamp": frame.timestamp.isoformat(),
                    "frame_index": frame.frame_index,
                    "node_id": frame.node_id,
                    "event_type": frame.event_type,
                    "event_data": frame.event_data,
                    "local_vars": frame.local_vars,
                    "call_stack": frame.call_stack,
                    "elapsed_ns": frame.elapsed_ns,
                }
                self.session.frames.append(frame_data)

                # Notify callback
                if self._frame_callback:
                    self._frame_callback(frame)

    def on_frame(self, callback: Callable[[ExecutionFrame], None]) -> None:
        """Register a callback for each frame."""
        self._frame_callback = callback

    @property
    def is_recording(self) -> bool:
        return self._recording

    @property
    def frame_count(self) -> int:
        if self.session:
            return len(self.session.frames)
        return 0


class RecordingContext:
    """Context manager for recording execution."""

    def __init__(self, organism: Organism, session_id: Optional[str] = None):
        self.organism = organism
        self.session_id = session_id
        self.recorder: Optional[ExecutionRecorder] = None
        self.session: Optional[RecordingSession] = None

    def __enter__(self) -> RecordingSession:
        self.recorder = ExecutionRecorder(self.organism)
        self.session = self.recorder.start(self.session_id)
        return self.session

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.recorder:
            self.recorder.stop()


def record_execution(organism: Organism, session_id: Optional[str] = None) -> RecordingContext:
    """
    Context manager for recording execution.

    Usage:
        with record_execution(organism) as session:
            # Your code here
            my_function()

        # session now contains all recorded frames
        session.save(Path("my_recording.corg.gz"))
    """
    return RecordingContext(organism, session_id)
