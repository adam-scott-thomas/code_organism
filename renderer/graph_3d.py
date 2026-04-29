# SPDX-License-Identifier: Apache-2.0
"""
CODE ORGANISM: 3D GRAPH RENDERER

Renders the organism as an interactive 3D visualization.
Uses a web-based approach with Three.js for cross-platform compatibility.
"""

from __future__ import annotations
import json
import webbrowser
import http.server
import socketserver
import threading
from pathlib import Path
from typing import Optional
import tempfile
import os

from ..model.organism import Organism


class OrganismRenderer:
    """
    Renders an Organism as a 3D interactive visualization.

    Uses a local web server to serve a Three.js-based visualization
    that can be viewed in any modern browser.
    """

    def __init__(self, organism: Organism, port: int = 8765, bind: str = "127.0.0.1"):
        self.organism = organism
        self.port = port
        self.bind = bind
        self.server: Optional[socketserver.TCPServer] = None
        self.server_thread: Optional[threading.Thread] = None

    def render(self, open_browser: bool = True) -> str:
        """
        Start the visualization server and optionally open browser.

        Returns:
            URL of the visualization
        """
        # Pre-compute layout server-side (avoids O(n^2) JS freeze)
        from ..model.layout import LayoutEngine
        engine = LayoutEngine()
        self._precomputed_positions = engine.compute_layout(
            self.organism.nodes, self.organism.edges,
            use_cache=True, iterations=80,
        )
        print(f"Layout computed: {len(self._precomputed_positions)} positions")

        # Generate the HTML
        html_content = self._generate_html()

        # Create temp directory for serving
        self.temp_dir = tempfile.mkdtemp(prefix="code_organism_")
        html_path = Path(self.temp_dir) / "index.html"

        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        # Write organism data as JSON
        data_path = Path(self.temp_dir) / "organism_data.json"
        with open(data_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(self.organism.get_layout_data()))

        # Start server
        self._start_server()

        url = f"http://localhost:{self.port}"

        if open_browser:
            webbrowser.open(url)

        return url

    def _start_server(self) -> None:
        """Start the HTTP server in a background thread."""
        os.chdir(self.temp_dir)

        handler = http.server.SimpleHTTPRequestHandler

        self.server = socketserver.TCPServer((self.bind, self.port), handler)

        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.start()

        print(f"Code Organism Visualizer running at http://localhost:{self.port}")
        print("   Press Ctrl+C to stop")

    def stop(self) -> None:
        """Stop the server."""
        if self.server:
            self.server.shutdown()

    def _generate_html(self) -> str:
        """Generate the HTML/JS visualization."""
        layout_data = self.organism.get_layout_data()

        # Filter to structural nodes only (skip cellular noise)
        structural_types = {"module", "class", "function", "method"}
        structural_ids = {
            n["id"] for n in layout_data["nodes"] if n["type"] in structural_types
        }
        layout_data["nodes"] = [
            n for n in layout_data["nodes"] if n["id"] in structural_ids
        ]
        layout_data["edges"] = [
            e for e in layout_data["edges"]
            if e["source"] in structural_ids and e["target"] in structural_ids
        ]
        layout_data["particles"] = []

        # Inject pre-computed positions (scaled for spacing)
        positions = getattr(self, '_precomputed_positions', {})
        if positions:
            spread = 4.0
            for node in layout_data["nodes"]:
                pos = positions.get(node["id"])
                if pos:
                    node["x"] = pos["x"] * spread
                    node["y"] = pos["y"] * spread
                    node["z"] = pos["z"] * spread
        organism_data = json.dumps(layout_data)

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Code Organism: {self.organism.name}</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: #0a0a0f;
            color: #e0e0e0;
            overflow: hidden;
        }}

        #container {{
            width: 100vw;
            height: 100vh;
        }}

        #info-panel {{
            position: fixed;
            top: 20px;
            left: 20px;
            background: rgba(10, 10, 20, 0.9);
            border: 1px solid #333;
            border-radius: 8px;
            padding: 15px;
            min-width: 280px;
            max-width: 400px;
            backdrop-filter: blur(10px);
            z-index: 100;
        }}

        #info-panel h1 {{
            font-size: 1.2em;
            color: #8af;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        #info-panel h1::before {{
            content: "🧬";
        }}

        .stat-row {{
            display: flex;
            justify-content: space-between;
            padding: 4px 0;
            border-bottom: 1px solid #222;
        }}

        .stat-label {{
            color: #888;
        }}

        .stat-value {{
            color: #aef;
            font-family: monospace;
        }}

        #node-info {{
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #333;
            display: none;
        }}

        #node-info.visible {{
            display: block;
        }}

        #node-info h2 {{
            font-size: 1em;
            color: #fa8;
            margin-bottom: 8px;
        }}

        .health-indicator {{
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 6px;
        }}

        .health-healthy {{ background: #4a4; }}
        .health-stressed {{ background: #aa4; }}
        .health-inflamed {{ background: #a84; }}
        .health-necrotic {{ background: #666; }}
        .health-cancerous {{ background: #a44; }}

        #controls {{
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(10, 10, 20, 0.9);
            border: 1px solid #333;
            border-radius: 8px;
            padding: 10px 20px;
            display: flex;
            gap: 15px;
            align-items: center;
            backdrop-filter: blur(10px);
            z-index: 100;
        }}

        .control-btn {{
            background: #234;
            border: 1px solid #456;
            color: #aef;
            padding: 8px 16px;
            border-radius: 4px;
            cursor: pointer;
            transition: all 0.2s;
        }}

        .control-btn:hover {{
            background: #345;
            border-color: #678;
        }}

        .control-btn.active {{
            background: #456;
            border-color: #8af;
        }}

        #legend {{
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: rgba(10, 10, 20, 0.9);
            border: 1px solid #333;
            border-radius: 8px;
            padding: 15px;
            backdrop-filter: blur(10px);
            z-index: 100;
        }}

        #legend h3 {{
            font-size: 0.9em;
            color: #888;
            margin-bottom: 10px;
        }}

        .legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 3px 0;
            font-size: 0.85em;
        }}

        .legend-color {{
            width: 16px;
            height: 16px;
            border-radius: 3px;
        }}

        #loading {{
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            font-size: 1.5em;
            color: #8af;
            z-index: 1000;
        }}

        #loading.hidden {{
            display: none;
        }}
    </style>
