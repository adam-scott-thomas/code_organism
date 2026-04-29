# SPDX-License-Identifier: Apache-2.0
"""
Run the Code Organism demo.

This script demonstrates the Code Organism Visualizer by
analyzing the demo_target.py file and launching the 3D visualization.
"""

import sys
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from code_organism import Organism
from code_organism.renderer import render_organism


def main():
    print("Code Organism Visualizer Demo")
    print("=" * 50)

    # Analyze the demo target
    demo_file = Path(__file__).parent / "demo_target.py"

    print(f"\nAnalyzing: {demo_file.name}")

    organism = Organism.from_file(demo_file)

    # Print stats
    stats = organism.stats

    print(f"""
Analysis Results:
   Modules:     {stats.total_modules}
   Classes:     {stats.total_classes}
   Functions:   {stats.total_functions}
   Nodes:       {stats.total_nodes}
   Edges:       {stats.total_edges}
   Lines:       {stats.total_lines}

Health Report:
   Healthy:     {stats.healthy_nodes}
   Stressed:    {stats.stressed_nodes}
   Inflamed:    {stats.inflamed_nodes}
   Necrotic:    {stats.necrotic_nodes}
   Cancerous:   {stats.cancerous_nodes}

Complexity:
   Average:     {stats.avg_complexity:.2f}
   Maximum:     {stats.max_complexity}
""")

    # Find dead code
    dead_code = organism.find_dead_code()
    if dead_code:
        print("Dead Code Detected:")
        for node in dead_code:
            print(f"   {node.qualified_name}")
        print()

    # Find complexity hotspots
    hotspots = organism.find_complexity_hotspots(threshold=5)
    if hotspots:
        print("Complexity Hotspots:")
        for node in hotspots:
            print(f"   {node.qualified_name} (complexity: {node.metrics.cyclomatic_complexity})")
        print()

    # Launch visualization
    print("Launching 3D Visualization...")
    print("   Open your browser to see the organism!")
    print("   Press Ctrl+C to stop.\n")

    renderer = render_organism(organism)

    try:
        while True:
            import time
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down...")
        renderer.stop()


if __name__ == "__main__":
    main()
