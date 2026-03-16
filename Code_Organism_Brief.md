# Code_Organism: 3D Codebase Visualization with Health Diagnostics

**Ghost_Logic Forensic Evidence Platform -- Instance 8**

Author: Adam Thomas, Independent Researcher
Date: 2026-02-14
Classification: Executive Brief

---

## 1. Executive Summary

Code_Organism transforms source code into a living, navigable 3D structure. It combines static AST analysis with dynamic runtime tracing to produce a force-directed graph where every node carries a computed health status -- HEALTHY, STRESSED, INFLAMED, NECROTIC, or CANCEROUS -- derived from McCabe cyclomatic complexity, Halstead metrics, and a composite maintainability index.

The system ships with four rendering modes: a flat force-directed graph (Three.js WebGL), an instanced renderer for GPU-efficient large graphs, a Solar System hierarchical navigator that maps packages to galaxies and functions to planets, and a playback renderer that replays recorded execution traces frame-by-frame with variable speed from 0.1x to 50x.

Static analysis walks the Python AST once, producing 13 distinct node types and 5 edge types. Dynamic analysis instruments the runtime via `sys.settrace`, capturing every call, return, and exception with nanosecond-precision timestamps. A dedicated malware scanner evaluates 30+ dangerous import signatures and 11 regex-based behavioral patterns, flagging code injection, obfuscation, command-and-control channels, and ransomware indicators on a 4-tier severity scale.

The Python-side layout engine uses Barnes-Hut approximation for O(n log n) force calculations with an octree spatial data structure. Layouts are cached to disk via MD5-keyed JSON files. The JavaScript-side force simulation runs 80-100 iterations with Coulomb repulsion and Hooke attraction, producing interactive 3D scenes that render in any modern browser without plugins.

---

## 2. Problem

Codebase complexity is invisible. Developers work inside text editors that show one file at a time, leaving the structural relationships between modules, the coupling between classes, and the health of individual functions entirely opaque. Three specific gaps motivate this work:

**No spatial intuition.** A developer reading a 50,000-line project has no way to see which modules cluster together, which classes are isolated, or where the dependency bottlenecks lie. Existing call-graph tools produce flat 2D diagrams that collapse under scale.

**Static metrics miss runtime behavior.** McCabe complexity tells you a function has 15 decision paths, but not that 14 of them are never exercised. Without execution tracing, dead code and hot paths are indistinguishable from each other.

**No unified health model.** Current tools report complexity, coupling, and code smells as separate disconnected metrics. No existing system maps all of these into a single biological health classification that a non-specialist can read at a glance -- let alone combines that health model with malware detection in the same pipeline.

Code_Organism addresses all three gaps in a single integrated system.

---

## 3. Visualization Engine

### 3.1 Force-Directed Graph Layout

Code_Organism computes 3D node positions using force-directed simulation. Two implementations serve different contexts.

**Python-side layout** (`model/layout.py`) runs before rendering, using Barnes-Hut octree approximation:

```python
class LayoutEngine:
    def compute_layout(
        self,
        nodes: Dict[str, Node],
        edges: Dict[str, Edge],
        use_cache: bool = True,
        iterations: int = 100,
        theta: float = 0.8,  # Barnes-Hut threshold
    ) -> Dict[str, dict]:
```

Force parameters from the source:

| Parameter  | Value  | Role                                    |
|------------|--------|-----------------------------------------|
| repulsion  | 1000.0 | Coulomb-like node separation            |
| attraction | 0.01   | Spring force along edges                |
| damping    | 0.9    | Velocity decay per iteration            |
| theta      | 0.8    | Barnes-Hut distance/size approximation  |
| iterations | 100    | Simulation steps                        |
| min_dist   | 0.1    | Minimum distance floor                  |

Adaptive damping decays at 0.99 per iteration: `damping = max(0.5, damping * 0.99)`. Graphs under 5,000 nodes use direct O(n^2) repulsion; graphs over 5,000 nodes switch to spatial hashing with a 5-cell neighborhood radius for approximate O(n log n) behavior. Layouts are cached to `~/.code_organism/layout_cache/` keyed by MD5 hash of sorted node IDs and edge pairs.

