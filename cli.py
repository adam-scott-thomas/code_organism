"""
CODE ORGANISM: Command Line Interface

Usage:
    python -m code_organism path/to/file.py
    python -m code_organism path/to/directory/
    python -m code_organism --export organism.json path/to/project/
    python -m code_organism --playback recording.corg.gz
"""

import argparse
import sys
from pathlib import Path

from .model import Organism
from .renderer import render_organism, render_organism_instanced, render_playback_file, render_solar_system


def main():
    parser = argparse.ArgumentParser(
        description="Code Organism Visualizer - See the soul of software",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s script.py                    Visualize a single file
  %(prog)s my_project/                  Visualize a whole directory
  %(prog)s --port 9000 script.py        Use custom port
  %(prog)s --export out.json .          Export organism data to JSON
  %(prog)s --stats script.py            Print stats without visualization
  %(prog)s --playback recording.corg.gz Play back a recorded session
  %(prog)s --malware-scan script.py     Scan for malware patterns
        """,
    )

    parser.add_argument(
        "target",
        type=str,
        nargs="?",
        help="Python file or directory to analyze",
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port for visualization server (default: 8765)",
    )

    parser.add_argument(
        "--export",
        type=str,
        metavar="FILE",
        help="Export organism data to JSON file",
    )

    parser.add_argument(
        "--stats",
        action="store_true",
        help="Print statistics and exit (no visualization)",
    )

    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="Don't automatically open browser",
    )

    parser.add_argument(
        "--pattern",
        type=str,
        default="**/*.py",
        help="Glob pattern for files (default: **/*.py)",
    )

    parser.add_argument(
        "--playback",
        type=str,
        metavar="FILE",
        help="Play back a recorded session (.corg or .corg.gz file)",
    )

    parser.add_argument(
        "--malware-scan",
        action="store_true",
        help="Scan for malware patterns and suspicious code",
    )

    parser.add_argument(
        "--complexity",
        action="store_true",
        help="Show detailed complexity analysis",
    )

    parser.add_argument(
        "--instanced",
        action="store_true",
        help="Use GPU-instanced renderer for large codebases (1000+ nodes)",
    )

    parser.add_argument(
        "--max-level",
        type=int,
        default=2,
        help="Maximum cluster detail level for instanced renderer (0-4, default: 2)",
    )

    parser.add_argument(
        "--solar",
        action="store_true",
        help="Use solar system navigation (click-to-expand cosmic hierarchy)",
    )

    args = parser.parse_args()

    # Handle playback mode
    if args.playback:
        return run_playback(args)

    # Require target for other modes
    if not args.target:
        parser.print_help()
        sys.exit(1)

    target = Path(args.target)

    if not target.exists():
        print(f"Error: '{target}' does not exist")
        sys.exit(1)

    # Handle malware scan
    if args.malware_scan:
        return run_malware_scan(target, args)

    # Handle complexity analysis
    if args.complexity:
        return run_complexity_analysis(target, args)

    # Analyze
    print(f"Analyzing {'directory' if target.is_dir() else 'file'}: {target}")

    try:
        if target.is_dir():
            organism = Organism.from_directory(target, pattern=args.pattern)
        else:
            organism = Organism.from_file(target)
    except Exception as e:
        print(f"Error analyzing code: {e}")
        sys.exit(1)

    # Print stats
    stats = organism.stats
    print(f"""
+--------------------------------------------------------------+
|                    ORGANISM ANALYSIS                          |
+--------------------------------------------------------------+
|  Name:           {organism.name:42} |
|  Modules:        {stats.total_modules:42} |
|  Classes:        {stats.total_classes:42} |
|  Functions:      {stats.total_functions:42} |
|  Total Nodes:    {stats.total_nodes:42} |
|  Connections:    {stats.total_edges:42} |
|  Lines of Code:  {stats.total_lines:42} |
+--------------------------------------------------------------+
|  COMPLEXITY                                                   |
+--------------------------------------------------------------+
|  Avg Complexity: {stats.avg_complexity:42.2f} |
|  Max Complexity: {stats.max_complexity:42} |
|  Max Depth:      {stats.max_depth:42} |
|  Circular Deps:  {stats.circular_dependencies:42} |
+--------------------------------------------------------------+
|  HEALTH                                                       |
+--------------------------------------------------------------+
|  Healthy:        {stats.healthy_nodes:42} |
|  Stressed:       {stats.stressed_nodes:42} |
|  Inflamed:       {stats.inflamed_nodes:42} |
|  Necrotic:       {stats.necrotic_nodes:42} |
|  Cancerous:      {stats.cancerous_nodes:42} |
+--------------------------------------------------------------+
""")

    # Report hotspots
    if stats.complexity_hotspots:
        print("Complexity Hotspots:")
        for hotspot in stats.complexity_hotspots[:5]:
            print(f"   - {hotspot}")
        print()

    # Report dead code
    dead_code = organism.find_dead_code()
    if dead_code:
        print(f"Dead Code ({len(dead_code)} items):")
        for node in dead_code[:5]:
            print(f"   - {node.qualified_name}")
        if len(dead_code) > 5:
            print(f"   ... and {len(dead_code) - 5} more")
        print()

    # Report circular dependencies
    circles = organism.find_circular_dependencies()
    if circles:
        print(f"Circular Dependencies ({len(circles)} cycles):")
        for cycle in circles[:3]:
            cycle_str = " -> ".join(cycle[:5])
            if len(cycle) > 5:
                cycle_str += " -> ..."
            print(f"   - {cycle_str}")
        print()

    # Export if requested
    if args.export:
        export_path = Path(args.export)
        organism.save(export_path)
        print(f"Exported to: {export_path}")

    # Visualize unless --stats
    if not args.stats:
        if args.solar:
            # Solar system navigation mode
            print("Launching solar system navigation...")
            print("  Click on cosmic bodies to explore deeper")
            print("  Use breadcrumbs to navigate back")
            renderer = render_solar_system(
                organism,
                port=args.port,
                open_browser=not args.no_browser,
            )
        elif args.instanced or stats.total_nodes > 5000:
            # GPU-instanced mode for large codebases
            print(f"Launching GPU-instanced visualization (level {args.max_level})...")
            print("  Using hierarchical clustering for large-scale rendering")
            renderer = render_organism_instanced(
                organism,
                port=args.port,
                open_browser=not args.no_browser,
                max_level=args.max_level,
            )
        else:
            print("Launching 3D visualization...")
            renderer = render_organism(
                organism,
                port=args.port,
                open_browser=not args.no_browser,
            )

        try:
            print("\n   Press Ctrl+C to stop the server\n")
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down...")
            renderer.stop()


def run_playback(args):
    """Run playback mode."""
    filepath = Path(args.playback)

    if not filepath.exists():
        print(f"Error: Recording file '{filepath}' does not exist")
        sys.exit(1)

    print(f"Loading recording: {filepath}")

    try:
        renderer = render_playback_file(
            filepath,
            port=args.port,
            open_browser=not args.no_browser,
        )

        print("\n   Press Ctrl+C to stop the server\n")
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        renderer.stop()


def run_malware_scan(target: Path, args):
    """Run malware pattern scan."""
    from .health import analyze_for_malware

    print(f"Scanning for malware patterns: {target}")
    print()

    if target.is_file():
        files = [target]
    else:
        files = list(target.glob(args.pattern))

    total_markers = 0
    critical_count = 0

    for filepath in files:
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                source = f.read()

            result = analyze_for_malware(source, str(filepath))

            if result.markers:
                print(f"\n[!] {filepath}")
                for marker in result.markers:
                    severity_icon = {
                        "critical": "[CRITICAL]",
                        "high": "[HIGH]",
                        "medium": "[MEDIUM]",
                        "low": "[low]",
                    }.get(marker.severity.value, "[ ]")

                    print(f"    {severity_icon} {marker.description}")
                    print(f"        Location: {marker.location}")
                    if marker.code_snippet:
                        print(f"        Code: {marker.code_snippet[:60]}...")

                    total_markers += 1
                    if marker.severity.value == "critical":
                        critical_count += 1

        except Exception as e:
            print(f"Error scanning {filepath}: {e}")

    print()
    print(f"Scan complete: {len(files)} files scanned")
    print(f"Findings: {total_markers} suspicious patterns")
    if critical_count:
        print(f"[!] CRITICAL: {critical_count} critical issues found!")


def run_complexity_analysis(target: Path, args):
    """Run detailed complexity analysis."""
    from .health import analyze_complexity

    print(f"Analyzing complexity: {target}")
    print()

    if target.is_file():
        files = [target]
    else:
        files = list(target.glob(args.pattern))

    all_functions = []

    for filepath in files:
        try:
            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                source = f.read()

            report = analyze_complexity(source, str(filepath))
            all_functions.extend(report.functions)

        except Exception as e:
            print(f"Error analyzing {filepath}: {e}")

    # Sort by complexity
    all_functions.sort(key=lambda f: f.cyclomatic, reverse=True)

    print("+--------------------------------------------------------------+")
    print("|                    COMPLEXITY REPORT                          |")
    print("+--------------------------------------------------------------+")
    print(f"| Total functions analyzed: {len(all_functions):33} |")
    print("+--------------------------------------------------------------+")
    print()

    if all_functions:
        avg_cyclomatic = sum(f.cyclomatic for f in all_functions) / len(all_functions)
        avg_cognitive = sum(f.cognitive for f in all_functions) / len(all_functions)
        avg_maintainability = sum(f.maintainability_index for f in all_functions) / len(all_functions)

        print(f"Average Cyclomatic Complexity: {avg_cyclomatic:.2f}")
        print(f"Average Cognitive Complexity:  {avg_cognitive:.2f}")
        print(f"Average Maintainability Index: {avg_maintainability:.2f}")
        print()

        print("Top 10 Most Complex Functions:")
        print("-" * 70)
        for func in all_functions[:10]:
            print(f"  {func.name:30} CC={func.cyclomatic:3}  COG={func.cognitive:3}  MI={func.maintainability_index:.1f}")
            print(f"    {func.location}")
        print()


if __name__ == "__main__":
    main()
