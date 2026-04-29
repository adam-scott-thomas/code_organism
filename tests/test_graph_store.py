"""Tests for graph.store — GraphStore persistence layer."""

import pytest

from Code_Organism.graph.store import GraphStore
from Code_Organism.model.nodes import (
    Edge,
    HealthStatus,
    Metrics,
    NodeType,
    OrganismNode,
    Position,
)
from Code_Organism.model.organism import Organism


def _make_organism() -> Organism:
    """Build a small Organism with nodes and edges for testing."""
    org = Organism(name="test-org")

    mod = OrganismNode(
        id="mod1",
        name="app",
        node_type=NodeType.MODULE,
        qualified_name="app",
        position=Position(file="app.py", line=1, column=0, end_line=50),
        metrics=Metrics(
            cyclomatic_complexity=1,
            cognitive_complexity=0,
            maintainability_index=90.0,
            halstead_difficulty=2.0,
            lines_of_code=50,
        ),
        health=HealthStatus.HEALTHY,
    )

    cls = OrganismNode(
        id="cls1",
        name="Handler",
        node_type=NodeType.CLASS,
        qualified_name="app.Handler",
        position=Position(file="app.py", line=5, column=0, end_line=30),
        metrics=Metrics(
            cyclomatic_complexity=4,
            cognitive_complexity=3,
            maintainability_index=75.0,
            halstead_difficulty=6.5,
            lines_of_code=25,
        ),
        health=HealthStatus.STRESSED,
    )

    func = OrganismNode(
        id="fn1",
        name="run",
        node_type=NodeType.FUNCTION,
        qualified_name="app.run",
        position=Position(file="app.py", line=35, column=0, end_line=45),
        signature="run() -> None",
        metrics=Metrics(
            cyclomatic_complexity=2,
            cognitive_complexity=1,
            maintainability_index=88.0,
            halstead_difficulty=3.0,
            lines_of_code=10,
        ),
        health=HealthStatus.HEALTHY,
    )

    var = OrganismNode(
        id="var1",
        name="TIMEOUT",
        node_type=NodeType.VARIABLE,
        qualified_name="app.TIMEOUT",
        position=Position(file="app.py", line=3, column=0),
    )

    ext = OrganismNode(
        id="ext1",
        name="os",
        node_type=NodeType.EXTERNAL_MODULE,
        qualified_name="os",
    )

    for node in [mod, cls, func, var, ext]:
        org.add_node(node)

    # Edges: module contains class, module contains function, function references variable
    org.add_edge(Edge(
        id="e1",
        source_id="mod1",
        target_id="cls1",
        edge_type="contains",
        weight=1.0,
    ))
    org.add_edge(Edge(
        id="e2",
        source_id="mod1",
        target_id="fn1",
        edge_type="contains",
        weight=1.0,
    ))
    org.add_edge(Edge(
        id="e3",
        source_id="fn1",
        target_id="var1",
        edge_type="reference",
        weight=0.5,
    ))
    org.add_edge(Edge(
        id="e4",
        source_id="mod1",
        target_id="ext1",
        edge_type="import",
        weight=1.0,
    ))

    return org


class TestGraphStoreLifecycle:
    def test_open_creates_db(self, tmp_path):
        """open() creates the database file/directory."""
        db_path = tmp_path / "sub" / "graph.kuzu"
        store = GraphStore(db_path)
        store.open()
        try:
            # Parent directory must exist after open
            assert db_path.parent.exists()
        finally:
            store.close()

    def test_context_manager(self, tmp_path):
        """GraphStore works as a context manager."""
        db_path = tmp_path / "graph.kuzu"
        with GraphStore(db_path) as store:
            assert store.count_nodes() == 0
        # After exiting, the store should be closed (no crash)


class TestGraphStoreSave:
    def test_save_persists_nodes(self, tmp_path):
        """save() inserts nodes that can be counted."""
        db_path = tmp_path / "graph.kuzu"
        org = _make_organism()

        with GraphStore(db_path) as store:
            store.save(org)
            count = store.count_nodes()
            assert count == 5  # mod, cls, func, var, ext

    def test_roundtrip_health_data(self, tmp_path):
        """Health data survives a save/query roundtrip."""
        db_path = tmp_path / "graph.kuzu"
        org = _make_organism()

        with GraphStore(db_path) as store:
            store.save(org)

            rows = store.query(
                "MATCH (f:Function {uid: $uid}) "
                "RETURN f.health_status AS status, "
                "       f.health_score AS score, "
                "       f.cyclomatic_complexity AS cc, "
                "       f.maintainability_index AS mi",
                {"uid": "fn1"},
            )
            assert len(rows) == 1
            row = rows[0]
            assert row["status"] == "healthy"
            assert row["score"] == pytest.approx(org.nodes["fn1"].metrics.health_score())
            assert row["cc"] == 2
            assert row["mi"] == pytest.approx(88.0)

    def test_edges_preserved(self, tmp_path):
        """Edges are persisted and can be queried."""
        db_path = tmp_path / "graph.kuzu"
        org = _make_organism()

        with GraphStore(db_path) as store:
            store.save(org)

            rows = store.query(
                "MATCH (s)-[r:CodeRelation]->(t) "
                "RETURN s.uid AS src, r.kind AS kind, t.uid AS tgt "
                "ORDER BY src, tgt"
            )
            assert len(rows) == 4

            # Check specific edges
            kinds = {(r["src"], r["tgt"]): r["kind"] for r in rows}
            assert kinds[("mod1", "cls1")] == "contains"
            assert kinds[("mod1", "fn1")] == "contains"
            assert kinds[("fn1", "var1")] == "reference"
            assert kinds[("mod1", "ext1")] == "import"

    def test_save_clears_previous(self, tmp_path):
        """Calling save() a second time replaces existing data."""
        db_path = tmp_path / "graph.kuzu"
        org = _make_organism()

        with GraphStore(db_path) as store:
            store.save(org)
            assert store.count_nodes() == 5

            # Save again — should still be 5, not 10
            store.save(org)
            assert store.count_nodes() == 5


class TestGraphStoreQuery:
    def test_query_returns_dicts(self, tmp_path):
        """query() returns list of dicts with column names as keys."""
        db_path = tmp_path / "graph.kuzu"
        org = _make_organism()

        with GraphStore(db_path) as store:
            store.save(org)

            rows = store.query(
                "MATCH (m:Module) RETURN m.uid AS uid, m.name AS name"
            )
            assert len(rows) == 1
            assert rows[0]["uid"] == "mod1"
            assert rows[0]["name"] == "app"

    def test_query_empty_result(self, tmp_path):
        """query() returns empty list when no matches."""
        db_path = tmp_path / "graph.kuzu"

        with GraphStore(db_path) as store:
            rows = store.query("MATCH (m:Module) RETURN m.uid AS uid")
            assert rows == []
