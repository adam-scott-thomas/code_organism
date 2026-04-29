# SPDX-License-Identifier: Apache-2.0
"""
CODE ORGANISM: TIMELINE CONTROLS

Provides a control interface for timeline playback.
These controls can be bound to keyboard shortcuts,
UI buttons, or API endpoints.
"""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Callable, Any

from .player import TimelinePlayer, PlaybackState


class ControlCommand(Enum):
    """Available control commands."""
    PLAY = "play"
    PAUSE = "pause"
    STOP = "stop"
    TOGGLE = "toggle"
    STEP_FORWARD = "step_forward"
    STEP_BACKWARD = "step_backward"
    STEP_FORWARD_10 = "step_forward_10"
    STEP_BACKWARD_10 = "step_backward_10"
    STEP_TO_CALL = "step_to_call"
    STEP_TO_RETURN = "step_to_return"
    STEP_TO_EXCEPTION = "step_to_exception"
    SEEK_START = "seek_start"
    SEEK_END = "seek_end"
    SPEED_UP = "speed_up"
    SPEED_DOWN = "speed_down"
    SPEED_NORMAL = "speed_normal"
    TOGGLE_LOOP = "toggle_loop"


@dataclass
class ControlBinding:
    """A keyboard/action binding."""
    key: str
    command: ControlCommand
    description: str


