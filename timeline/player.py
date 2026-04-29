# SPDX-License-Identifier: Apache-2.0
"""
CODE ORGANISM: TIMELINE PLAYER

Plays back recorded execution traces with full control
over playback speed, seeking, and stepping.

Like watching a nature documentary about the organism's
internal life - you can pause, rewind, slow down to see
every detail.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path

from ..model.organism import Organism
from .recorder import RecordingSession


class PlaybackState(Enum):
    """Current state of playback."""
    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"
    SEEKING = "seeking"
    FINISHED = "finished"


@dataclass
class PlaybackEvent:
    """An event during playback."""
    event_type: str  # "frame", "state_change", "seek", "speed_change"
    timestamp: datetime
    data: dict = field(default_factory=dict)


@dataclass
class PlaybackPosition:
    """Current position in the timeline."""
    frame_index: int
    elapsed_ns: int
    progress: float  # 0.0 to 1.0
    timestamp: str | None = None


class TimelinePlayer:
    """
    Plays back recorded execution traces.

    Features:
    - Variable speed playback (0.1x to 100x)
    - Pause/resume
    - Seek to any frame
    - Step forward/backward
    - Frame-by-frame mode
    - Loop playback
    """

    def __init__(self, session: RecordingSession):
        self.session = session
        self._state = PlaybackState.STOPPED
        self._current_frame = 0
        self._speed = 1.0
        self._loop = False

        # Threading
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._pause_event.set()  # Not paused initially

        # Callbacks
        self._on_frame: Callable[[dict, PlaybackPosition], None] | None = None
        self._on_state_change: Callable[[PlaybackState], None] | None = None
        self._on_event: Callable[[PlaybackEvent], None] | None = None

        # Reconstructed organism (for state at each frame)
        self._organism: Organism | None = None

    @classmethod
    def from_file(cls, filepath: Path) -> TimelinePlayer:
        """Load a player from a recording file."""
        session = RecordingSession.load(filepath)
        return cls(session)

    # =========================================================================
    # PROPERTIES
    # =========================================================================

    @property
    def state(self) -> PlaybackState:
        return self._state

    @property
    def current_frame(self) -> int:
        return self._current_frame

    @property
    def total_frames(self) -> int:
        return len(self.session.frames)

    @property
    def speed(self) -> float:
        return self._speed

    @speed.setter
    def speed(self, value: float) -> None:
        self._speed = max(0.01, min(100.0, value))
        self._emit_event("speed_change", {"speed": self._speed})

    @property
    def loop(self) -> bool:
        return self._loop

    @loop.setter
    def loop(self, value: bool) -> None:
        self._loop = value

    @property
    def position(self) -> PlaybackPosition:
        """Get current playback position."""
        if not self.session.frames:
            return PlaybackPosition(0, 0, 0.0)

        frame = self.session.frames[self._current_frame] if self._current_frame < len(self.session.frames) else None
        elapsed_ns = frame.get("elapsed_ns", 0) if frame else 0

        return PlaybackPosition(
            frame_index=self._current_frame,
            elapsed_ns=elapsed_ns,
            progress=self._current_frame / max(1, self.total_frames - 1),
            timestamp=frame.get("timestamp") if frame else None,
        )

    # =========================================================================
    # PLAYBACK CONTROL
    # =========================================================================

    def play(self) -> None:
        """Start or resume playback."""
        if self._state == PlaybackState.FINISHED:
            self._current_frame = 0

        if self._state in (PlaybackState.STOPPED, PlaybackState.PAUSED, PlaybackState.FINISHED):
            self._set_state(PlaybackState.PLAYING)
            self._pause_event.set()

            if self._thread is None or not self._thread.is_alive():
                self._stop_event.clear()
                self._thread = threading.Thread(target=self._playback_loop, daemon=True)
                self._thread.start()

    def pause(self) -> None:
        """Pause playback."""
        if self._state == PlaybackState.PLAYING:
            self._pause_event.clear()
            self._set_state(PlaybackState.PAUSED)

    def stop(self) -> None:
        """Stop playback and reset to beginning."""
        self._stop_event.set()
        self._pause_event.set()

        if self._thread:
            self._thread.join(timeout=1.0)
            self._thread = None

        self._current_frame = 0
        self._set_state(PlaybackState.STOPPED)

    def toggle_play_pause(self) -> None:
        """Toggle between play and pause."""
        if self._state == PlaybackState.PLAYING:
            self.pause()
        else:
            self.play()

    # =========================================================================
    # SEEKING
    # =========================================================================

    def seek_to_frame(self, frame_index: int) -> None:
        """Seek to a specific frame."""
        was_playing = self._state == PlaybackState.PLAYING

        if was_playing:
            self._pause_event.clear()

        with self._lock:
            self._current_frame = max(0, min(frame_index, self.total_frames - 1))
            self._emit_current_frame()

        self._emit_event("seek", {"frame": self._current_frame})

        if was_playing:
            self._pause_event.set()

    def seek_to_progress(self, progress: float) -> None:
        """Seek to a position by progress (0.0 to 1.0)."""
        progress = max(0.0, min(1.0, progress))
        frame = int(progress * (self.total_frames - 1))
        self.seek_to_frame(frame)

    def seek_to_time_ns(self, time_ns: int) -> None:
        """Seek to a position by elapsed time in nanoseconds."""
        # Binary search for the frame
        left, right = 0, self.total_frames - 1

        while left < right:
            mid = (left + right) // 2
            frame_time = self.session.frames[mid].get("elapsed_ns", 0)

            if frame_time < time_ns:
                left = mid + 1
            else:
                right = mid

        self.seek_to_frame(left)

    # =========================================================================
    # STEPPING
    # =========================================================================

    def step_forward(self, count: int = 1) -> None:
        """Step forward by count frames."""
        if self._state == PlaybackState.PLAYING:
            self.pause()

        with self._lock:
            new_frame = min(self._current_frame + count, self.total_frames - 1)
            if new_frame != self._current_frame:
                self._current_frame = new_frame
                self._emit_current_frame()

    def step_backward(self, count: int = 1) -> None:
        """Step backward by count frames."""
        if self._state == PlaybackState.PLAYING:
            self.pause()

        with self._lock:
            new_frame = max(self._current_frame - count, 0)
            if new_frame != self._current_frame:
                self._current_frame = new_frame
                self._emit_current_frame()

    def step_to_next_call(self) -> None:
        """Step to the next function call event."""
        for i in range(self._current_frame + 1, self.total_frames):
            if self.session.frames[i].get("event_type") == "call":
                self.seek_to_frame(i)
                return

    def step_to_next_return(self) -> None:
        """Step to the next function return event."""
        for i in range(self._current_frame + 1, self.total_frames):
            if self.session.frames[i].get("event_type") == "return":
                self.seek_to_frame(i)
                return

    def step_to_next_exception(self) -> None:
        """Step to the next exception event."""
        for i in range(self._current_frame + 1, self.total_frames):
            if self.session.frames[i].get("event_type") == "exception":
                self.seek_to_frame(i)
                return

    # =========================================================================
    # CALLBACKS
    # =========================================================================

    def on_frame(self, callback: Callable[[dict, PlaybackPosition], None]) -> None:
        """Register callback for each frame during playback."""
        self._on_frame = callback

    def on_state_change(self, callback: Callable[[PlaybackState], None]) -> None:
        """Register callback for state changes."""
        self._on_state_change = callback

    def on_event(self, callback: Callable[[PlaybackEvent], None]) -> None:
        """Register callback for playback events."""
        self._on_event = callback

    # =========================================================================
    # FRAME ACCESS
    # =========================================================================

    def get_frame(self, index: int) -> dict | None:
        """Get frame data by index."""
        if 0 <= index < self.total_frames:
            return self.session.frames[index]
        return None

    def get_current_frame_data(self) -> dict | None:
        """Get current frame data."""
        return self.get_frame(self._current_frame)

    def get_frames_in_range(self, start: int, end: int) -> list[dict]:
        """Get frames in a range."""
        return self.session.frames[max(0, start):min(end, self.total_frames)]

    def find_frames_by_node(self, node_id: str) -> list[int]:
        """Find all frame indices for a specific node."""
        return [
            i for i, frame in enumerate(self.session.frames)
            if frame.get("node_id") == node_id
        ]

    def find_frames_by_event_type(self, event_type: str) -> list[int]:
        """Find all frame indices for a specific event type."""
        return [
            i for i, frame in enumerate(self.session.frames)
            if frame.get("event_type") == event_type
        ]

    # =========================================================================
    # INTERNAL
    # =========================================================================

    def _playback_loop(self) -> None:
        """Main playback loop running in a thread."""
        last_frame_time = time.perf_counter_ns()

        while not self._stop_event.is_set():
            # Wait if paused
            self._pause_event.wait()

            if self._stop_event.is_set():
                break

            with self._lock:
                if self._current_frame >= self.total_frames:
                    if self._loop:
                        self._current_frame = 0
                    else:
                        self._set_state(PlaybackState.FINISHED)
                        break

                current = self._current_frame
                frame = self.session.frames[current]

            # Calculate delay based on frame timing and playback speed
            if current > 0 and current < self.total_frames:
                prev_frame = self.session.frames[current - 1]
                frame_interval_ns = frame.get("elapsed_ns", 0) - prev_frame.get("elapsed_ns", 0)

                # Apply speed multiplier
                target_delay_ns = frame_interval_ns / self._speed if self._speed > 0 else 0

                # Calculate actual delay
                elapsed = time.perf_counter_ns() - last_frame_time
                delay_ns = max(0, target_delay_ns - elapsed)

                if delay_ns > 0:
                    time.sleep(delay_ns / 1_000_000_000)

            # Emit frame
            self._emit_current_frame()
            last_frame_time = time.perf_counter_ns()

            # Advance
            with self._lock:
                self._current_frame += 1

    def _set_state(self, state: PlaybackState) -> None:
        """Set playback state and notify."""
        if state != self._state:
            self._state = state
            if self._on_state_change:
                self._on_state_change(state)
            self._emit_event("state_change", {"state": state.value})

    def _emit_current_frame(self) -> None:
        """Emit the current frame to callback."""
        if self._on_frame and self._current_frame < self.total_frames:
            frame = self.session.frames[self._current_frame]
            position = self.position
            self._on_frame(frame, position)

    def _emit_event(self, event_type: str, data: dict) -> None:
        """Emit a playback event."""
        if self._on_event:
            event = PlaybackEvent(
                event_type=event_type,
                timestamp=datetime.now(timezone.utc),
                data=data,
            )
            self._on_event(event)
