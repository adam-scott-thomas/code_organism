# SPDX-License-Identifier: Apache-2.0
"""
Code Organism Tracer

Dynamic execution tracing for visualizing code as it runs.
"""

from .instrumenter import (
    TraceContext,
    TraceEvent,
    Tracer,
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
