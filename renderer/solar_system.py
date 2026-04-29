# SPDX-License-Identifier: Apache-2.0
"""
CODE ORGANISM: SOLAR SYSTEM NAVIGATOR

Hierarchical code visualization using a cosmic metaphor:
- Universe = Entire codebase
- Galaxies = Major packages/subsystems
- Star Systems = Modules/files
- Stars = Classes
- Planets = Functions/methods
- Moons = Nested functions, variables

Click to drill down, breadcrumb to navigate back.
Only renders ~50-200 objects at any time for smooth performance.
"""

from __future__ import annotations

import http.server
import json
import os
import socketserver
import tempfile
import threading
import webbrowser
from pathlib import Path
from urllib.parse import urlparse

from ..model.organism import Organism


class SolarSystemRenderer:
    """
    Renders code as a navigable solar system.

    Click galaxies to zoom into star systems, click stars to see planets.
    Only the current "view" is rendered - never the whole codebase.
    """

    def __init__(self, organism: Organism, port: int = 8765, bind: str = "127.0.0.1"):
        self.organism = organism
        self.port = port
        self.bind = bind
        self.server: socketserver.TCPServer | None = None
        self.server_thread: threading.Thread | None = None
        self.temp_dir: str | None = None

        # Pre-compute hierarchy
        self._hierarchy = None
        self._build_hierarchy()

    def _build_hierarchy(self) -> None:
        """Build the cosmic hierarchy from DIRECTORY structure."""
        # Build a tree based on actual file paths, not code connectivity
        self._directory_tree = {}  # path -> {children: [], nodes: [], info: {}}
        self._path_to_id = {}  # path -> unique ID
        self._id_to_path = {}  # unique ID -> path
        self._id_counter = 0

        # Only include structural nodes with valid file positions
        for node_id, node in self.organism.nodes.items():
            # Skip non-structural nodes (variables, parameters, externals, builtins)
            if hasattr(node, 'node_type') and node.node_type.value not in (
                'module', 'class', 'function', 'method', 'package'
            ):
                continue

            position = getattr(node, 'position', None)
            if position and hasattr(position, 'file') and position.file:
                file_path = str(position.file).replace('\\', '/')
            elif hasattr(node, 'qualified_name') and '.' in node.qualified_name:
                # Only use qualified_name if it looks like a real dotted path
                file_path = node.qualified_name.replace('.', '/')
            else:
                # Skip nodes without a valid file path
                continue

            # Split into directory parts
            parts = file_path.split('/')

            # Build tree structure
            current_path = ''
            for i, part in enumerate(parts[:-1]):  # Exclude filename
                parent_path = current_path
                current_path = f"{current_path}/{part}" if current_path else part

                if current_path not in self._directory_tree:
                    self._directory_tree[current_path] = {
                        'name': part,
                        'path': current_path,
                        'parent': parent_path if parent_path else None,
                        'children': set(),  # Child directories
                        'files': set(),  # Files in this directory
                        'nodes': [],  # Code nodes
                        'depth': i,
                    }
                    # Assign unique ID
                    self._id_counter += 1
                    uid = f"dir_{self._id_counter}"
                    self._path_to_id[current_path] = uid
                    self._id_to_path[uid] = current_path

                # Link to parent
                if parent_path and parent_path in self._directory_tree:
                    self._directory_tree[parent_path]['children'].add(current_path)

            # Add file (last part before .py)
            file_name = parts[-1] if parts else 'unknown'
            file_key = f"{current_path}/{file_name}" if current_path else file_name

            if file_key not in self._directory_tree:
                self._directory_tree[file_key] = {
                    'name': file_name.replace('.py', ''),
                    'path': file_key,
                    'parent': current_path if current_path else None,
                    'children': set(),
                    'files': set(),
                    'nodes': [],
                    'depth': len(parts) - 1,
                    'is_file': True,
                }
                self._id_counter += 1
                uid = f"file_{self._id_counter}"
                self._path_to_id[file_key] = uid
                self._id_to_path[uid] = file_key

                if current_path and current_path in self._directory_tree:
                    self._directory_tree[current_path]['files'].add(file_key)

            # Add node to file
            self._directory_tree[file_key]['nodes'].append(node_id)

        # Convert sets to lists for JSON serialization
        for info in self._directory_tree.values():
            info['children'] = list(info['children'])
            info['files'] = list(info['files'])

        # Find a sensible root level. When paths are absolute (D:/foo/bar/...),
        # we want to find the common prefix and use the first level below it as roots.
        all_paths = list(self._directory_tree.keys())
        if not all_paths:
            self._roots = []
            return

        # Find the longest common prefix among all directory paths
        # (strip the path down to the project root)
        dir_paths = [p for p, info in self._directory_tree.items() if not info.get('is_file')]
        if dir_paths:
            prefix_parts = dir_paths[0].split('/')
            for dp in dir_paths[1:]:
                other_parts = dp.split('/')
                common_len = 0
                for a, b in zip(prefix_parts, other_parts, strict=False):
                    if a == b:
                        common_len += 1
                    else:
                        break
                prefix_parts = prefix_parts[:common_len]
            common_prefix = '/'.join(prefix_parts)
        else:
            common_prefix = ''

        # The roots are direct children of the common prefix
        self._roots = []
        for path, info in self._directory_tree.items():
            if info.get('is_file'):
                continue
            parent = info.get('parent', '')
            # A root is a directory whose parent IS the common prefix
            if parent == common_prefix:
                total_nodes = self._count_nodes_in_tree(path)
                if total_nodes > 0:  # Skip empty directories
                    self._roots.append(path)

        # If no roots found (single-directory project), use common prefix itself
        if not self._roots and common_prefix in self._directory_tree:
            self._roots = [common_prefix]

        # If there's only one root, drill down to its children for a more useful view
        while len(self._roots) == 1:
            only_root = self._roots[0]
            info = self._directory_tree.get(only_root, {})
            children_dirs = [c for c in info.get('children', [])
                             if not self._directory_tree.get(c, {}).get('is_file')
                             and self._count_nodes_in_tree(c) > 0]
            if len(children_dirs) >= 2:
                # This root has multiple meaningful children — use them as roots
                self._roots = children_dirs
                break
            elif len(children_dirs) == 1:
                # Single child — drill down further
                self._roots = children_dirs
            else:
                # No children dirs, keep this as the only root
                break

    def _count_nodes_in_tree(self, path: str) -> int:
        """Count nodes recursively for filtering."""
        info = self._directory_tree.get(path, {})
        count = len(info.get('nodes', []))
        for child in info.get('children', []):
            count += self._count_nodes_in_tree(child)
        for f in info.get('files', []):
            finfo = self._directory_tree.get(f, {})
            count += len(finfo.get('nodes', []))
        return count

    def render(self, open_browser: bool = True) -> str:
        """Start the visualization server."""
        self.temp_dir = tempfile.mkdtemp(prefix="code_organism_solar_")

        # Generate HTML
        html_content = self._generate_html()
        html_path = Path(self.temp_dir) / "index.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        # Start server
        self._start_server()

        url = f"http://localhost:{self.port}"
        if open_browser:
            webbrowser.open(url)

        return url

    def _start_server(self) -> None:
        """Start HTTP server with API endpoints."""
        os.chdir(self.temp_dir)

        org = self.organism
        directory_tree = self._directory_tree
        path_to_id = self._path_to_id
        id_to_path = self._id_to_path
        roots = self._roots

        class APIHandler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                parsed = urlparse(self.path)

                if parsed.path == '/api/universe':
                    # Top level - root directories (your projects)
                    self._serve_json(self._get_universe())
                elif parsed.path.startswith('/api/expand/'):
                    # Expand a directory or file to see its contents
                    node_id = parsed.path.split('/')[-1]
                    self._serve_json(self._get_children(node_id))
                elif parsed.path == '/api/stats':
                    self._serve_json({
                        'total_nodes': len(org.nodes),
                        'total_edges': len(org.edges),
                        'directories': len([p for p in directory_tree if not directory_tree[p].get('is_file')]),
                        'files': len([p for p in directory_tree if directory_tree[p].get('is_file')]),
                    })
                else:
                    super().do_GET()

            def _get_universe(self) -> dict:
                """Get top-level view - your project directories."""
                import math

                nodes = []
                # Use roots as galaxies
                n_roots = max(len(roots), 1)
                for i, root_path in enumerate(roots):
                    info = directory_tree[root_path]
                    uid = path_to_id[root_path]

                    total = self._count_nodes_recursive(root_path)
                    health = self._calculate_health(root_path)

                    # Fibonacci sphere distribution for true 3D
                    x, y, z = self._fibonacci_sphere_point(i, n_roots, radius=40)

                    nodes.append({
                        'id': uid,
                        'name': info['name'],
                        'type': 'galaxy',
                        'size': 2 + math.log10(max(1, total)) * 0.8,
                        'total_nodes': total,
                        'health': health,
                        'expandable': True,
                        'x': x,
                        'y': y,
                        'z': z,
                    })

                return {
                    'nodes': nodes,
                    'edges': [],
                    'level_name': 'Universe',
                }

            def _get_children(self, parent_id: str) -> dict:
                """Get children of a directory."""
                import math

                # Find the path for this ID
                if parent_id not in id_to_path:
                    return {'nodes': [], 'edges': [], 'level_name': 'Not Found'}

                parent_path = id_to_path[parent_id]
                parent_info = directory_tree.get(parent_path, {})

                nodes = []
                child_dirs = parent_info.get('children', [])
                child_files = parent_info.get('files', [])
                child_nodes = parent_info.get('nodes', [])

                # If this is a file, show its code nodes (classes, functions)
                if parent_info.get('is_file') and child_nodes:
                    return self._get_code_nodes(child_nodes, parent_info['name'])

                # Otherwise, show child directories and files
                all_children = child_dirs + child_files
                total_items = len(all_children)

                for i, child_path in enumerate(all_children):
                    child_info = directory_tree.get(child_path, {})
                    if not child_info:
                        continue

                    uid = path_to_id.get(child_path)
                    if not uid:
                        continue

                    is_file = child_info.get('is_file', False)
                    total = self._count_nodes_recursive(child_path)
                    health = self._calculate_health(child_path)

                    # Determine cosmic type based on what it is
                    if is_file:
                        cosmic_type = 'star'  # Files are stars
                    elif child_info.get('depth', 0) == 0:
                        cosmic_type = 'galaxy'  # Top-level dirs are galaxies
                    else:
                        cosmic_type = 'star_system'  # Subdirs are star systems

                    # Fibonacci sphere distribution
                    x, y, z = self._fibonacci_sphere_point(i, total_items, radius=25 + total_items * 0.8)

                    # Check if expandable
                    has_children = bool(child_info.get('children') or child_info.get('files') or child_info.get('nodes'))

                    nodes.append({
                        'id': uid,
                        'name': child_info['name'],
                        'type': cosmic_type,
                        'code_type': 'file' if is_file else 'directory',
                        'size': 1.5 + math.log10(max(1, total)) * 0.5,
                        'total_nodes': total,
                        'health': health,
                        'expandable': has_children,
                        'x': x,
                        'y': y,
                        'z': z,
                    })

                level_name = 'Star System' if parent_info.get('depth', 0) > 0 else 'Galaxy'

                return {
                    'nodes': nodes,
                    'edges': [],
                    'level_name': level_name,
                }

            def _get_code_nodes(self, node_ids: list, file_name: str) -> dict:
                """Get actual code nodes (classes, functions, etc.)."""

                nodes_dict = {nid: org.nodes[nid] for nid in node_ids if nid in org.nodes}

                # Get edges between these nodes
                edges_list = []
                for eid, edge in org.edges.items():
                    if edge.source_id in nodes_dict and edge.target_id in nodes_dict:
                        edges_list.append({
                            'id': eid,
                            'source': edge.source_id,
                            'target': edge.target_id,
                        })

                # Simple circular layout
                nodes = []
                total = len(nodes_dict)
                for i, (nid, node) in enumerate(nodes_dict.items()):
                    node_type = node.node_type.value if hasattr(node.node_type, 'value') else str(node.node_type)

                    # Map to cosmic type
                    cosmic_type = {
                        'module': 'star',
                        'class': 'planet',
                        'function': 'moon',
                        'method': 'asteroid',
                    }.get(node_type, 'asteroid')

                    x, y, z = self._fibonacci_sphere_point(i, total, radius=15 + total * 0.3)

                    health = node.health.value if hasattr(node.health, 'value') else str(node.health)

                    nodes.append({
                        'id': nid,
                        'name': node.name,
                        'type': cosmic_type,
                        'code_type': node_type,
                        'size': node.size * 0.8,
                        'health': health,
                        'expandable': False,
                        'x': x,
                        'y': y,
                        'z': z,
                    })

                return {
                    'nodes': nodes,
                    'edges': edges_list,
                    'level_name': f'File: {file_name}',
                    'is_leaf': True,
                }

            @staticmethod
            def _fibonacci_sphere_point(index: int, total: int, radius: float = 30) -> tuple:
                """Distribute points on a sphere using Fibonacci spiral."""
                import math
                if total <= 1:
                    return (0, 0, 0)
                golden_ratio = (1 + math.sqrt(5)) / 2
                theta = 2 * math.pi * index / golden_ratio
                phi = math.acos(1 - 2 * (index + 0.5) / total)
                x = radius * math.sin(phi) * math.cos(theta)
                y = radius * math.cos(phi)
                z = radius * math.sin(phi) * math.sin(theta)
                return (round(x, 2), round(y, 2), round(z, 2))

            def _count_nodes_recursive(self, path: str) -> int:
                """Count all code nodes under a path."""
                info = directory_tree.get(path, {})
                count = len(info.get('nodes', []))

                for child in info.get('children', []):
                    count += self._count_nodes_recursive(child)
                for file_path in info.get('files', []):
                    file_info = directory_tree.get(file_path, {})
                    count += len(file_info.get('nodes', []))

                return count

            def _calculate_health(self, path: str) -> str:
                """Calculate dominant health for a path."""
                health_counts = {'healthy': 0, 'stressed': 0, 'inflamed': 0, 'necrotic': 0, 'cancerous': 0}

                def count_health(p):
                    pinfo = directory_tree.get(p, {})
                    for nid in pinfo.get('nodes', []):
                        if nid in org.nodes:
                            h = org.nodes[nid].health
                            hv = h.value if hasattr(h, 'value') else str(h)
                            if hv in health_counts:
                                health_counts[hv] += 1
                    for child in pinfo.get('children', []):
                        count_health(child)
                    for fp in pinfo.get('files', []):
                        count_health(fp)

                count_health(path)

                if sum(health_counts.values()) == 0:
                    return 'healthy'
                return max(health_counts, key=health_counts.get)

            def _serve_json(self, data: dict):
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(data).encode())

            def log_message(self, format, *args):
                pass

        socketserver.TCPServer.allow_reuse_address = True
        self.server = socketserver.TCPServer((self.bind, self.port), APIHandler)
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.start()

        print(f"Code Organism Solar System running at http://localhost:{self.port}")
        print("   Click on galaxies to explore!")
        print("   Press Ctrl+C to stop")

    def stop(self) -> None:
        """Stop the server."""
        if self.server:
            self.server.shutdown()

    def _generate_html(self) -> str:
        """Generate the solar system visualization HTML."""
        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Code Organism: {self.organism.name} - Solar System View</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: #000010;
            overflow: hidden;
            font-family: 'Segoe UI', system-ui, sans-serif;
            color: #fff;
        }}

        #canvas-container {{ width: 100vw; height: 100vh; }}

        /* Breadcrumb navigation */
        #breadcrumb {{
            position: fixed;
            top: 20px;
            left: 20px;
            z-index: 1000;
            display: flex;
            gap: 8px;
            align-items: center;
            font-size: 14px;
        }}

        .breadcrumb-item {{
            background: rgba(100, 150, 255, 0.2);
            border: 1px solid rgba(100, 150, 255, 0.4);
            padding: 6px 12px;
            border-radius: 20px;
            cursor: pointer;
            transition: all 0.2s;
        }}

        .breadcrumb-item:hover {{
            background: rgba(100, 150, 255, 0.4);
        }}

        .breadcrumb-separator {{
            color: rgba(255,255,255,0.4);
        }}

        /* Info panel */
        #info-panel {{
            position: fixed;
            top: 20px;
            right: 20px;
            background: rgba(0, 10, 30, 0.9);
            border: 1px solid rgba(100, 150, 255, 0.3);
            border-radius: 12px;
            padding: 16px;
            min-width: 250px;
            z-index: 1000;
        }}

        #info-panel h3 {{
            margin-bottom: 12px;
            color: #8af;
        }}

        #info-panel .stat {{
            display: flex;
            justify-content: space-between;
            margin: 6px 0;
            color: rgba(255,255,255,0.7);
        }}

        #info-panel .stat-value {{
            color: #fff;
            font-weight: 500;
        }}

        /* Loading indicator */
        #loading {{
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            font-size: 18px;
            color: #8af;
            z-index: 2000;
        }}

        #loading.hidden {{ display: none; }}

        /* Instructions */
        #instructions {{
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(0, 10, 30, 0.8);
            padding: 12px 24px;
            border-radius: 8px;
            font-size: 13px;
            color: rgba(255,255,255,0.6);
            z-index: 1000;
        }}

        /* Tooltip */
        #tooltip {{
            position: fixed;
            background: rgba(0, 20, 50, 0.95);
            border: 1px solid rgba(100, 150, 255, 0.5);
            padding: 10px 14px;
            border-radius: 8px;
            pointer-events: none;
            z-index: 3000;
            display: none;
            max-width: 300px;
        }}

        #tooltip .name {{
            font-weight: 600;
            color: #8cf;
            margin-bottom: 4px;
        }}

        #tooltip .type {{
            font-size: 12px;
            color: rgba(255,255,255,0.5);
            text-transform: uppercase;
        }}

        #tooltip .detail {{
            margin-top: 6px;
            font-size: 13px;
            color: rgba(255,255,255,0.7);
        }}
    </style>
