"""
Code Organism Tracer

Dynamic execution tracing for visualizing code as it runs.
"""

from .instrumenter import (
    Tracer,
    TraceContext,
    TraceEvent,
    trace_execution,
    trace_function,
)

__all__ = [
    "Tracer",
    "TraceContext",
    "TraceEvent",
    "trace_execution",
    "trace_function",
]