</head>
<body>
    <div id="loading">🧬 Analyzing organism...</div>

    <div id="container"></div>

    <div id="info-panel">
        <h1>{self.organism.name}</h1>
        <div class="stat-row">
            <span class="stat-label">Modules:</span>
            <span class="stat-value" id="stat-modules">-</span>
        </div>
        <div class="stat-row">
            <span class="stat-label">Classes:</span>
            <span class="stat-value" id="stat-classes">-</span>
        </div>
        <div class="stat-row">
            <span class="stat-label">Functions:</span>
            <span class="stat-value" id="stat-functions">-</span>
        </div>
        <div class="stat-row">
            <span class="stat-label">Connections:</span>
            <span class="stat-value" id="stat-edges">-</span>
        </div>
        <div class="stat-row">
            <span class="stat-label">Health:</span>
            <span class="stat-value" id="stat-health">-</span>
        </div>

        <div id="node-info">
            <h2 id="node-name">-</h2>
            <div class="stat-row">
                <span class="stat-label">Type:</span>
                <span class="stat-value" id="node-type">-</span>
            </div>
            <div class="stat-row">
                <span class="stat-label">Health:</span>
                <span class="stat-value" id="node-health">-</span>
            </div>
            <div class="stat-row">
                <span class="stat-label">Connections:</span>
                <span class="stat-value" id="node-connections">-</span>
            </div>
        </div>
    </div>

    <div id="controls">
        <button class="control-btn" id="btn-rotate" title="Toggle auto-rotation">🔄 Rotate</button>
        <button class="control-btn" id="btn-health" title="Toggle health overlay">❤️ Health</button>
        <button class="control-btn" id="btn-flow" title="Toggle data flow">🩸 Flow</button>
        <button class="control-btn" id="btn-reset" title="Reset view">🎯 Reset</button>
    </div>

    <div id="legend">
        <h3>Node Types</h3>
        <div class="legend-item">
            <div class="legend-color" style="background: #6699ff"></div>
            <span>Module</span>
        </div>
        <div class="legend-item">
            <div class="legend-color" style="background: #ff6666"></div>
            <span>Class</span>
        </div>
        <div class="legend-item">
            <div class="legend-color" style="background: #66ff99"></div>
            <span>Function</span>
        </div>
        <div class="legend-item">
            <div class="legend-color" style="background: #cc99ff"></div>
            <span>Method</span>
        </div>
        <div class="legend-item">
            <div class="legend-color" style="background: #ffcc66"></div>
            <span>External</span>
        </div>
        <h3 style="margin-top: 10px;">Edge Types</h3>
        <div class="legend-item">
            <div class="legend-color" style="background: #4488ff"></div>
            <span>Import</span>
        </div>
        <div class="legend-item">
            <div class="legend-color" style="background: #44ff88"></div>
            <span>Call</span>
        </div>
        <div class="legend-item">
            <div class="legend-color" style="background: #ff8844"></div>
            <span>Inheritance</span>
        </div>
    </div>

    <!-- Three.js from CDN -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>

    <script>
        // Check if Three.js loaded
        if (typeof THREE === 'undefined') {{
            document.getElementById('loading').textContent = 'Error: Three.js failed to load. Check your internet connection.';
            throw new Error('Three.js not loaded');
        }}

        // Organism data embedded from Python
        let organismData;
        try {{
            organismData = {organism_data};
            console.log('Organism data loaded:', organismData);
            console.log('  Nodes:', organismData.nodes ? organismData.nodes.length : 'undefined');
            console.log('  Edges:', organismData.edges ? organismData.edges.length : 'undefined');
        }} catch (e) {{
            console.error('Failed to parse organism data:', e);
            document.getElementById('loading').textContent = 'Error: Failed to parse organism data';
            throw e;
        }}

        // Scene setup
        let scene, camera, renderer, controls;
        let nodeMeshes = {{}};
        let edgeLines = [];
        let particles = [];
        let raycaster, mouse;
        let selectedNode = null;
        let autoRotate = false;
        let showHealth = false;
        let showFlow = false;
        let initialized = false;

        function init() {{
            if (initialized) {{
                console.log('Already initialized, skipping');
                return;
            }}
            initialized = true;
            console.log('Initializing visualization...');
            // Scene
            scene = new THREE.Scene();
            scene.background = new THREE.Color(0x0a0a0f);

            // Camera - far plane set high for large layouts
            camera = new THREE.PerspectiveCamera(
                60,
                window.innerWidth / window.innerHeight,
                0.1,
                50000
            );
            camera.position.set(0, 20, 40);

            // Renderer
            renderer = new THREE.WebGLRenderer({{ antialias: true }});
            renderer.setSize(window.innerWidth, window.innerHeight);
            renderer.setPixelRatio(window.devicePixelRatio);
            document.getElementById('container').appendChild(renderer.domElement);

            // Controls
            controls = new THREE.OrbitControls(camera, renderer.domElement);
            controls.enableDamping = true;
            controls.dampingFactor = 0.05;
            controls.autoRotate = autoRotate;
            controls.autoRotateSpeed = 0.5;

            // Raycaster for picking
            raycaster = new THREE.Raycaster();
            mouse = new THREE.Vector2();

            // Lighting
            const ambientLight = new THREE.AmbientLight(0x404040, 0.5);
            scene.add(ambientLight);

            const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
            directionalLight.position.set(10, 20, 10);
            scene.add(directionalLight);

            const pointLight = new THREE.PointLight(0x8888ff, 0.5, 100);
            pointLight.position.set(-10, 10, -10);
            scene.add(pointLight);

            // Add subtle fog for depth - reduced density for large layouts
            scene.fog = new THREE.FogExp2(0x0a0a0f, 0.0005);

            // Build the organism
            buildOrganism();

            // Update stats
            updateStats();

            // Event listeners
            window.addEventListener('resize', onWindowResize);
            renderer.domElement.addEventListener('click', onMouseClick);
            renderer.domElement.addEventListener('mousemove', onMouseMove);

            // Control buttons
            document.getElementById('btn-rotate').addEventListener('click', toggleRotate);
            document.getElementById('btn-health').addEventListener('click', toggleHealth);
            document.getElementById('btn-flow').addEventListener('click', toggleFlow);
            document.getElementById('btn-reset').addEventListener('click', resetView);

            // Hide loading
            document.getElementById('loading').classList.add('hidden');

            console.log('Initialization complete. Starting animation...');
            console.log('Scene has', scene.children.length, 'objects');

            // Start animation
            animate();
        }}

        // Dark mode optimized colors
        const typeColors = {{
            module: new THREE.Color(0x6699ff),    // Bright blue
            package: new THREE.Color(0x6699ff),
            class: new THREE.Color(0xff6666),     // Bright red
            function: new THREE.Color(0x66ff99),  // Bright green
            method: new THREE.Color(0xcc99ff),    // Bright purple
            external: new THREE.Color(0xffcc66),  // Bright orange
            builtin: new THREE.Color(0x99ccff),   // Light blue
            parameter: new THREE.Color(0x88aacc), // Muted blue
            attribute: new THREE.Color(0xccaa88), // Muted orange
        }};

        function getNodeColor(nodeType) {{
            return typeColors[nodeType] || new THREE.Color(0xaaaaaa);
        }}

        function buildOrganism() {{
            const nodes = organismData.nodes;
            const edges = organismData.edges;

            console.log('Building organism with', nodes.length, 'nodes and', edges.length, 'edges');

            if (nodes.length === 0) {{
                console.error('No nodes to display!');
                document.getElementById('loading').textContent = 'Error: No nodes in organism data';
                return;
            }}

            // Use pre-computed positions if available, else fall back to JS layout
            let positions;
            const hasPrecomputed = nodes.length > 0 && nodes[0].x !== undefined;
            if (hasPrecomputed) {{
                positions = {{}};
                nodes.forEach(n => {{ positions[n.id] = {{ x: n.x, y: n.y, z: n.z }}; }});
                console.log('Using pre-computed layout for', nodes.length, 'nodes');
            }} else {{
                positions = layoutNodes(nodes, edges);
                console.log('Computed JS layout for', Object.keys(positions).length, 'nodes');
            }}

            // Create node meshes - LARGER SIZES for visibility
            nodes.forEach((node, index) => {{
                const pos = positions[node.id] || {{ x: 0, y: 0, z: 0 }};

                // Geometry based on type - LARGE SIZES for visibility
                let geometry;
                const size = (node.size || 1) * 2.5;  // scaled for clarity

                switch (node.type) {{
                    case 'module':
                    case 'package':
                        geometry = new THREE.BoxGeometry(size * 1.5, size * 1.5, size * 1.5);
                        break;
                    case 'class':
                        geometry = new THREE.OctahedronGeometry(size * 1.2);
                        break;
                    case 'function':
                    case 'method':
                        geometry = new THREE.SphereGeometry(size * 0.8, 16, 16);
                        break;
                    case 'external':
                    case 'builtin':
                        geometry = new THREE.TetrahedronGeometry(size * 0.7);
                        break;
                    default:
                        geometry = new THREE.SphereGeometry(size * 0.5, 8, 8);
                }}

                // Use bright colors optimized for dark mode
                const color = getNodeColor(node.type);

                const material = new THREE.MeshPhongMaterial({{
                    color: color,
                    emissive: color.clone().multiplyScalar(0.4),  // More glow
                    transparent: true,
                    opacity: 0.95,
                    shininess: 80,
                }});

                const mesh = new THREE.Mesh(geometry, material);
                mesh.position.set(pos.x, pos.y, pos.z);
                mesh.userData = {{ ...node, baseColor: color }};

                scene.add(mesh);
                nodeMeshes[node.id] = mesh;
            }});

            console.log('Created', Object.keys(nodeMeshes).length, 'node meshes');

            // Create edges using cylinders for thick visible lines
            edges.forEach(edge => {{
                const sourceNode = nodeMeshes[edge.source];
                const targetNode = nodeMeshes[edge.target];

                if (sourceNode && targetNode) {{
                    const start = sourceNode.position.clone();
                    const end = targetNode.position.clone();

                    // Create thick tube/cylinder for edge
                    const direction = new THREE.Vector3().subVectors(end, start);
                    const length = direction.length();
                    const midpoint = new THREE.Vector3().addVectors(start, end).multiplyScalar(0.5);

                    // Edge color based on type
                    let edgeColor;
                    switch (edge.type) {{
                        case 'import':
                            edgeColor = new THREE.Color(0x4488ff);
                            break;
                        case 'call':
                            edgeColor = new THREE.Color(0x44ff88);
                            break;
                        case 'inheritance':
                            edgeColor = new THREE.Color(0xff8844);
                            break;
                        default:
                            edgeColor = new THREE.Color(0x6688aa);
                    }}

                    // Use cylinder geometry for thick lines - scaled up for visibility
                    const cylinderGeometry = new THREE.CylinderGeometry(0.15, 0.15, length, 4);
                    const cylinderMaterial = new THREE.MeshBasicMaterial({{
                        color: edgeColor,
                        transparent: true,
                        opacity: 0.6,
                    }});

                    const cylinder = new THREE.Mesh(cylinderGeometry, cylinderMaterial);
                    cylinder.position.copy(midpoint);

                    // Orient cylinder to connect the two nodes
                    cylinder.quaternion.setFromUnitVectors(
                        new THREE.Vector3(0, 1, 0),
                        direction.clone().normalize()
                    );

                    cylinder.userData = edge;
                    scene.add(cylinder);
                    edgeLines.push(cylinder);
                }}
            }});

            console.log('Created', edgeLines.length, 'edge cylinders');

            // Auto-focus camera to fit all nodes
            fitCameraToOrganism();
            console.log('Camera positioned, scene children:', scene.children.length);
        }}

        function fitCameraToOrganism() {{
            const box = new THREE.Box3();

            // Include all node meshes in bounding box
            Object.values(nodeMeshes).forEach(mesh => {{
                box.expandByObject(mesh);
            }});

            if (box.isEmpty()) return;

            const center = box.getCenter(new THREE.Vector3());
            const size = box.getSize(new THREE.Vector3());
            const maxDim = Math.max(size.x, size.y, size.z);

            // Position camera to see everything with some padding
            const fov = camera.fov * (Math.PI / 180);
            const distance = (maxDim / (2 * Math.tan(fov / 2))) * 1.8;

            camera.position.set(
                center.x + distance * 0.3,
                center.y + distance * 0.4,
                center.z + distance
            );
            controls.target.copy(center);
            controls.update();
        }}

        function layoutNodes(nodes, edges) {{
            // Simple force-directed layout
            const positions = {{}};
            const nodeMap = {{}};

            // Initialize positions randomly in a smaller sphere
            nodes.forEach((node, i) => {{
                const theta = Math.random() * Math.PI * 2;
                const phi = Math.acos(2 * Math.random() - 1);
                const r = 10 + Math.random() * 5;  // Smaller initial spread

                positions[node.id] = {{
                    x: r * Math.sin(phi) * Math.cos(theta),
                    y: r * Math.sin(phi) * Math.sin(theta),
                    z: r * Math.cos(phi),
                    vx: 0, vy: 0, vz: 0
                }};
                nodeMap[node.id] = node;
            }});

            // Build adjacency for connected components
            const adjacency = {{}};
            edges.forEach(edge => {{
                if (!adjacency[edge.source]) adjacency[edge.source] = [];
                if (!adjacency[edge.target]) adjacency[edge.target] = [];
                adjacency[edge.source].push(edge.target);
                adjacency[edge.target].push(edge.source);
            }});

            // Run simulation - reduced repulsion for tighter clustering
            const iterations = 100;
            const repulsion = 100;  // Reduced from 500 for tighter layout
            const attraction = 0.1;  // Increased from 0.05 for stronger clustering
            const damping = 0.85;

            for (let iter = 0; iter < iterations; iter++) {{
                // Repulsion between all pairs
                const nodeIds = Object.keys(positions);
                for (let i = 0; i < nodeIds.length; i++) {{
                    for (let j = i + 1; j < nodeIds.length; j++) {{
                        const a = positions[nodeIds[i]];
                        const b = positions[nodeIds[j]];

                        const dx = b.x - a.x;
                        const dy = b.y - a.y;
                        const dz = b.z - a.z;
                        const dist = Math.sqrt(dx*dx + dy*dy + dz*dz) + 0.1;

                        const force = repulsion / (dist * dist);
                        const fx = (dx / dist) * force;
                        const fy = (dy / dist) * force;
                        const fz = (dz / dist) * force;

                        a.vx -= fx; a.vy -= fy; a.vz -= fz;
                        b.vx += fx; b.vy += fy; b.vz += fz;
                    }}
                }}

                // Attraction along edges
                edges.forEach(edge => {{
                    const a = positions[edge.source];
                    const b = positions[edge.target];
                    if (!a || !b) return;

                    const dx = b.x - a.x;
                    const dy = b.y - a.y;
                    const dz = b.z - a.z;
                    const dist = Math.sqrt(dx*dx + dy*dy + dz*dz) + 0.1;

                    const force = dist * attraction;
                    const fx = (dx / dist) * force;
                    const fy = (dy / dist) * force;
                    const fz = (dz / dist) * force;

                    a.vx += fx; a.vy += fy; a.vz += fz;
                    b.vx -= fx; b.vy -= fy; b.vz -= fz;
                }});

                // Apply velocities and damping
                nodeIds.forEach(id => {{
                    const p = positions[id];
                    p.x += p.vx; p.y += p.vy; p.z += p.vz;
                    p.vx *= damping; p.vy *= damping; p.vz *= damping;
                }});
            }}

            return positions;
        }}

        function updateStats() {{
            let modules = 0, classes = 0, functions = 0;

            organismData.nodes.forEach(node => {{
                if (node.type === 'module' || node.type === 'package') modules++;
                else if (node.type === 'class') classes++;
                else if (node.type === 'function' || node.type === 'method') functions++;
            }});

            document.getElementById('stat-modules').textContent = modules;
            document.getElementById('stat-classes').textContent = classes;
            document.getElementById('stat-functions').textContent = functions;
            document.getElementById('stat-edges').textContent = organismData.edges.length;

            // Calculate health percentage
            let healthy = 0;
            organismData.nodes.forEach(node => {{
                if (node.health === 'healthy') healthy++;
            }});
            const healthPct = organismData.nodes.length > 0
                ? Math.round((healthy / organismData.nodes.length) * 100)
                : 100;
            document.getElementById('stat-health').textContent = healthPct + '%';
        }}

        function onWindowResize() {{
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
        }}

        function onMouseClick(event) {{
            mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
            mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;

            raycaster.setFromCamera(mouse, camera);
            const meshes = Object.values(nodeMeshes);
            const intersects = raycaster.intersectObjects(meshes);

            if (intersects.length > 0) {{
                selectNode(intersects[0].object);
            }} else {{
                deselectNode();
            }}
        }}

        function onMouseMove(event) {{
            mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
            mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;
        }}

        function selectNode(mesh) {{
            // Deselect previous
            if (selectedNode) {{
                selectedNode.material.emissive.setHex(
                    selectedNode.userData.originalEmissive || 0x000000
                );
            }}

            selectedNode = mesh;
            mesh.userData.originalEmissive = mesh.material.emissive.getHex();
            mesh.material.emissive.setHex(0xffaa00);

            // Update info panel
            const node = mesh.userData;
            document.getElementById('node-info').classList.add('visible');
            document.getElementById('node-name').textContent = node.name;
            document.getElementById('node-type').textContent = node.type;

            const healthEl = document.getElementById('node-health');
            healthEl.innerHTML = `<span class="health-indicator health-${{node.health}}"></span>${{node.health}}`;

            // Count connections
            let connections = 0;
            organismData.edges.forEach(edge => {{
                if (edge.source === node.id || edge.target === node.id) {{
                    connections++;
                }}
            }});
            document.getElementById('node-connections').textContent = connections;
        }}

        function deselectNode() {{
            if (selectedNode) {{
                selectedNode.material.emissive.setHex(
                    selectedNode.userData.originalEmissive || 0x000000
                );
                selectedNode = null;
            }}
            document.getElementById('node-info').classList.remove('visible');
        }}

        function toggleRotate() {{
            autoRotate = !autoRotate;
            controls.autoRotate = autoRotate;
            document.getElementById('btn-rotate').classList.toggle('active', autoRotate);
        }}

        function toggleHealth() {{
            showHealth = !showHealth;
            document.getElementById('btn-health').classList.toggle('active', showHealth);

            // Update node colors based on health
            Object.values(nodeMeshes).forEach(mesh => {{
                const node = mesh.userData;
                if (showHealth) {{
                    const healthColors = {{
                        healthy: 0x44aa44,
                        stressed: 0xaaaa44,
                        inflamed: 0xaa8844,
                        necrotic: 0x666666,
                        cancerous: 0xaa4444,
                        unknown: 0x888888
                    }};
                    mesh.material.color.setHex(healthColors[node.health] || 0x888888);
                }} else {{
                    mesh.material.color.setRGB(
                        node.color[0],
                        node.color[1],
                        node.color[2]
                    );
                }}
            }});
        }}

        function toggleFlow() {{
            showFlow = !showFlow;
            document.getElementById('btn-flow').classList.toggle('active', showFlow);

            // Toggle edge visibility
            edgeLines.forEach(line => {{
                line.material.opacity = showFlow ? 0.6 : 0.3;
            }});

            // TODO: Add particle animation for data flow
        }}

        function resetView() {{
            // Use auto-fit to center on organism
            fitCameraToOrganism();
        }}

        function animate() {{
            requestAnimationFrame(animate);

            controls.update();

            // Subtle pulsing for selected node
            if (selectedNode) {{
                const time = Date.now() * 0.003;
                const pulse = Math.sin(time) * 0.1 + 0.9;
                selectedNode.scale.setScalar(pulse);
            }}

            // Rotate nodes slightly based on their type
            Object.values(nodeMeshes).forEach(mesh => {{
                if (mesh.userData.type === 'class') {{
                    mesh.rotation.y += 0.002;
                }}
            }});

            renderer.render(scene, camera);
        }}

        // Initialize when DOM is ready
        document.addEventListener('DOMContentLoaded', function() {{
            try {{
                init();
            }} catch (e) {{
                console.error('Initialization error:', e);
                document.getElementById('loading').textContent = 'Error: ' + e.message;
            }}
        }});

        // Also try to init if DOMContentLoaded already fired
        if (document.readyState !== 'loading') {{
            try {{
                init();
            }} catch (e) {{
                console.error('Initialization error:', e);
                document.getElementById('loading').textContent = 'Error: ' + e.message;
            }}
        }}
    </script>
</body>
</html>
'''


def render_organism(organism: Organism, port: int = 8765, open_browser: bool = True) -> OrganismRenderer:
    """
    Render an organism as a 3D visualization.

    Args:
        organism: The organism to render
        port: Port for the local web server
        open_browser: Whether to automatically open browser

    Returns:
        The renderer instance (call .stop() when done)
    """
    renderer = OrganismRenderer(organism, port)
    renderer.render(open_browser)
    return renderer