</head>
<body>
    <div id="canvas-container"></div>

    <div id="breadcrumb">
        <div class="breadcrumb-item" data-id="root">{self.organism.name}</div>
    </div>

    <div id="info-panel">
        <h3>Code Universe</h3>
        <div class="stat">
            <span>Total Nodes</span>
            <span class="stat-value" id="stat-nodes">-</span>
        </div>
        <div class="stat">
            <span>Current View</span>
            <span class="stat-value" id="stat-view">Universe</span>
        </div>
        <div class="stat">
            <span>Visible Objects</span>
            <span class="stat-value" id="stat-visible">-</span>
        </div>
    </div>

    <div id="loading">Loading universe...</div>

    <div id="instructions">
        Click on objects to explore inside | Scroll to zoom | Drag to rotate
    </div>

    <div id="tooltip">
        <div class="name"></div>
        <div class="type"></div>
        <div class="detail"></div>
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>

    <script>
        // Scene setup
        const container = document.getElementById('canvas-container');
        const scene = new THREE.Scene();
        const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 0.1, 10000);
        const renderer = new THREE.WebGLRenderer({{ antialias: true, alpha: true }});

        renderer.setSize(window.innerWidth, window.innerHeight);
        renderer.setPixelRatio(window.devicePixelRatio);
        container.appendChild(renderer.domElement);

        // Controls
        const controls = new THREE.OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.05;
        controls.minDistance = 5;
        controls.maxDistance = 500;

        // Lighting
        const ambientLight = new THREE.AmbientLight(0x404060, 0.5);
        scene.add(ambientLight);

        const pointLight = new THREE.PointLight(0xffffff, 1, 1000);
        pointLight.position.set(0, 50, 50);
        scene.add(pointLight);

        // Star field background
        function createStarfield() {{
            const geometry = new THREE.BufferGeometry();
            const vertices = [];
            for (let i = 0; i < 5000; i++) {{
                vertices.push(
                    (Math.random() - 0.5) * 2000,
                    (Math.random() - 0.5) * 2000,
                    (Math.random() - 0.5) * 2000
                );
            }}
            geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
            const material = new THREE.PointsMaterial({{ color: 0xffffff, size: 0.5, transparent: true, opacity: 0.6 }});
            return new THREE.Points(geometry, material);
        }}
        scene.add(createStarfield());

        // State
        let currentNodes = [];
        let currentEdges = [];
        let meshes = [];
        let edgeLines = null;
        let navigationStack = [];

        // Color map for health
        const healthColors = {{
            'healthy': 0x44ff88,
            'stressed': 0xffff44,
            'inflamed': 0xff8844,
            'necrotic': 0x666666,
            'cancerous': 0xff4444
        }};

        // Cosmic type geometries
        const geometries = {{
            'galaxy': new THREE.IcosahedronGeometry(1, 1),
            'star_system': new THREE.OctahedronGeometry(1, 0),
            'star': new THREE.SphereGeometry(1, 16, 16),
            'planet': new THREE.SphereGeometry(1, 12, 12),
            'moon': new THREE.SphereGeometry(1, 8, 8),
            'asteroid': new THREE.TetrahedronGeometry(1, 0),
        }};

        // Create glow effect
        function createGlow(color, size) {{
            const spriteMaterial = new THREE.SpriteMaterial({{
                map: createGlowTexture(),
                color: color,
                transparent: true,
                blending: THREE.AdditiveBlending,
                opacity: 0.4
            }});
            const sprite = new THREE.Sprite(spriteMaterial);
            sprite.scale.set(size * 3, size * 3, 1);
            return sprite;
        }}

        function createGlowTexture() {{
            const canvas = document.createElement('canvas');
            canvas.width = 64;
            canvas.height = 64;
            const ctx = canvas.getContext('2d');
            const gradient = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
            gradient.addColorStop(0, 'rgba(255,255,255,1)');
            gradient.addColorStop(0.3, 'rgba(255,255,255,0.5)');
            gradient.addColorStop(1, 'rgba(255,255,255,0)');
            ctx.fillStyle = gradient;
            ctx.fillRect(0, 0, 64, 64);
            const texture = new THREE.CanvasTexture(canvas);
            return texture;
        }}

        // Load and display nodes
        async function loadUniverse() {{
            showLoading(true);
            try {{
                const response = await fetch('/api/universe');
                const data = await response.json();
                displayNodes(data);
                updateBreadcrumb([{{ id: 'root', name: '{self.organism.name}' }}]);

                // Get stats
                const statsResp = await fetch('/api/stats');
                const stats = await statsResp.json();
                document.getElementById('stat-nodes').textContent = stats.total_nodes.toLocaleString();
            }} catch (e) {{
                console.error('Failed to load universe:', e);
            }}
            showLoading(false);
        }}

        async function expandNode(nodeId, nodeName) {{
            showLoading(true);
            try {{
                const response = await fetch(`/api/expand/${{nodeId}}`);
                const data = await response.json();

                if (data.nodes && data.nodes.length > 0) {{
                    // Save current state for back navigation
                    navigationStack.push({{
                        nodes: currentNodes,
                        edges: currentEdges,
                    }});

                    displayNodes(data);

                    // Update breadcrumb
                    const breadcrumb = document.getElementById('breadcrumb');
                    const items = breadcrumb.querySelectorAll('.breadcrumb-item');
                    const currentPath = Array.from(items).map(item => ({{
                        id: item.dataset.id,
                        name: item.textContent
                    }}));
                    currentPath.push({{ id: nodeId, name: nodeName }});
                    updateBreadcrumb(currentPath);
                }}
            }} catch (e) {{
                console.error('Failed to expand node:', e);
            }}
            showLoading(false);
        }}

        function displayNodes(data) {{
            // Clear existing
            meshes.forEach(m => scene.remove(m));
            meshes = [];
            if (edgeLines) {{
                scene.remove(edgeLines);
                edgeLines = null;
            }}

            currentNodes = data.nodes || [];
            currentEdges = data.edges || [];

            // Create meshes for nodes
            currentNodes.forEach(node => {{
                const geometry = geometries[node.type] || geometries['asteroid'];
                const color = healthColors[node.health] || 0x8888ff;

                const material = new THREE.MeshPhongMaterial({{
                    color: color,
                    emissive: color,
                    emissiveIntensity: 0.3,
                    shininess: 50,
                }});

                const mesh = new THREE.Mesh(geometry, material);
                mesh.position.set(node.x || 0, node.y || 0, node.z || 0);

                const size = (node.size || 1) * (node.type === 'galaxy' ? 1.5 : 1);
                mesh.scale.set(size, size, size);

                mesh.userData = {{ ...node, size: size }};
                scene.add(mesh);
                meshes.push(mesh);

                // Add glow for expandable nodes
                if (node.expandable) {{
                    const glow = createGlow(color, size);
                    glow.position.copy(mesh.position);
                    scene.add(glow);
                    meshes.push(glow);
                }}
            }});

            // Create edges
            if (currentEdges.length > 0) {{
                const positions = [];
                const colors = [];

                currentEdges.forEach(edge => {{
                    const source = currentNodes.find(n => n.id === edge.source);
                    const target = currentNodes.find(n => n.id === edge.target);

                    if (source && target) {{
                        positions.push(source.x, source.y, source.z);
                        positions.push(target.x, target.y, target.z);

                        // Dim edge color
                        colors.push(0.3, 0.4, 0.6);
                        colors.push(0.3, 0.4, 0.6);
                    }}
                }});

                const geometry = new THREE.BufferGeometry();
                geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
                geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));

                const material = new THREE.LineBasicMaterial({{
                    vertexColors: true,
                    transparent: true,
                    opacity: 0.3,
                }});

                edgeLines = new THREE.LineSegments(geometry, material);
                scene.add(edgeLines);
            }}

            // Update stats
            document.getElementById('stat-view').textContent = data.level_name || 'View';
            document.getElementById('stat-visible').textContent = currentNodes.length;

            // Fit camera to scene
            fitCameraToScene();

            // Initialize force simulation for new nodes
            initForceState();
        }}

        function fitCameraToScene() {{
            if (currentNodes.length === 0) return;

            let minX = Infinity, maxX = -Infinity;
            let minY = Infinity, maxY = -Infinity;
            let minZ = Infinity, maxZ = -Infinity;

            currentNodes.forEach(node => {{
                minX = Math.min(minX, node.x || 0);
                maxX = Math.max(maxX, node.x || 0);
                minY = Math.min(minY, node.y || 0);
                maxY = Math.max(maxY, node.y || 0);
                minZ = Math.min(minZ, node.z || 0);
                maxZ = Math.max(maxZ, node.z || 0);
            }});

            const centerX = (minX + maxX) / 2;
            const centerY = (minY + maxY) / 2;
            const centerZ = (minZ + maxZ) / 2;

            const size = Math.max(maxX - minX, maxY - minY, maxZ - minZ);
            const distance = size * 1.5 + 20;

            camera.position.set(centerX, centerY + distance * 0.3, centerZ + distance);
            controls.target.set(centerX, centerY, centerZ);
            controls.update();
        }}

        function updateBreadcrumb(path) {{
            const breadcrumb = document.getElementById('breadcrumb');
            breadcrumb.innerHTML = '';

            path.forEach((item, index) => {{
                if (index > 0) {{
                    const sep = document.createElement('span');
                    sep.className = 'breadcrumb-separator';
                    sep.textContent = '>';
                    breadcrumb.appendChild(sep);
                }}

                const crumb = document.createElement('div');
                crumb.className = 'breadcrumb-item';
                crumb.textContent = item.name;
                crumb.dataset.id = item.id;
                crumb.dataset.index = index;

                crumb.addEventListener('click', () => {{
                    navigateToBreadcrumb(index);
                }});

                breadcrumb.appendChild(crumb);
            }});
        }}

        function navigateToBreadcrumb(index) {{
            // Navigate back to a previous level
            if (index === 0) {{
                navigationStack = [];
                loadUniverse();
            }} else {{
                // Pop back to the right level
                while (navigationStack.length > index) {{
                    navigationStack.pop();
                }}

                if (navigationStack.length > 0) {{
                    const state = navigationStack[navigationStack.length - 1];
                    displayNodes({{ nodes: state.nodes, edges: state.edges }});
                }} else {{
                    loadUniverse();
                }}
            }}

            // Update breadcrumb
            const breadcrumb = document.getElementById('breadcrumb');
            const items = breadcrumb.querySelectorAll('.breadcrumb-item');
            const newPath = [];
            for (let i = 0; i <= index; i++) {{
                newPath.push({{
                    id: items[i].dataset.id,
                    name: items[i].textContent
                }});
            }}
            updateBreadcrumb(newPath);
        }}

        function showLoading(show) {{
            document.getElementById('loading').classList.toggle('hidden', !show);
        }}

        // Raycaster for clicking
        const raycaster = new THREE.Raycaster();
        const mouse = new THREE.Vector2();

        function onMouseClick(event) {{
            mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
            mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;

            raycaster.setFromCamera(mouse, camera);

            const clickableMeshes = meshes.filter(m => m.userData && m.userData.id);
            const intersects = raycaster.intersectObjects(clickableMeshes);

            if (intersects.length > 0) {{
                const node = intersects[0].object.userData;
                if (node.expandable) {{
                    expandNode(node.id, node.name);
                }}
            }}
        }}

        function onMouseMove(event) {{
            mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
            mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;

            raycaster.setFromCamera(mouse, camera);

            const clickableMeshes = meshes.filter(m => m.userData && m.userData.id);
            const intersects = raycaster.intersectObjects(clickableMeshes);

            const tooltip = document.getElementById('tooltip');

            if (intersects.length > 0) {{
                const node = intersects[0].object.userData;

                tooltip.querySelector('.name').textContent = node.name;
                tooltip.querySelector('.type').textContent = node.code_type || node.type;

                let detail = '';
                if (node.total_nodes) {{
                    detail = `${{node.total_nodes.toLocaleString()}} nodes`;
                }}
                if (node.expandable) {{
                    detail += detail ? ' - Click to explore' : 'Click to explore';
                }}
                tooltip.querySelector('.detail').textContent = detail;

                tooltip.style.display = 'block';
                tooltip.style.left = (event.clientX + 15) + 'px';
                tooltip.style.top = (event.clientY + 15) + 'px';

                document.body.style.cursor = node.expandable ? 'pointer' : 'default';
            }} else {{
                tooltip.style.display = 'none';
                document.body.style.cursor = 'default';
            }}
        }}

        window.addEventListener('click', onMouseClick);
        window.addEventListener('mousemove', onMouseMove);

        // Resize handler
        window.addEventListener('resize', () => {{
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
        }});

        // 3D force simulation state
        const nodeVelocities = new Map();  // mesh -> {{vx, vy, vz}}

        function initForceState() {{
            meshes.forEach(mesh => {{
                nodeVelocities.set(mesh, {{ vx: 0, vy: 0, vz: 0 }});
            }});
        }}

        function applyForces() {{
            const centerForce = 0.0005;   // Pull toward center
            const repulsion = 50;         // Push apart
            const damping = 0.95;         // Velocity decay
            const minDist = 3;

            meshes.forEach((meshA, i) => {{
                const vel = nodeVelocities.get(meshA);
                if (!vel) return;

                // Attract to origin (keeps the cluster together)
                vel.vx -= meshA.position.x * centerForce;
                vel.vy -= meshA.position.y * centerForce;
                vel.vz -= meshA.position.z * centerForce;

                // Repel from other nodes
                meshes.forEach((meshB, j) => {{
                    if (i >= j) return;
                    const dx = meshA.position.x - meshB.position.x;
                    const dy = meshA.position.y - meshB.position.y;
                    const dz = meshA.position.z - meshB.position.z;
                    const dist = Math.sqrt(dx*dx + dy*dy + dz*dz) || minDist;
                    if (dist < repulsion) {{
                        const force = repulsion / (dist * dist);
                        const fx = (dx / dist) * force * 0.01;
                        const fy = (dy / dist) * force * 0.01;
                        const fz = (dz / dist) * force * 0.01;
                        vel.vx += fx; vel.vy += fy; vel.vz += fz;
                        const velB = nodeVelocities.get(meshB);
                        if (velB) {{ velB.vx -= fx; velB.vy -= fy; velB.vz -= fz; }}
                    }}
                }});

                // Damping
                vel.vx *= damping; vel.vy *= damping; vel.vz *= damping;

                // Apply velocity
                meshA.position.x += vel.vx;
                meshA.position.y += vel.vy;
                meshA.position.z += vel.vz;

                // Update label position if present
                if (meshA.userData && meshA.userData.label) {{
                    const label = meshA.userData.label;
                    label.position.copy(meshA.position);
                    label.position.y += meshA.userData.size * 1.5 + 2;
                }}
            }});
        }}

        // Animation loop
        function animate() {{
            requestAnimationFrame(animate);
            controls.update();

            // Run force simulation
            applyForces();

            // Gentle self-rotation for all bodies
            meshes.forEach(mesh => {{
                mesh.rotation.y += 0.003;
                mesh.rotation.x += 0.001;
            }});

            renderer.render(scene, camera);
        }}

        // Start
        camera.position.set(0, 50, 100);
        loadUniverse();
        animate();
    </script>
</body>
</html>
'''


def render_solar_system(
    organism: Organism,
    port: int = 8765,
    open_browser: bool = True
) -> SolarSystemRenderer:
    """
    Render organism as a navigable solar system.

    Args:
        organism: The organism to render
        port: Port for local web server
        open_browser: Whether to auto-open browser

    Returns:
        Renderer instance (call .stop() when done)
    """
    renderer = SolarSystemRenderer(organism, port)
    renderer.render(open_browser)
    return renderer
