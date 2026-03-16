"""Tests for the Code_Organism MCP server."""
import json
from pathlib import Path

import pytest


# -----------------------------------------------------------------------
# Import tests
# -----------------------------------------------------------------------

def test_server_module_imports():
    """The mcp_server module can be imported without error."""
    from Code_Organism.mcp_server import server
    assert hasattr(server, "mcp")
    assert hasattr(server, "main")


def test_fastmcp_instance():
    """The FastMCP instance is correctly configured."""
    from Code_Organism.mcp_server.server import mcp
    assert mcp is not None
    assert mcp.name == "Code_Organism"


# -----------------------------------------------------------------------
# Tool registration
# -----------------------------------------------------------------------

@pytest.mark.asyncio
async def test_tools_registered():
    """All expected tools are registered on the server."""
    from Code_Organism.mcp_server.server import mcp

    tools = await mcp.list_tools()
    tool_names = {t.name for t in tools}

    expected = {"analyze", "health", "index", "query", "impact", "communities", "hotspots", "unhealthy"}
    assert expected.issubset(tool_names), f"Missing tools: {expected - tool_names}"


@pytest.mark.asyncio
async def test_resources_registered():
    """Both resources are registered."""
    from Code_Organism.mcp_server.server import mcp

    resources = await mcp.list_resources()
    uris = {str(r.uri) for r in resources}

    assert "code-organism://status" in uris
    assert "code-organism://schema" in uris


# -----------------------------------------------------------------------
# analyze tool
# -----------------------------------------------------------------------

def test_analyze_single_file(sample_python_file):
    """analyze tool returns valid JSON for a single Python file."""
    from Code_Organism.mcp_server.server import analyze

    raw = analyze(str(sample_python_file))
    data = json.loads(raw)

    assert "error" not in data, f"Unexpected error: {data.get('error')}"
    assert "nodes" in data
    assert "edges" in data
    assert "stats" in data
    assert data["stats"]["total_nodes"] > 0
    # Should find the module, class, functions
    node_names = {n["name"] for n in data["nodes"]}
    assert "FileProcessor" in node_names
    assert "helper" in node_names


def test_analyze_directory(sample_project):
    """analyze tool works on a directory."""
    from Code_Organism.mcp_server.server import analyze

    raw = analyze(str(sample_project))
    data = json.loads(raw)

    assert "error" not in data, f"Unexpected error: {data.get('error')}"
    assert data["stats"]["total_nodes"] > 0
    assert data["stats"]["total_modules"] >= 2  # at least sample.py + utils.py


def test_analyze_nonexistent_path():
    """analyze tool returns an error for a nonexistent path."""
    from Code_Organism.mcp_server.server import analyze

    raw = analyze("/nonexistent/path/to/file.py")
    data = json.loads(raw)

    assert "error" in data
    assert "does not exist" in data["error"]


# -----------------------------------------------------------------------
# health tool
# -----------------------------------------------------------------------

def test_health_tool(sample_python_file):
    """health tool returns a health summary and per-node data."""
    from Code_Organism.mcp_server.server import health

    raw = health(str(sample_python_file))
    data = json.loads(raw)

    assert "error" not in data, f"Unexpected error: {data.get('error')}"
    assert "health_summary" in data
    assert "nodes" in data
    # health_summary should have the standard keys
    for key in ["healthy", "stressed", "inflamed", "necrotic", "cancerous"]:
        assert key in data["health_summary"]


# -----------------------------------------------------------------------
# communities tool
# -----------------------------------------------------------------------

def test_communities_tool(sample_project):
    """communities tool detects at least one community."""
    from Code_Organism.mcp_server.server import communities

    raw = communities(str(sample_project))
    data = json.loads(raw)

    assert "error" not in data, f"Unexpected error: {data.get('error')}"
    assert "communities" in data
    assert "total" in data
    # With a small multi-file project there should be at least 1 community
    assert data["total"] >= 1


# -----------------------------------------------------------------------
# index + query tools
# -----------------------------------------------------------------------

