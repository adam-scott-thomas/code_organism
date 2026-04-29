# SPDX-License-Identifier: Apache-2.0
"""KuzuDB schema for Code_Organism graph."""
import kuzu

# Common data columns shared by structural node types (no PRIMARY KEY — appended separately)
_COMMON_DATA = (
    "uid STRING, "
    "name STRING, "
    "filePath STRING, "
    "startLine INT64, "
    "endLine INT64, "
    "docstring STRING, "
    "source_code STRING, "
    "health_status STRING, "
    "health_score DOUBLE, "
    "cyclomatic_complexity INT64, "
    "cognitive_complexity INT64, "
    "maintainability_index DOUBLE, "
    "halstead_difficulty DOUBLE, "
    "lines_of_code INT64"
)

_PK = ", PRIMARY KEY (uid)"

# For spec compatibility, expose a combined _COMMON_COLUMNS constant
_COMMON_COLUMNS = _COMMON_DATA + _PK

NODE_TABLES = {
    "Module":    _COMMON_DATA + _PK,
    "Package":   _COMMON_DATA + _PK,
    "Class":     _COMMON_DATA + ", bases STRING" + _PK,
    "Function":  _COMMON_DATA + ", signature STRING, is_async BOOLEAN" + _PK,
    "Method":    _COMMON_DATA + ", signature STRING, is_async BOOLEAN, is_property BOOLEAN" + _PK,
    "Variable":  "uid STRING, name STRING, filePath STRING, startLine INT64, endLine INT64, PRIMARY KEY (uid)",
    "External":  "uid STRING, name STRING, kind STRING, PRIMARY KEY (uid)",
    "Community": "uid STRING, name STRING, keywords STRING, cohesion DOUBLE, symbolCount INT64, PRIMARY KEY (uid)",
    "Process":   "uid STRING, name STRING, entryPointId STRING, stepCount INT64, processType STRING, PRIMARY KEY (uid)",
}

# All structural node types that can participate in code relationships
_STRUCTURAL_TYPES = ["Module", "Package", "Class", "Function", "Method", "Variable", "External"]


def create_schema(conn: kuzu.Connection) -> None:
    """Create the KuzuDB schema. Idempotent -- safe to call multiple times."""
    # Check which tables already exist
    result = conn.execute("CALL show_tables() RETURN name")
    if isinstance(result, list):
        result = result[-1]
    existing: set[str] = set()
    while result.has_next():
        # kuzu's get_next() returns a list-like row; the type stub says dict.
        existing.add(str(result.get_next()[0]))  # type: ignore[index]

    # Create node tables
    for table_name, columns in NODE_TABLES.items():
        if table_name not in existing:
            conn.execute(f"CREATE NODE TABLE {table_name}({columns})")

    # Create edge table covering all structural type combinations
    if "CodeRelation" not in existing:
        from_to_pairs = []
        for src in _STRUCTURAL_TYPES:
            for tgt in _STRUCTURAL_TYPES:
                from_to_pairs.append(f"FROM {src} TO {tgt}")
        from_to_clause = ", ".join(from_to_pairs)
        conn.execute(
            f"CREATE REL TABLE CodeRelation("
            f"{from_to_clause}, "
            f"kind STRING, "
            f"weight DOUBLE"
            f")"
        )