**JavaScript-side layout** (`renderer/graph_3d.py` inline JS) runs at page load for smaller graphs:

```javascript
const iterations = 100;
const repulsion = 100;
const attraction = 0.1;
const damping = 0.85;
```

The playback renderer (`renderer/playback_renderer.py`) uses a separate parameter set tuned for execution replay: repulsion = 400/dist^2, attraction = dist * 0.04, damping = 0.9, 80 iterations.

### 3.2 Three.js WebGL Rendering

All renderers produce self-contained HTML pages served via a local HTTP server on a configurable port (default 8765). The visualization stack:

- **Three.js r128** loaded from CDN
- **OrbitControls** for camera rotation, zoom, and pan with damping factor 0.05
- **Raycaster** for click-to-select node interaction
- **MeshPhongMaterial** with emissive glow scaled to 0.4x base color intensity
- **FogExp2** at density 0.0005 for depth perception

Node geometries are mapped by type:

| Node Type   | Geometry              | Base Size Multiplier |
|-------------|-----------------------|----------------------|
| module      | BoxGeometry           | 1.5x                |
| class       | OctahedronGeometry    | 1.2x                |
| function    | SphereGeometry(16,16) | 0.8x                |
| external    | TetrahedronGeometry   | 0.7x                |
| default     | SphereGeometry(8,8)   | 0.5x                |

