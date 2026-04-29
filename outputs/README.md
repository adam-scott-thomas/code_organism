# Reference outputs

These are real outputs from running Code Organism on its own source tree (commit `f52b351`, 2026-04-29). Use them as a reference for what each subcommand produces.

| File | Subcommand | Size | Content |
|---|---|---|---|
| `example.analyze.summary.json` | `analyze` | 2 KB | Stats block + 5-node shape sample. (Full output is ~1.5 MB.) |
| `example.health.summary.json` | `health` | 4 KB | Health summary + top-10 unhealthy nodes. (Full output is ~930 KB.) |
| `example.communities.json` | `communities` | 29 KB | Full Leiden community detection — 39 communities across 3,254 nodes. |

## Reproduce

```bash
git clone https://github.com/adam-scott-thomas/code_organism.git
cd code_organism
pip install -e .
python -m Code_Organism.cli analyze     . --output json | head -40   # stats block
python -m Code_Organism.cli health      . --output json | head -40
python -m Code_Organism.cli communities . --output json
```

## What the numbers mean (snapshot)

From `example.analyze.summary.json`:

- **3,254 nodes** total — modules, classes, functions, methods, variables, references.
- **3,078 edges** — imports, calls, references, containment.
- **55 modules** — the file-level skeleton.
- **97 classes**, **605 functions** — the organ structure.
- **27,261 lines of code** including everything; the engine source is ~18K, the rest is tests + tools + examples.
- **6 circular dependencies** — flagged for refactor.
- **Average complexity 0.75** — most code is HEALTHY. **122 NECROTIC** (unreached by any call edge — usually demo entry points and test helpers).