class TimelineController:
    """
    Central controller for timeline playback.

    Maps commands to player actions and provides
    a clean interface for UI/keyboard bindings.
    """

    # Default keyboard bindings
    DEFAULT_BINDINGS = [
        ControlBinding("Space", ControlCommand.TOGGLE, "Play/Pause"),
        ControlBinding("s", ControlCommand.STOP, "Stop"),
        ControlBinding("ArrowRight", ControlCommand.STEP_FORWARD, "Step forward"),
        ControlBinding("ArrowLeft", ControlCommand.STEP_BACKWARD, "Step backward"),
        ControlBinding("Shift+ArrowRight", ControlCommand.STEP_FORWARD_10, "Step forward 10"),
        ControlBinding("Shift+ArrowLeft", ControlCommand.STEP_BACKWARD_10, "Step backward 10"),
        ControlBinding("c", ControlCommand.STEP_TO_CALL, "Next call"),
        ControlBinding("r", ControlCommand.STEP_TO_RETURN, "Next return"),
        ControlBinding("e", ControlCommand.STEP_TO_EXCEPTION, "Next exception"),
        ControlBinding("Home", ControlCommand.SEEK_START, "Go to start"),
        ControlBinding("End", ControlCommand.SEEK_END, "Go to end"),
        ControlBinding("+", ControlCommand.SPEED_UP, "Speed up"),
        ControlBinding("-", ControlCommand.SPEED_DOWN, "Speed down"),
        ControlBinding("=", ControlCommand.SPEED_NORMAL, "Normal speed"),
        ControlBinding("l", ControlCommand.TOGGLE_LOOP, "Toggle loop"),
    ]

    # Speed presets
    SPEED_PRESETS = [0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 10.0, 50.0]

    def __init__(self, player: TimelinePlayer):
        self.player = player
        self._speed_preset_index = 3  # 1.0x
        self._bindings = {b.key: b.command for b in self.DEFAULT_BINDINGS}
        self._command_callbacks: dict[ControlCommand, list[Callable]] = {}

    def execute(self, command: ControlCommand) -> None:
        """Execute a control command."""
        handler = self._get_handler(command)
        if handler:
            handler()

        # Notify callbacks
        callbacks = self._command_callbacks.get(command, [])
        for callback in callbacks:
            callback()

    def handle_key(self, key: str) -> bool:
        """Handle a keyboard event. Returns True if handled."""
        command = self._bindings.get(key)
        if command:
            self.execute(command)
            return True
        return False

    def on_command(self, command: ControlCommand, callback: Callable) -> None:
        """Register a callback for when a command is executed."""
        if command not in self._command_callbacks:
            self._command_callbacks[command] = []
        self._command_callbacks[command].append(callback)

    def set_binding(self, key: str, command: ControlCommand) -> None:
        """Set or override a key binding."""
        self._bindings[key] = command

    def get_bindings(self) -> list[ControlBinding]:
        """Get all current bindings."""
        return [
            ControlBinding(key, cmd, self._get_description(cmd))
            for key, cmd in self._bindings.items()
        ]

    def _get_handler(self, command: ControlCommand) -> Optional[Callable]:
        """Get the handler function for a command."""
        handlers = {
            ControlCommand.PLAY: self.player.play,
            ControlCommand.PAUSE: self.player.pause,
            ControlCommand.STOP: self.player.stop,
            ControlCommand.TOGGLE: self.player.toggle_play_pause,
            ControlCommand.STEP_FORWARD: self.player.step_forward,
            ControlCommand.STEP_BACKWARD: self.player.step_backward,
            ControlCommand.STEP_FORWARD_10: lambda: self.player.step_forward(10),
            ControlCommand.STEP_BACKWARD_10: lambda: self.player.step_backward(10),
            ControlCommand.STEP_TO_CALL: self.player.step_to_next_call,
            ControlCommand.STEP_TO_RETURN: self.player.step_to_next_return,
            ControlCommand.STEP_TO_EXCEPTION: self.player.step_to_next_exception,
            ControlCommand.SEEK_START: lambda: self.player.seek_to_frame(0),
            ControlCommand.SEEK_END: lambda: self.player.seek_to_frame(self.player.total_frames - 1),
            ControlCommand.SPEED_UP: self._speed_up,
            ControlCommand.SPEED_DOWN: self._speed_down,
            ControlCommand.SPEED_NORMAL: self._speed_normal,
            ControlCommand.TOGGLE_LOOP: self._toggle_loop,
        }
        return handlers.get(command)

    def _speed_up(self) -> None:
        """Increase playback speed."""
        if self._speed_preset_index < len(self.SPEED_PRESETS) - 1:
            self._speed_preset_index += 1
            self.player.speed = self.SPEED_PRESETS[self._speed_preset_index]

    def _speed_down(self) -> None:
        """Decrease playback speed."""
        if self._speed_preset_index > 0:
            self._speed_preset_index -= 1
            self.player.speed = self.SPEED_PRESETS[self._speed_preset_index]

    def _speed_normal(self) -> None:
        """Reset to normal speed."""
        self._speed_preset_index = 3  # 1.0x
        self.player.speed = 1.0

    def _toggle_loop(self) -> None:
        """Toggle loop mode."""
        self.player.loop = not self.player.loop

    def _get_description(self, command: ControlCommand) -> str:
        """Get description for a command."""
        descriptions = {
            ControlCommand.PLAY: "Start playback",
            ControlCommand.PAUSE: "Pause playback",
            ControlCommand.STOP: "Stop and reset",
            ControlCommand.TOGGLE: "Toggle play/pause",
            ControlCommand.STEP_FORWARD: "Step forward one frame",
            ControlCommand.STEP_BACKWARD: "Step backward one frame",
            ControlCommand.STEP_FORWARD_10: "Step forward 10 frames",
            ControlCommand.STEP_BACKWARD_10: "Step backward 10 frames",
            ControlCommand.STEP_TO_CALL: "Jump to next function call",
            ControlCommand.STEP_TO_RETURN: "Jump to next return",
            ControlCommand.STEP_TO_EXCEPTION: "Jump to next exception",
            ControlCommand.SEEK_START: "Go to beginning",
            ControlCommand.SEEK_END: "Go to end",
            ControlCommand.SPEED_UP: "Increase speed",
            ControlCommand.SPEED_DOWN: "Decrease speed",
            ControlCommand.SPEED_NORMAL: "Reset to 1x speed",
            ControlCommand.TOGGLE_LOOP: "Toggle loop mode",
        }
        return descriptions.get(command, command.value)

    # =========================================================================
    # CONVENIENCE METHODS
    # =========================================================================

    @property
    def is_playing(self) -> bool:
        return self.player.state == PlaybackState.PLAYING

    @property
    def is_paused(self) -> bool:
        return self.player.state == PlaybackState.PAUSED

    @property
    def current_speed(self) -> float:
        return self.player.speed

    @property
    def current_speed_label(self) -> str:
        speed = self.player.speed
        if speed == 1.0:
            return "1x"
        elif speed < 1.0:
            return f"{speed:.2f}x"
        else:
            return f"{speed:.0f}x"

    @property
    def progress(self) -> float:
        return self.player.position.progress

    @property
    def frame_info(self) -> str:
        pos = self.player.position
        return f"{pos.frame_index + 1}/{self.player.total_frames}"

    def seek_to_percent(self, percent: float) -> None:
        """Seek to a percentage position (0-100)."""
        self.player.seek_to_progress(percent / 100.0)


def create_controller(player: TimelinePlayer) -> TimelineController:
    """Create a controller for a player."""
    return TimelineController(player)
