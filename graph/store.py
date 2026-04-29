# SPDX-License-Identifier: Apache-2.0
"""KuzuDB graph store for Code_Organism."""
from __future__ import annotations

import sys
from pathlib import Path

import kuzu

from ..model.nodes import NodeType, OrganismNode
from ..model.organism import Organism
from .schema import create_schema

# Map NodeType enum values to KuzuDB table names.
# PARAMETER and ATTRIBUTE are stored in the Variable table.
_TYPE_TO_TABLE: dict[str, str] = {
    NodeType.MODULE.value: "Module",
    NodeType.PACKAGE.value: "Package",
    NodeType.CLASS.value: "Class",
    NodeType.FUNCTION.value: "Function",
    NodeType.METHOD.value: "Method",
    NodeType.VARIABLE.value: "Variable",
    NodeType.PARAMETER.value: "Variable",
    NodeType.ATTRIBUTE.value: "Variable",
    NodeType.EXTERNAL_MODULE.value: "External",
    NodeType.BUILTIN.value: "External",
}

# Node types that use the common (full) column set
_FULL_TABLES = {"Module", "Package", "Class", "Function", "Method"}

# Tables that can participate in CodeRelation edges
_EDGE_TABLES = {"Module", "Package", "Class", "Function", "Method", "Variable", "External"}


