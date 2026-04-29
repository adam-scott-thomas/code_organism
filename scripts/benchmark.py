# SPDX-License-Identifier: Apache-2.0
"""
Benchmark Code Organism's `analyze` pass against a few public Python repos.

Usage:
    python scripts/benchmark.py                 # benchmark default targets
    python scripts/benchmark.py /path/to/repo   # benchmark one specific path
    python scripts/benchmark.py --markdown      # emit a markdown table for the README

The script clones each target into a temp dir, runs `Organism.from_directory`,
and reports nodes parsed + wall time. It is deliberately simple — no warmup,
no statistical pass count — so the numbers are honest first-run measurements.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

# Default benchmark targets. Picked for variety: small/medium/large pure-Python.
DEFAULT_TARGETS: list[tuple[str, str]] = [
    ("requests",   "https://github.com/psf/requests.git"),
    ("flask",      "https://github.com/pallets/flask.git"),
    ("rich",       "https://github.com/Textualize/rich.git"),
    ("fastapi",    "https://github.com/fastapi/fastapi.git"),
]


@dataclass
class Result:
    name: str
    path: Path
    nodes: int
    edges: int
    py_files: int
    seconds: float

    def nodes_per_sec(self) -> float:
        return self.nodes / self.seconds if self.seconds else 0.0


def _clone(url: str, dest: Path) -> None:
    subprocess.run(
        ["git", "clone", "--depth", "1", "--quiet", url, str(dest)],
        check=True,
    )


def _benchmark_path(name: str, path: Path) -> Result:
    # Lazy import so importing this script doesn't pay parse cost
    from Code_Organism.model.organism import Organism

    py_files = sum(1 for _ in path.glob("**/*.py"))
    t0 = time.perf_counter()
    org = Organism.from_directory(path)
    elapsed = time.perf_counter() - t0
    return Result(
        name=name,
        path=path,
        nodes=len(org.nodes),
        edges=len(org.edges),
        py_files=py_files,
        seconds=elapsed,
    )


def _print_table(results: list[Result], markdown: bool) -> None:
    if markdown:
        print("| Project | .py files | Nodes | Edges | Time | Nodes/s |")
        print("|---|---:|---:|---:|---:|---:|")
        for r in results:
            print(
                f"| {r.name} | {r.py_files} | {r.nodes:,} | {r.edges:,} | "
                f"{r.seconds:.2f}s | {int(r.nodes_per_sec()):,} |"
            )
    else:
        print(f"{'Project':<12} {'Files':>6} {'Nodes':>8} {'Edges':>8} {'Time':>8} {'Nodes/s':>10}")
        print("-" * 60)
        for r in results:
            print(
                f"{r.name:<12} {r.py_files:>6} {r.nodes:>8,} {r.edges:>8,} "
                f"{r.seconds:>7.2f}s {int(r.nodes_per_sec()):>10,}"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path", nargs="?", default=None,
        help="Local path to benchmark instead of cloning the default targets",
    )
    parser.add_argument(
        "--markdown", action="store_true",
        help="Emit results as a Markdown table",
    )
    parser.add_argument(
        "--keep", action="store_true",
        help="Keep cloned repos in a persistent dir (./bench_targets)",
    )
    args = parser.parse_args()

    results: list[Result] = []

    if args.path:
        results.append(_benchmark_path(Path(args.path).name, Path(args.path)))
    else:
        bench_dir = Path("bench_targets") if args.keep else Path(tempfile.mkdtemp(prefix="codeorg_bench_"))
        bench_dir.mkdir(exist_ok=True)
        try:
            for name, url in DEFAULT_TARGETS:
                target_path = bench_dir / name
                if not target_path.exists():
                    print(f"Cloning {name} ...", file=sys.stderr)
                    _clone(url, target_path)
                print(f"Benchmarking {name} ...", file=sys.stderr)
                results.append(_benchmark_path(name, target_path))
        finally:
            if not args.keep and bench_dir.name.startswith("codeorg_bench_"):
                shutil.rmtree(bench_dir, ignore_errors=True)

    _print_table(results, args.markdown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