Edges render as CylinderGeometry tubes (radius 0.5, 6 segments) oriented by quaternion rotation between source and target node positions, with opacity 0.6 and type-based coloring (import=#4488ff, call=#44ff88, inheritance=#ff8844).

### 3.3 Solar System Navigator

For large codebases, the Solar System renderer (`renderer/solar_system.py`) maps code structure to a cosmic hierarchy:

| Code Structure   | Cosmic Object | Geometry                 |
|------------------|---------------|--------------------------|
| Package          | Galaxy        | IcosahedronGeometry      |
| Module           | Star System   | OctahedronGeometry       |
| Class            | Star          | SphereGeometry (high-res)|
| Function/Method  | Planet        | SphereGeometry           |
| Nested/Variable  | Moon          | SphereGeometry (low-res) |
| External/Builtin | Asteroid      | TetrahedronGeometry      |

The renderer maintains only 50-200 visible objects at any time. Users click to drill down through the hierarchy, and a breadcrumb trail allows upward navigation. The backend serves JSON via API endpoints (`/api/universe`, `/api/expand/{id}`, `/api/stats`), so only the visible slice of the codebase is ever sent to the browser.

---

## 4. Dual Analysis Pipeline

### 4.1 Static Analysis: The CodeAnatomist

The AST walker (`parser/ast_walker.py`) dissects Python source into anatomical nodes and edges in a single pass. The `CodeAnatomist` class extends `ast.NodeVisitor`:

```python
class CodeAnatomist(ast.NodeVisitor):
    def __init__(self, context: WalkContext):
        self.context = context
        self.nodes: list[OrganismNode] = []
        self.edges: list[Edge] = []
        self._defined_names: dict[str, str] = {}
        self._imports: dict[str, str] = {}
        self._current_node_id: Optional[str] = None
```

It extracts 13 node types organized into five anatomical categories:

| Category           | Node Types                        | Biological Metaphor              |
|--------------------|-----------------------------------|----------------------------------|
| Skeletal System    | MODULE, PACKAGE                   | Bones, bone clusters             |
| Organ Systems      | CLASS, FUNCTION, METHOD           | Organs, tissues, capillaries     |
| Cellular Level     | VARIABLE, PARAMETER, ATTRIBUTE    | Cells, receptors, properties     |
| Connective Tissue  | IMPORT, CALL, REFERENCE           | Ligaments, nerve signals, vessels|
| External Systems   | EXTERNAL_MODULE, BUILTIN          | Symbiotic organisms, chemistry   |

Five edge types connect nodes: `import`, `call`, `reference`, `inheritance`, and `composition`. Each edge carries a weight, bidirectional flag, and flow metrics. Node IDs are generated by SHA-256 hashing of `"{type}:{qualified_name}"`, truncated to 16 hex characters:

```python
@staticmethod
def generate_id(qualified_name: str, node_type: NodeType) -> str:
    content = f"{node_type.value}:{qualified_name}"
    return hashlib.sha256(content.encode()).hexdigest()[:16]
```

Cyclomatic complexity is computed inline during the walk:

```python
def _compute_complexity(self, node: ast.AST) -> int:
    complexity = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)):
            complexity += 1
        elif isinstance(child, ast.ExceptHandler):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += len(child.values) - 1
        elif isinstance(child, ast.IfExp):
            complexity += 1
        elif isinstance(child, ast.comprehension):
            complexity += 1
            if child.ifs:
                complexity += len(child.ifs)
    return complexity
```

### 4.2 Dynamic Analysis: The Tracer

The runtime tracer (`tracer/instrumenter.py`) instruments execution using Python's `sys.settrace` hook:

```python
class Tracer:
    def start(self, trace_id: Optional[str] = None) -> ExecutionTrace:
        self.trace = self.organism.start_trace(trace_id)
        self._start_time_ns = time.perf_counter_ns()
        self._active = True
        sys.settrace(self._trace_function)
        threading.settrace(self._trace_function)
        return self.trace
```

The trace function filters events to only files present in the organism, then records three event types:

- **call**: Captures function name, qualified name, filename, line number, and a snapshot of local variables (excluding underscore-prefixed names)
- **return**: Captures return value representation and type name, increments call_count on the node
- **exception**: Captures exception type, message, and full traceback, increments exceptions_raised

Each event produces an `ExecutionFrame` dataclass:

```python
@dataclass
class ExecutionFrame:
    timestamp: datetime
    frame_index: int
    node_id: str
    event_type: str     # "enter", "exit", "read", "write", "call", "return", "exception"
    event_data: dict
    local_vars: dict
    call_stack: list[str]
    elapsed_ns: int
    memory_bytes: int
```

Call events spawn `FlowParticle` objects for visualization, color-coded by data type: int=#3355ff, str=#33cc33, Exception=#ff3333, dict=#ee8822.

### 4.3 Recording and Playback

The timeline subsystem (`timeline/`) provides full recording, serialization, and replay:

```python
@dataclass
class RecordingMetadata:
    session_id: str
    organism_id: str
    organism_name: str
    started_at: str
    ended_at: Optional[str] = None
    total_frames: int = 0
    duration_ns: int = 0
    file_count: int = 0
    node_count: int = 0
    edge_count: int = 0
    avg_frame_interval_ns: int = 0
    min_frame_interval_ns: int = 0
    max_frame_interval_ns: int = 0
```

Recordings save as `.corg` (JSON) or `.corg.gz` (gzip-compressed JSON). The `TimelinePlayer` supports 5 playback states (STOPPED, PLAYING, PAUSED, SEEKING, FINISHED), variable speed from 0.01x to 100x, and 8 preset speeds: [0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 10.0, 50.0]. Seeking uses binary search on timestamps for O(log n) frame lookup. The `TimelineController` defines 17 control commands with keyboard bindings.

---

## 5. Health Diagnostics

### 5.1 McCabe Cyclomatic Complexity

The `ComplexityAnalyzer` (`health/complexity.py`) computes CC by walking the AST and counting decision points:

```python
def _compute_cyclomatic(self, node: ast.AST) -> int:
    complexity = 1
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.While, ast.For, ast.AsyncFor)):
            complexity += 1
        elif isinstance(child, ast.ExceptHandler):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += len(child.values) - 1
        elif isinstance(child, ast.IfExp):
            complexity += 1
        elif isinstance(child, ast.comprehension):
            complexity += 1
            complexity += len(child.ifs)
        elif isinstance(child, ast.Assert):
            complexity += 1
    return complexity
```

Decision points counted: `if`, `while`, `for`, `async for`, `except`, boolean operators (`and`/`or` each add len-1), ternary expressions, comprehensions (including their filter clauses), and assertions.

### 5.2 Cognitive Complexity

Unlike cyclomatic complexity, cognitive complexity weights nesting depth to reflect human comprehension difficulty. Each structural construct (if, for, while, except) adds `1 + current_nesting_level`, penalizing deeply nested code exponentially:

```python
if isinstance(n, (ast.If, ast.IfExp)):
    increment += 1 + nesting_level
    nesting_increment = 1
elif isinstance(n, (ast.For, ast.AsyncFor, ast.While)):
    increment += 1 + nesting_level
    nesting_increment = 1
```

Boolean operators add `len(values) - 1` regardless of nesting. Break/continue statements add 1 as flow interrupts.

### 5.3 Halstead Metrics

The `_compute_halstead` method classifies AST nodes into operators and operands:

| Category  | AST Node Types                                       |
|-----------|------------------------------------------------------|
| Operators | BinOp, UnaryOp, BoolOp, Compare, Call, Subscript, Attribute |
| Operands  | Name, Constant                                       |

From these counts, seven derived metrics are computed:

| Metric             | Formula                              |
|--------------------|--------------------------------------|
| Vocabulary (n)     | n1 + n2                              |
| Length (N)          | N1 + N2                              |
| Volume (V)         | N * log2(n)                          |
| Difficulty (D)     | (n1 / 2) * (N2 / n2)                |
| Effort (E)         | D * V                                |
| Time to Program    | E / 18 (seconds)                     |
| Bugs Delivered     | V / 3000                             |

Where n1 = unique operators, n2 = unique operands, N1 = total operators, N2 = total operands.

### 5.4 Maintainability Index

The composite maintainability index follows the standard SEI formula, normalized to a 0-100 scale:

```python
def _compute_maintainability(self, cyclomatic: int, loc: int, volume: float) -> float:
    if loc == 0:
        return 100.0
    v = max(volume, 1)
    cc = cyclomatic
    lines = max(loc, 1)
    mi = 171 - 5.2 * math.log(v) - 0.23 * cc - 16.2 * math.log(lines)
    mi = max(0, mi * 100 / 171)
    return round(mi, 2)
```

This formula -- `MI = 171 - 5.2 * ln(V) - 0.23 * CC - 16.2 * ln(LOC)` -- weighs Halstead volume most heavily, followed by lines of code, with cyclomatic complexity as a minor correction factor. The normalization `mi * 100 / 171` maps the theoretical maximum of 171 to a percentage scale.

### 5.5 Pattern Detection

The `PatternDetector` (`health/patterns.py`) applies 12 anti-pattern checks organized by category:

| Pattern              | Threshold    | Severity | Category      |
|----------------------|--------------|----------|---------------|
| long_function        | > 50 lines   | WARNING  | complexity    |
| too_many_arguments   | > 5 args     | WARNING  | complexity    |
| deep_nesting         | > 4 levels   | WARNING  | complexity    |
| god_class            | > 20 methods | WARNING  | design        |
| complex_init         | > 30 lines   | WARNING  | complexity    |
| bare_except          | any          | WARNING  | error_handling|
| star_import          | any          | WARNING  | imports       |
| missing_docstring    | public funcs | INFO     | documentation |
| single_letter_var    | non-standard | INFO     | naming        |
| compare_to_true      | `== True`    | INFO     | style         |
| long_boolean_expr    | > 3 terms    | INFO     | complexity    |
| long_file            | > 500 lines  | WARNING  | organization  |

---

## 6. Health Status Model

Every `OrganismNode` carries a `HealthStatus` enum from `model/nodes.py`:

```python
class HealthStatus(Enum):
    HEALTHY = "healthy"       # Clean, well-structured
    STRESSED = "stressed"     # High complexity, needs attention
    INFLAMED = "inflamed"     # Circular dependencies, tight coupling
    NECROTIC = "necrotic"     # Dead code, unreachable
    CANCEROUS = "cancerous"   # Obfuscated, malicious patterns
    UNKNOWN = "unknown"       # Not yet analyzed
```

### 6.1 Composite Health Score

The `health_score()` method on the `Metrics` dataclass computes a float from 0.0 (dead) to 1.0 (perfect):

```python
def health_score(self) -> float:
    score = 1.0
    if self.cyclomatic_complexity > 10:
        score -= min(0.3, (self.cyclomatic_complexity - 10) * 0.03)
    if self.depth > 4:
        score -= min(0.2, (self.depth - 4) * 0.05)
    if self.instability > 0.8 and self.afferent_coupling > 5:
        score -= 0.2
    score += (self.maintainability_index / 100) * 0.2 - 0.1
    return max(0.0, min(1.0, score))
```

Three penalty dimensions and one reward:

| Factor               | Trigger                          | Penalty/Reward           | Cap   |
|----------------------|----------------------------------|--------------------------|-------|
| Cyclomatic > 10      | Each unit over 10                | -0.03 per unit           | -0.30 |
| Nesting depth > 4    | Each level over 4                | -0.05 per level          | -0.20 |
| High instability     | instability > 0.8 AND afferent > 5 | -0.20 flat            | -0.20 |
| Maintainability      | MI / 100                         | +0.0 to +0.1 (net)      | +0.10 |

### 6.2 Status Thresholds

The `update_health()` method on `OrganismNode` maps scores to status tiers:

| Score Range | Status    | Interpretation                       |
|-------------|-----------|--------------------------------------|
| >= 0.80     | HEALTHY   | Clean, well-structured code          |
| 0.60 - 0.79| STRESSED  | Moderate complexity, needs attention |
| 0.30 - 0.59| INFLAMED  | High complexity, tight coupling      |
| < 0.30     | CANCEROUS | Critical complexity, likely dangerous|

Two override conditions bypass the score entirely:

- **NECROTIC**: Functions/methods with zero callers (excluding `__init__` and underscore-prefixed names) are classified as dead code regardless of their health score.
- **INFLAMED**: Nodes with self-referential imports or calls (circular dependencies) are immediately flagged.

### 6.3 Visualization Color Map

Health status maps to visualization colors in the Solar System renderer:

| Status    | Hex Color | Visual Appearance |
|-----------|-----------|-------------------|
| HEALTHY   | #44ff88   | Bright green      |
| STRESSED  | #ffff44   | Yellow            |
| INFLAMED  | #ff8844   | Orange            |
| NECROTIC  | #666666   | Gray              |
| CANCEROUS | #ff4444   | Red               |

### 6.4 Aggregate Statistics

The `OrganismStats` dataclass computes codebase-wide health counts:

```python
@dataclass
class OrganismStats:
    total_nodes: int = 0
    total_edges: int = 0
    total_modules: int = 0
    total_classes: int = 0
    total_functions: int = 0
    total_lines: int = 0
    avg_complexity: float = 0.0
    max_complexity: int = 0
    healthy_nodes: int = 0
    stressed_nodes: int = 0
    inflamed_nodes: int = 0
    necrotic_nodes: int = 0
    cancerous_nodes: int = 0
    max_depth: int = 0
    circular_dependencies: int = 0
    external_dependencies: int = 0
```

The `health_summary()` method returns per-tier percentages: `{"healthy": 0.72, "stressed": 0.15, "inflamed": 0.08, "necrotic": 0.05, "cancerous": 0.00}`.

---

## 7. Malware Detection

The `MalwareAnalyzer` (`health/malware.py`) functions as the organism's immune system, scanning for patterns associated with malicious code. Analysis is read-only -- it never modifies or executes the target.

### 7.1 Dangerous Import Catalog

The analyzer maintains a dictionary of 30+ import signatures with severity ratings:

```python
DANGEROUS_IMPORTS = {
    "exec": (MalwareSeverity.HIGH, "Dynamic code execution"),
    "eval": (MalwareSeverity.HIGH, "Dynamic expression evaluation"),
    "os.system": (MalwareSeverity.HIGH, "Shell command execution"),
    "os.popen": (MalwareSeverity.HIGH, "Shell pipe"),
    "pty": (MalwareSeverity.HIGH, "Pseudo-terminal"),
    "subprocess": (MalwareSeverity.MEDIUM, "Process spawning"),
    "paramiko": (MalwareSeverity.MEDIUM, "SSH connections"),
    "marshal": (MalwareSeverity.MEDIUM, "Code serialization"),
    "pickle": (MalwareSeverity.MEDIUM, "Object serialization (unsafe)"),
    "winreg": (MalwareSeverity.MEDIUM, "Windows registry access"),
    "ctypes": (MalwareSeverity.MEDIUM, "C library calls"),
    "socket": (MalwareSeverity.LOW, "Raw socket access"),
    "base64": (MalwareSeverity.LOW, "Base64 encoding"),
    # ... 17 additional entries
}
```

Each import found in the AST is matched against this catalog. Both exact matches and prefix matches are evaluated, allowing detection of `os.system` when only `os` is imported.

### 7.2 Behavioral Pattern Detection

Eleven regex patterns scan the raw source for behavioral indicators:

| Pattern                              | Severity  | Category        |
|--------------------------------------|-----------|-----------------|
| `eval(...decode(...))`               | CRITICAL  | code_injection  |
| `exec(compile(...))`                 | CRITICAL  | code_injection  |
| Long hex-encoded strings (6+ bytes)  | MEDIUM    | obfuscation     |
| Registry Run key references          | HIGH      | persistence     |
| Hardcoded IP addresses               | LOW       | network         |
| Common malware ports (4444, 1337...) | MEDIUM    | network         |
| Socket connect calls                 | MEDIUM    | network         |
| File encryption calls                | MEDIUM    | ransomware      |
| Hardcoded passwords                  | LOW       | credentials     |
| Base64-encoded data (50+ chars)      | LOW       | obfuscation     |
| Obfuscated variable names            | LOW       | obfuscation     |

### 7.3 Risk Scoring

The overall risk score aggregates all markers with severity-weighted confidence:

```python
severity_weights = {
    MalwareSeverity.LOW: 0.1,
    MalwareSeverity.MEDIUM: 0.3,
    MalwareSeverity.HIGH: 0.6,
    MalwareSeverity.CRITICAL: 1.0,
}

total_weight = sum(
    severity_weights[m.severity] * m.confidence
    for m in self.markers
)

self.overall_risk = min(1.0, total_weight / 3.0)
self.is_likely_malware = self.overall_risk >= 0.5 or any(
    m.severity == MalwareSeverity.CRITICAL for m in self.markers
)
```

A single CRITICAL marker (e.g., `eval` with decoded content, confidence 0.9) immediately flags the code as likely malicious regardless of the aggregate score. The normalization divisor of 3.0 means three medium-confidence, medium-severity markers are needed to cross the 0.5 threshold.

---

## 8. Key Metrics

### 8.1 Architecture Dimensions

| Dimension          | Count | Source                                 |
|--------------------|-------|----------------------------------------|
| Node types         | 13    | `model/nodes.py` NodeType enum         |
| Edge types         | 5     | import, call, reference, inheritance, composition |
| Health tiers       | 6     | HEALTHY through UNKNOWN                |
| Cosmic hierarchy   | 6     | Universe > Galaxy > Star System > Star > Planet > Moon |
| Rendering modes    | 4     | graph_3d, instanced, solar_system, playback |
| Complexity metrics | 4     | McCabe, cognitive, Halstead, maintainability |

### 8.2 Layout Engine Parameters

| Parameter          | Python-side         | JS graph_3d        | JS playback        |
|--------------------|---------------------|---------------------|---------------------|
| Repulsion          | 1000.0              | 100                 | 400/dist^2          |
| Attraction         | 0.01                | 0.1                 | dist * 0.04         |
| Damping            | 0.9 (adaptive)      | 0.85                | 0.9                 |
| Iterations         | 100                 | 100                 | 80                  |
| Min distance       | 0.1                 | 0.1                 | 0.1                 |
| BH threshold       | 0.8                 | N/A (direct O(n^2)) | N/A                 |
| Cache              | disk (MD5-keyed)    | none                | none                |

### 8.3 Timeline System

| Capability         | Value                                           |
|--------------------|-------------------------------------------------|
| Speed presets      | 8: [0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 10.0, 50.0]|
| Speed range        | 0.01x to 100x continuous                        |
| Control commands   | 17 (play, pause, stop, seek, step, speed, loop) |
| Playback states    | 5: STOPPED, PLAYING, PAUSED, SEEKING, FINISHED  |
| Seek algorithm     | Binary search on timestamps, O(log n)           |
| Recording format   | .corg (JSON) / .corg.gz (gzip-compressed)       |
| Frame precision    | Nanosecond (time.perf_counter_ns)                |
| Frame fields       | 9: timestamp, frame_index, node_id, event_type, event_data, local_vars, call_stack, elapsed_ns, memory_bytes |

### 8.4 Malware Scanner Coverage

| Category          | Patterns/Signatures | Severity Distribution           |
|-------------------|---------------------|---------------------------------|
| Dangerous imports | 30+                 | 7 HIGH, 10 MEDIUM, 9 LOW       |
| Regex patterns    | 11                  | 2 CRITICAL, 3 MEDIUM, 1 HIGH, 5 LOW |
| AST checks        | 4 categories        | exec/eval, shell calls, obfuscated names, string ops |
| Risk thresholds   | 2 triggers          | aggregate >= 0.5 OR any CRITICAL marker |

### 8.5 Health Score Boundaries

| Score  | Status    | Example Trigger                                    |
|--------|-----------|----------------------------------------------------|
| 1.00   | HEALTHY   | CC=5, depth=2, MI=85                               |
| 0.75   | STRESSED  | CC=18, depth=3, MI=60                              |
| 0.45   | INFLAMED  | CC=25, depth=6, MI=40                              |
| 0.10   | CANCEROUS | CC=35, depth=8, instability=0.9, afferent=10       |
| N/A    | NECROTIC  | Function with 0 callers (dead code bypass)         |

---

## 9. Future Work

**IDE Integration.** VS Code and PyCharm plugins that run Code_Organism analysis on save, rendering a minimap-style 3D health overlay in the editor sidebar. Health status changes would appear as inline annotations alongside traditional lint warnings.

**Real-Time Monitoring.** Continuous tracing mode that streams execution events to a persistent 3D visualization via WebSocket, enabling live observation of running production systems. The timeline playback infrastructure already supports variable-speed replay; extending it to live-append mode requires only a streaming frame protocol.

**Multi-Language AST Walkers.** The `CodeAnatomist` pattern is language-agnostic. JavaScript/TypeScript support would require replacing `ast.parse` with an Acorn or TypeScript compiler API walker while maintaining the same `OrganismNode` and `Edge` output format.

**Distributed Codebase Visualization.** Microservices architectures span multiple repositories. A federation layer would aggregate per-service organisms into a single interconnected graph, with network API calls appearing as cross-organism edges.

**Machine Learning Anomaly Detection.** Training a classifier on the malware marker feature vector (import signatures, pattern matches, complexity metrics) against a labeled corpus would produce probabilistic malware scores to complement the current rule-based system.

**Performance Profiling Overlay.** Integrating execution timing data from the tracer into the visualization as a heatmap layer, where node color intensity scales with cumulative execution time or call frequency, would combine structural health with runtime performance in a single view.

---

*Ghost_Logic Forensic Evidence Platform -- Instance 8 of 12*
*All claims trace to source files in `D:\lost_marbles\Code_Organism\`*