class GraphStore:
    """Persist and query a Code_Organism graph in KuzuDB."""

    def __init__(self, db_path: str | Path) -> None:
        self._db_path = Path(db_path)
        self._db: kuzu.Database | None = None
        self._conn: kuzu.Connection | None = None

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def open(self) -> None:
        """Open (or create) the database and ensure the schema exists."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = kuzu.Database(str(self._db_path))
        self._conn = kuzu.Connection(self._db)
        create_schema(self._conn)

    def close(self) -> None:
        """Close the database connection."""
        # kuzu.Connection and Database don't expose an explicit close(),
        # but dropping references lets the C++ destructor run.
        self._conn = None
        self._db = None

    def __enter__(self) -> GraphStore:
        self.open()
        return self

    def __exit__(self, *args: object) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def save(self, organism: Organism) -> None:
        """Persist all nodes and edges from *organism* into the graph.

        Clears any existing data first so the DB reflects exactly what
        the Organism object contains.
        """
        assert self._conn is not None, "Store is not open"
        conn = self._conn

        # --- clear existing data (DETACH DELETE removes edges automatically) ---
        for table in _EDGE_TABLES | {"Community", "Process"}:
            try:
                conn.execute(f"MATCH (n:{table}) DETACH DELETE n")
            except Exception:
                pass  # table may be empty or not exist yet

        # --- insert nodes ---
        for node in organism.nodes.values():
            table_or_none = _TYPE_TO_TABLE.get(node.node_type.value)
            if table_or_none is None:
                # Skip relationship-type "nodes" (IMPORT, CALL, REFERENCE)
                continue
            self._insert_node(conn, node, table_or_none)

        # --- insert edges ---
        for edge in organism.edges.values():
            self._insert_edge(conn, edge, organism)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def count_nodes(self) -> int:
        """Return the total number of nodes across all tables."""
        assert self._conn is not None, "Store is not open"
        result = self._conn.execute("MATCH (n) RETURN count(n)")
        if isinstance(result, list):
            result = result[-1]
        row = result.get_next()
        # kuzu returns a list-like row; the type stub says dict.
        return int(row[0])  # type: ignore[index]

    def query(self, cypher: str, parameters: dict | None = None) -> list[dict]:
        """Execute a Cypher query and return results as a list of dicts.

        Each dict maps column name -> value.
        """
        assert self._conn is not None, "Store is not open"
        if parameters:
            result = self._conn.execute(cypher, parameters)
        else:
            result = self._conn.execute(cypher)

        # kuzu returns list[QueryResult] only when the query string contains
        # multiple statements; single-Cypher callers get a single QueryResult.
        if isinstance(result, list):
            result = result[-1]

        columns = result.get_column_names()
        rows: list[dict] = []
        while result.has_next():
            values = result.get_next()
            rows.append(dict(zip(columns, values, strict=False)))
        return rows

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _insert_node(self, conn: kuzu.Connection, node: OrganismNode, table: str) -> None:
        """Insert a single node into the appropriate table."""
        if table == "Variable":
            self._insert_variable(conn, node)
        elif table == "External":
            self._insert_external(conn, node)
        elif table in _FULL_TABLES:
            self._insert_full_node(conn, node, table)

    def _insert_full_node(self, conn: kuzu.Connection, node: OrganismNode, table: str) -> None:
        """Insert a node into one of the full-schema tables (Module/Package/Class/Function/Method)."""
        file_path = node.position.file if node.position else ""
        start_line = node.position.line if node.position else 0
        end_line = (node.position.end_line if node.position and node.position.end_line else 0)

        health_score = node.metrics.health_score()

        params = {
            "uid": node.id,
            "name": node.name,
            "filePath": file_path,
            "startLine": start_line,
            "endLine": end_line,
            "docstring": node.docstring or "",
            "source_code": node.source_code or "",
            "health_status": node.health.value,
            "health_score": health_score,
            "cyclomatic_complexity": node.metrics.cyclomatic_complexity,
            "cognitive_complexity": node.metrics.cognitive_complexity,
            "maintainability_index": node.metrics.maintainability_index,
            "halstead_difficulty": node.metrics.halstead_difficulty or 0.0,
            "lines_of_code": node.metrics.lines_of_code,
        }

        base_cols = (
            "uid: $uid, name: $name, filePath: $filePath, "
            "startLine: $startLine, endLine: $endLine, "
            "docstring: $docstring, source_code: $source_code, "
            "health_status: $health_status, health_score: $health_score, "
            "cyclomatic_complexity: $cyclomatic_complexity, "
            "cognitive_complexity: $cognitive_complexity, "
            "maintainability_index: $maintainability_index, "
            "halstead_difficulty: $halstead_difficulty, "
            "lines_of_code: $lines_of_code"
        )

        extra = ""
        if table == "Class":
            params["bases"] = ""  # Could be populated from AST later
            extra = ", bases: $bases"
        elif table == "Function":
            params["signature"] = node.signature or ""
            params["is_async"] = False  # Could be populated from AST later
            extra = ", signature: $signature, is_async: $is_async"
        elif table == "Method":
            params["signature"] = node.signature or ""
            params["is_async"] = False
            params["is_property"] = False
            extra = ", signature: $signature, is_async: $is_async, is_property: $is_property"

        cypher = f"CREATE (n:{table} {{{base_cols}{extra}}})"
        conn.execute(cypher, params)

    def _insert_variable(self, conn: kuzu.Connection, node: OrganismNode) -> None:
        """Insert a Variable/Parameter/Attribute node."""
        file_path = node.position.file if node.position else ""
        start_line = node.position.line if node.position else 0
        end_line = (node.position.end_line if node.position and node.position.end_line else 0)

        conn.execute(
            "CREATE (n:Variable {uid: $uid, name: $name, filePath: $filePath, "
            "startLine: $startLine, endLine: $endLine})",
            {
                "uid": node.id,
                "name": node.name,
                "filePath": file_path,
                "startLine": start_line,
                "endLine": end_line,
            },
        )

    def _insert_external(self, conn: kuzu.Connection, node: OrganismNode) -> None:
        """Insert an External/Builtin node."""
        conn.execute(
            "CREATE (n:External {uid: $uid, name: $name, kind: $kind})",
            {
                "uid": node.id,
                "name": node.name,
                "kind": node.node_type.value,
            },
        )

    def _insert_edge(self, conn: kuzu.Connection, edge, organism: Organism) -> None:
        """Insert an edge by matching source and target nodes by uid."""
        src_node = organism.nodes.get(edge.source_id)
        tgt_node = organism.nodes.get(edge.target_id)

        if src_node is None or tgt_node is None:
            print(
                f"[GraphStore] skipping edge {edge.id}: "
                f"missing {'source' if src_node is None else 'target'} node",
                file=sys.stderr,
            )
            return

        src_table = _TYPE_TO_TABLE.get(src_node.node_type.value)
        tgt_table = _TYPE_TO_TABLE.get(tgt_node.node_type.value)

        if src_table is None or tgt_table is None:
            print(
                f"[GraphStore] skipping edge {edge.id}: "
                f"unmapped node type (src={src_node.node_type.value}, tgt={tgt_node.node_type.value})",
                file=sys.stderr,
            )
            return

        if src_table not in _EDGE_TABLES or tgt_table not in _EDGE_TABLES:
            print(
                f"[GraphStore] skipping edge {edge.id}: "
                f"table not in edge schema (src_table={src_table}, tgt_table={tgt_table})",
                file=sys.stderr,
            )
            return

        try:
            conn.execute(
                f"MATCH (s:{src_table} {{uid: $src_uid}}), (t:{tgt_table} {{uid: $tgt_uid}}) "
                f"CREATE (s)-[:CodeRelation {{kind: $kind, weight: $weight}}]->(t)",
                {
                    "src_uid": edge.source_id,
                    "tgt_uid": edge.target_id,
                    "kind": edge.edge_type,
                    "weight": edge.weight,
                },
            )
        except Exception as exc:
            print(
                f"[GraphStore] skipping edge {edge.id} "
                f"({src_table}:{edge.source_id} -> {tgt_table}:{edge.target_id}): {exc}",
                file=sys.stderr,
            )