def test_index_and_query(sample_project, tmp_dir):
    """index tool persists to KuzuDB, then query tool reads from it."""
    from Code_Organism.mcp_server.server import index, query

    db_path = str(tmp_dir / "test_db")

    # Index
    raw = index(str(sample_project), db_path=db_path)
    data = json.loads(raw)
    assert "error" not in data, f"Unexpected error: {data.get('error')}"
    assert data["nodes_indexed"] > 0
    assert data["edges_indexed"] >= 0

    # Query: get all functions
    raw = query(db_path, "MATCH (f:Function) RETURN f.name AS name")
    data = json.loads(raw)
    assert "error" not in data, f"Unexpected error: {data.get('error')}"
    assert "results" in data
    names = {r["name"] for r in data["results"]}
    assert "helper" in names


def test_query_nonexistent_db():
    """query tool returns an error for a nonexistent database."""
    from Code_Organism.mcp_server.server import query

    raw = query("/nonexistent/db/path", "MATCH (n) RETURN n")
    data = json.loads(raw)

    assert "error" in data
    assert "not found" in data["error"].lower() or "Database not found" in data["error"]


# -----------------------------------------------------------------------
# hotspots tool
# -----------------------------------------------------------------------

def test_hotspots_tool(sample_project, tmp_dir):
    """hotspots tool returns complexity data from a persisted graph."""
    from Code_Organism.mcp_server.server import index, hotspots

    db_path = str(tmp_dir / "hotspots_db")
    index(str(sample_project), db_path=db_path)

    raw = hotspots(db_path, limit=5)
    data = json.loads(raw)

    assert "error" not in data, f"Unexpected error: {data.get('error')}"
    assert "hotspots" in data
    assert isinstance(data["hotspots"], list)


# -----------------------------------------------------------------------
# unhealthy tool
# -----------------------------------------------------------------------

def test_unhealthy_tool(sample_project, tmp_dir):
    """unhealthy tool returns nodes below health threshold."""
    from Code_Organism.mcp_server.server import index, unhealthy

    db_path = str(tmp_dir / "unhealthy_db")
    index(str(sample_project), db_path=db_path)

    raw = unhealthy(db_path, threshold=1.0)  # threshold 1.0 should catch everything
    data = json.loads(raw)

    assert "error" not in data, f"Unexpected error: {data.get('error')}"
    assert "unhealthy" in data
    assert isinstance(data["unhealthy"], list)


# -----------------------------------------------------------------------
# impact tool
# -----------------------------------------------------------------------

def test_impact_tool(sample_project, tmp_dir):
    """impact tool returns blast radius data."""
    from Code_Organism.mcp_server.server import index, impact

    db_path = str(tmp_dir / "impact_db")
    index(str(sample_project), db_path=db_path)

    raw = impact(db_path, target="helper", direction="upstream", depth=2)
    data = json.loads(raw)

    assert "error" not in data, f"Unexpected error: {data.get('error')}"
    assert "depth_1" in data
    assert "depth_2" in data


def test_impact_unknown_symbol(sample_project, tmp_dir):
    """impact tool returns an error for an unknown symbol."""
    from Code_Organism.mcp_server.server import index, impact

    db_path = str(tmp_dir / "impact_unknown_db")
    index(str(sample_project), db_path=db_path)

    raw = impact(db_path, target="nonexistent_function_xyz")
    data = json.loads(raw)

    assert "error" in data
    assert "not found" in data["error"].lower()


# -----------------------------------------------------------------------
# Resource content
# -----------------------------------------------------------------------

def test_resource_status_content():
    """The status resource returns valid JSON with version info."""
    from Code_Organism.mcp_server.server import resource_status

    raw = resource_status()
    data = json.loads(raw)

    assert data["name"] == "Code_Organism"
    assert "version" in data
    assert "capabilities" in data
    assert "tools" in data["capabilities"]


def test_resource_schema_content():
    """The schema resource returns valid JSON with graph schema info."""
    from Code_Organism.mcp_server.server import resource_schema

    raw = resource_schema()
    data = json.loads(raw)

    assert "node_tables" in data
    assert "edge_table" in data
    assert "common_queries" in data
    assert "Function" in data["node_tables"]
    assert "CodeRelation" == data["edge_table"]["name"]
