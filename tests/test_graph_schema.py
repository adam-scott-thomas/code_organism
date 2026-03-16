"""Tests for graph.schema — KuzuDB schema creation."""
import tempfile
from pathlib import Path

import kuzu
import pytest

from Code_Organism.graph.schema import create_schema, NODE_TABLES


@pytest.fixture
def kuzu_conn(tmp_path):
    """Yield a fresh KuzuDB connection."""
    db_path = tmp_path / "test.kuzu"
    db = kuzu.Database(str(db_path))
    conn = kuzu.Connection(db)
    yield conn


def _get_table_names(conn: kuzu.Connection) -> set[str]:
    result = conn.execute("CALL show_tables() RETURN name")
    names: set[str] = set()
    while result.has_next():
        names.add(result.get_next()[0])
    return names


class TestCreateSchema:
    def test_creates_all_tables(self, kuzu_conn):
        """create_schema creates every expected node table plus CodeRelation."""
        create_schema(kuzu_conn)
        names = _get_table_names(kuzu_conn)

        for table_name in NODE_TABLES:
            assert table_name in names, f"Missing table: {table_name}"
        assert "CodeRelation" in names

    def test_idempotent(self, kuzu_conn):
        """Calling create_schema twice does not raise."""
        create_schema(kuzu_conn)
        create_schema(kuzu_conn)  # should not error

        names = _get_table_names(kuzu_conn)
        # Still has exactly the expected tables
        for table_name in NODE_TABLES:
            assert table_name in names

    def test_health_columns_exist(self, kuzu_conn):
        """Full-schema tables accept health-related columns."""
        create_schema(kuzu_conn)

        # Insert a Function node with health data
        kuzu_conn.execute(
            "CREATE (f:Function {"
            "  uid: $uid, name: $name, filePath: $fp, startLine: $sl, endLine: $el,"
            "  docstring: $doc, source_code: $sc,"
            "  health_status: $hs, health_score: $hscore,"
            "  cyclomatic_complexity: $cc, cognitive_complexity: $cog,"
            "  maintainability_index: $mi, halstead_difficulty: $hd,"
            "  lines_of_code: $loc, signature: $sig, is_async: $ia"
            "})",
            {
                "uid": "fn-001",
                "name": "compute",
                "fp": "math.py",
                "sl": 10,
                "el": 25,
                "doc": "Compute stuff.",
                "sc": "def compute(): ...",
                "hs": "healthy",
                "hscore": 0.95,
                "cc": 3,
                "cog": 2,
                "mi": 85.0,
                "hd": 4.5,
                "loc": 15,
                "sig": "compute() -> int",
                "ia": False,
            },
        )

        # Read it back
        result = kuzu_conn.execute(
            "MATCH (f:Function {uid: 'fn-001'}) "
            "RETURN f.health_score, f.cyclomatic_complexity, f.maintainability_index"
        )
        row = result.get_next()
        assert row[0] == pytest.approx(0.95)
        assert row[1] == 3
        assert row[2] == pytest.approx(85.0)
