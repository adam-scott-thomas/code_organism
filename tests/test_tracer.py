"""Tests for tracer/instrumenter.py — execution tracing."""

from __future__ import annotations

import pytest

from Code_Organism.model.organism import Organism
from Code_Organism.tracer.instrumenter import (
    TraceContext,
    Tracer,
    trace_execution,
    trace_function,
)

# ---------------------------------------------------------------------------
# Fixture: a small organism parsed from sample_python_file
# ---------------------------------------------------------------------------


@pytest.fixture
def organism(sample_python_file):
    """A minimal organism parsed from the sample Python file."""
    return Organism.from_file(sample_python_file)


@pytest.fixture
def traceable_organism(tmp_dir):
    """An organism whose code we can actually call during tracing."""
    p = tmp_dir / "tiny.py"
    p.write_text(
        '''\
def add(a, b):
    return a + b

def boom():
    raise ValueError("nope")

class Greeter:
    def hello(self, name):
        return "hi " + name
'''
    )
    org = Organism.from_file(p)
    # Make the file importable from the test
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("tiny", p)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["tiny"] = module
    spec.loader.exec_module(module)
    return org, module


# ---------------------------------------------------------------------------
# Tracer construction
# ---------------------------------------------------------------------------


def test_tracer_init_collects_trace_files(organism):
    tracer = Tracer(organism)
    # Tracer should have indexed at least the module file
    assert len(tracer._trace_files) >= 1
    assert tracer._active is False
    assert tracer._frame_index == 0
    assert tracer._call_stack == []


def test_tracer_init_with_empty_organism():
    org = Organism("empty")
    tracer = Tracer(org)
    assert tracer._trace_files == set()


# ---------------------------------------------------------------------------
# start / stop
# ---------------------------------------------------------------------------


def test_tracer_start_returns_trace(organism):
    tracer = Tracer(organism)
    trace = tracer.start()
    try:
        assert trace is not None
        assert tracer._active is True
        assert tracer.trace is trace
    finally:
        tracer.stop()


def test_tracer_start_with_explicit_id(organism):
    tracer = Tracer(organism)
    trace = tracer.start(trace_id="my-trace-001")
    try:
        assert trace.trace_id == "my-trace-001"
    finally:
        tracer.stop()


def test_tracer_stop_clears_active(organism):
    tracer = Tracer(organism)
    tracer.start()
    tracer.stop()
    assert tracer._active is False


# ---------------------------------------------------------------------------
# Recording: real execution
# ---------------------------------------------------------------------------


def test_tracer_records_call_and_return(traceable_organism):
    org, module = traceable_organism
    tracer = Tracer(org)
    trace = tracer.start()
    try:
        module.add(2, 3)
    finally:
        tracer.stop()

    # Some frames should have been recorded; at least one call event.
    events = [f.event_type for f in trace.frames]
    assert "call" in events
    assert "return" in events


def test_tracer_records_exception(traceable_organism):
    org, module = traceable_organism
    tracer = Tracer(org)
    trace = tracer.start()
    try:
        with pytest.raises(ValueError):
            module.boom()
    finally:
        tracer.stop()

    events = [f.event_type for f in trace.frames]
    assert "exception" in events


def test_tracer_records_method_call(traceable_organism):
    org, module = traceable_organism
    tracer = Tracer(org)
    trace = tracer.start()
    try:
        g = module.Greeter()
        result = g.hello("world")
    finally:
        tracer.stop()

    assert result == "hi world"
    # At least one frame should reference the Greeter class
    qnames = [
        f.event_data.get("qualified_name", "")
        for f in trace.frames
        if f.event_type == "call"
    ]
    assert any("Greeter" in q for q in qnames)


# ---------------------------------------------------------------------------
# TraceContext / trace_execution
# ---------------------------------------------------------------------------


def test_trace_context_manager(traceable_organism):
    org, module = traceable_organism
    with trace_execution(org) as trace:
        module.add(1, 1)
    assert len(trace.frames) > 0


def test_trace_context_with_explicit_id(traceable_organism):
    org, module = traceable_organism
    ctx = TraceContext(org, trace_id="ctx-test")
    with ctx as trace:
        module.add(0, 0)
    assert trace.trace_id == "ctx-test"


def test_trace_context_exit_handles_no_tracer(organism):
    """__exit__ must be safe even if __enter__ never ran."""
    ctx = TraceContext(organism)
    ctx.__exit__(None, None, None)  # no-op, must not raise


# ---------------------------------------------------------------------------
# trace_function helper
# ---------------------------------------------------------------------------


def test_trace_function_returns_value_and_trace(traceable_organism):
    org, module = traceable_organism
    result, trace = trace_function(org, module.add, 4, 5)
    assert result == 9
    assert len(trace.frames) > 0


def test_trace_function_propagates_exception(traceable_organism):
    org, module = traceable_organism
    with pytest.raises(ValueError):
        trace_function(org, module.boom)


# ---------------------------------------------------------------------------
# _safe_repr
# ---------------------------------------------------------------------------


def test_safe_repr_simple_values(organism):
    tracer = Tracer(organism)
    assert tracer._safe_repr(42) == "42"
    assert tracer._safe_repr("hello") == "'hello'"
    assert tracer._safe_repr(None) == "None"


def test_safe_repr_truncates_long(organism):
    tracer = Tracer(organism)
    long_string = "x" * 500
    out = tracer._safe_repr(long_string, max_len=50)
    assert out.endswith("...")
    assert len(out) == 53  # 50 chars + "..."


def test_safe_repr_handles_repr_failure(organism):
    """If repr() raises, _safe_repr returns a typename fallback."""
    tracer = Tracer(organism)

    class Bad:
        def __repr__(self) -> str:
            raise RuntimeError("nope")

    out = tracer._safe_repr(Bad())
    assert "Bad" in out


# ---------------------------------------------------------------------------
# _get_qualified_name
# ---------------------------------------------------------------------------


def test_get_qualified_name_for_method(organism):
    import sys

    tracer = Tracer(organism)
    captured = {}

    class Holder:
        def capture(self):
            captured["frame"] = sys._getframe()

    Holder().capture()
    qname = tracer._get_qualified_name(captured["frame"])
    assert "Holder" in qname
    assert qname.endswith(".capture")


def test_get_qualified_name_for_classmethod(organism):
    """cls in f_locals branch."""
    import sys

    tracer = Tracer(organism)
    captured = {}

    class Holder:
        @classmethod
        def cm(cls):
            captured["frame"] = sys._getframe()

    Holder.cm()
    qname = tracer._get_qualified_name(captured["frame"])
    assert "Holder" in qname
    assert qname.endswith(".cm")


def test_get_qualified_name_for_module_function(organism):
    """No self / cls — just module + function."""
    import sys

    tracer = Tracer(organism)
    captured = {}

    def free():
        captured["frame"] = sys._getframe()

    free()
    qname = tracer._get_qualified_name(captured["frame"])
    assert qname.endswith(".free")


# ---------------------------------------------------------------------------
# _find_node_id
# ---------------------------------------------------------------------------


def test_find_node_id_by_qualified_name(organism):
    tracer = Tracer(organism)

    # Pick the first node with a qualified_name from the parsed sample.
    target = next(
        n for n in organism.nodes.values() if n.qualified_name and n.position
    )
    found = tracer._find_node_id(target.qualified_name, target.position.file, target.position.line)
    assert found == target.id


def test_find_node_id_returns_none_when_unknown(organism):
    tracer = Tracer(organism)
    found = tracer._find_node_id("nonsense.qname", "/no/such/file.py", 1)
    assert found is None
