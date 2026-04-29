# SPDX-License-Identifier: Apache-2.0
"""
CODE ORGANISM: EXECUTION TRACER

Instruments Python code to record execution flow.
This is the "bloodstream" - we're watching data flow
through the organism in real time.
"""

from __future__ import annotations
import sys
import time
import threading
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Any, Callable
from pathlib import Path
import traceback

from ..model.organism import Organism, ExecutionFrame, ExecutionTrace
from ..model.nodes import OrganismNode, NodeType


@dataclass
class TraceEvent:
    """A single trace event."""
    timestamp: datetime
    elapsed_ns: int
    event_type: str  # "call", "return", "exception", "line"
    filename: str
    lineno: int
    function_name: str
    locals: dict = field(default_factory=dict)
    return_value: Any = None
    exception: Optional[Exception] = None


class Tracer:
    """
    Traces execution of Python code and records events.

    This is like attaching a microscope to watch blood cells
    flowing through the circulatory system. We see every
    function call, every return, every exception.
    """

    def __init__(self, organism: Organism):
        self.organism = organism
        self.trace: Optional[ExecutionTrace] = None
        self._start_time_ns: int = 0
        self._call_stack: list[str] = []
        self._frame_index: int = 0
        self._active = False
        self._lock = threading.Lock()

        # Files we're tracing (to avoid tracing stdlib)
        self._trace_files: set[str] = set()
        for node in organism.nodes.values():
            if node.position:
                self._trace_files.add(node.position.file)

    def start(self, trace_id: Optional[str] = None) -> ExecutionTrace:
        """Start tracing execution."""
        self.trace = self.organism.start_trace(trace_id)
        self._start_time_ns = time.perf_counter_ns()
        self._call_stack = []
        self._frame_index = 0
        self._active = True

        # Install the trace function
        sys.settrace(self._trace_function)
        threading.settrace(self._trace_function)

        return self.trace

    def stop(self) -> Optional[ExecutionTrace]:
        """Stop tracing and return the trace."""
        self._active = False
        sys.settrace(None)
        threading.settrace(None)

        return self.organism.stop_trace()

    def _trace_function(self, frame, event: str, arg) -> Optional[Callable]:
        """
        The trace function called by Python for each event.

        This is called for every line of code executed!
        We need to be fast and selective.
        """
        if not self._active:
            return None

        filename = frame.f_code.co_filename

        # Only trace files in our organism
        if filename not in self._trace_files:
            return self._trace_function

        # Handle different event types
        if event == "call":
            self._on_call(frame, arg)
        elif event == "return":
            self._on_return(frame, arg)
        elif event == "exception":
            self._on_exception(frame, arg)
        # Note: 'line' events are too noisy, we skip them

        return self._trace_function

    def _on_call(self, frame, arg) -> None:
        """Handle function call event."""
        func_name = frame.f_code.co_name
        filename = frame.f_code.co_filename
        lineno = frame.f_lineno

        # Build qualified name
        qualified_name = self._get_qualified_name(frame)

        # Find the node ID
        node_id = self._find_node_id(qualified_name, filename, lineno)

        with self._lock:
            self._call_stack.append(node_id or qualified_name)

            # Capture local variables (be careful with large objects)
            local_vars = {}
            for name, value in frame.f_locals.items():
                if not name.startswith("_"):
                    local_vars[name] = self._safe_repr(value)

            exec_frame = ExecutionFrame(
                timestamp=datetime.now(timezone.utc),
                frame_index=self._frame_index,
                node_id=node_id or "",
                event_type="call",
                event_data={
                    "function": func_name,
                    "qualified_name": qualified_name,
                    "filename": filename,
                    "lineno": lineno,
                },
                local_vars=local_vars,
                call_stack=self._call_stack.copy(),
                elapsed_ns=time.perf_counter_ns() - self._start_time_ns,
            )

            self.organism.record_frame(exec_frame)
            self._frame_index += 1

    def _on_return(self, frame, arg) -> None:
        """Handle function return event."""
        func_name = frame.f_code.co_name
        filename = frame.f_code.co_filename
        lineno = frame.f_lineno

        qualified_name = self._get_qualified_name(frame)
        node_id = self._find_node_id(qualified_name, filename, lineno)

        with self._lock:
            if self._call_stack:
                self._call_stack.pop()

            exec_frame = ExecutionFrame(
                timestamp=datetime.now(timezone.utc),
                frame_index=self._frame_index,
                node_id=node_id or "",
                event_type="return",
                event_data={
                    "function": func_name,
                    "return_value": self._safe_repr(arg),
                    "return_type": type(arg).__name__,
                },
                call_stack=self._call_stack.copy(),
                elapsed_ns=time.perf_counter_ns() - self._start_time_ns,
            )

            self.organism.record_frame(exec_frame)
            self._frame_index += 1

            # Update node metrics
            if node_id:
                node = self.organism.get_node(node_id)
                if node:
                    node.metrics.call_count += 1

    def _on_exception(self, frame, arg) -> None:
        """Handle exception event."""
        exc_type, exc_value, exc_tb = arg
        func_name = frame.f_code.co_name
        filename = frame.f_code.co_filename
        lineno = frame.f_lineno

        qualified_name = self._get_qualified_name(frame)
        node_id = self._find_node_id(qualified_name, filename, lineno)

        with self._lock:
            exec_frame = ExecutionFrame(
                timestamp=datetime.now(timezone.utc),
                frame_index=self._frame_index,
                node_id=node_id or "",
                event_type="exception",
                event_data={
                    "function": func_name,
                    "exception_type": exc_type.__name__,
                    "exception_message": str(exc_value),
                    "traceback": "".join(traceback.format_exception(exc_type, exc_value, exc_tb)),
                },
                call_stack=self._call_stack.copy(),
                elapsed_ns=time.perf_counter_ns() - self._start_time_ns,
            )

            self.organism.record_frame(exec_frame)
            self._frame_index += 1

            # Update node metrics
            if node_id:
                node = self.organism.get_node(node_id)
                if node:
                    node.metrics.exceptions_raised += 1

    def _get_qualified_name(self, frame) -> str:
        """Build a qualified name for a frame."""
        parts = []

        # Module name from filename
        filename = frame.f_code.co_filename
        path = Path(filename)
        parts.append(path.stem)

        # Class name if in a method
        if "self" in frame.f_locals:
            obj = frame.f_locals["self"]
            parts.append(type(obj).__name__)
        elif "cls" in frame.f_locals:
            cls = frame.f_locals["cls"]
            parts.append(cls.__name__)

        # Function name
        parts.append(frame.f_code.co_name)

        return ".".join(parts)

    def _find_node_id(self, qualified_name: str, filename: str, lineno: int) -> Optional[str]:
        """Find the node ID for a given code location."""
        # Try by qualified name first
        for node in self.organism.nodes.values():
            if node.qualified_name == qualified_name:
                return node.id

        # Try by file and line
        for node in self.organism.get_nodes_by_file(filename):
            if node.position and node.position.line <= lineno:
                if node.position.end_line is None or node.position.end_line >= lineno:
                    return node.id

        return None

    def _safe_repr(self, value: Any, max_len: int = 100) -> str:
        """Safely get a string representation of a value."""
        try:
            r = repr(value)
            if len(r) > max_len:
                return r[:max_len] + "..."
            return r
        except Exception:
            return f"<{type(value).__name__}>"


class TraceContext:
    """Context manager for tracing code execution."""

    def __init__(self, organism: Organism, trace_id: Optional[str] = None):
        self.organism = organism
        self.trace_id = trace_id
        self.tracer: Optional[Tracer] = None
        self.trace: Optional[ExecutionTrace] = None

    def __enter__(self) -> ExecutionTrace:
        self.tracer = Tracer(self.organism)
        self.trace = self.tracer.start(self.trace_id)
        return self.trace

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.tracer:
            self.tracer.stop()


def trace_execution(organism: Organism, trace_id: Optional[str] = None) -> TraceContext:
    """
    Context manager for tracing code execution.

    Usage:
        with trace_execution(organism) as trace:
            # Your code here
            my_function()

        # trace now contains all execution frames
    """
    return TraceContext(organism, trace_id)


def trace_function(organism: Organism, func: Callable, *args, **kwargs) -> tuple[Any, ExecutionTrace]:
    """
    Trace a single function call.

    Returns:
        Tuple of (return_value, trace)
    """
    tracer = Tracer(organism)
    trace = tracer.start()

    try:
        result = func(*args, **kwargs)
    finally:
        tracer.stop()

    return result, trace
