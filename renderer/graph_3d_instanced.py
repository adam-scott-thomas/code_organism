"""
CODE ORGANISM: GPU-INSTANCED 3D RENDERER

High-performance renderer for massive codebases (millions of nodes).
Uses GPU instancing for O(1) draw calls per node type.
"""

from __future__ import annotations
import json
import webbrowser
import http.server
import socketserver
import threading
from pathlib import Path
from typing import Optional, Dict, Any
import tempfile
import os
from urllib.parse import urlparse, parse_qs

from ..model.organism import Organism


class InstancedOrganismRenderer:
    """
    High-performance renderer using GPU instancing.

    Supports:
    - Hierarchical clustering for massive codebases
    - Progressive loading via REST API
    - GPU-instanced rendering (one draw call per node type)
    """

    def __init__(
        self,
        organism: Organism,
        port: int = 8765,
        max_level: int = 2,
        bind: str = "127.0.0.1",
    ):
        self.organism = organism
        self.port = port
        self.max_level = max_level
        self.bind = bind
        self.server: Optional[socketserver.TCPServer] = None
        self.server_thread: Optional[threading.Thread] = None
        self.temp_dir: Optional[str] = None

    def render(self, open_browser: bool = True, use_clustering: bool = True) -> str:
        """Start the visualization server."""
        # Create temp directory
        self.temp_dir = tempfile.mkdtemp(prefix="code_organism_")

        # Generate HTML
        html_content = self._generate_html()
        html_path = Path(self.temp_dir) / "index.html"
        with open(html_path, "w", encoding="utf-8") as f:
            f.write(html_content)

        # Generate initial data (overview level)
        if use_clustering and len(self.organism.nodes) > 5000:
            initial_data = self.organism.get_hierarchical_layout_data(level=0)
        else:
            initial_data = self.organism.get_layout_data()
            # Add positions if not present
            if initial_data['nodes'] and 'x' not in initial_data['nodes'][0]:
                from ..model.layout import LayoutEngine
                engine = LayoutEngine()
                positions = engine.compute_layout(
                    self.organism.nodes,
                    self.organism.edges,
                    iterations=50
                )
                for node in initial_data['nodes']:
                    pos = positions.get(node['id'], {'x': 0, 'y': 0, 'z': 0})
                    node.update(pos)

        data_path = Path(self.temp_dir) / "organism_data.json"
        with open(data_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(initial_data))

        # Start server with API support
        self._start_server()

        url = f"http://localhost:{self.port}"
        if open_browser:
            webbrowser.open(url)

        return url

    def _start_server(self) -> None:
        """Start HTTP server with API endpoints."""
        os.chdir(self.temp_dir)

        # Create handler with reference to organism
        organism = self.organism

        class APIHandler(http.server.SimpleHTTPRequestHandler):
            def do_GET(self):
                parsed = urlparse(self.path)

                if parsed.path == '/api/overview':
                    self._serve_json(organism.get_hierarchical_layout_data(level=0))
                elif parsed.path.startswith('/api/cluster/'):
                    cluster_id = parsed.path.split('/')[-1]
                    self._serve_json(organism.get_cluster_children(cluster_id))
                elif parsed.path == '/api/level':
                    params = parse_qs(parsed.query)
                    level = int(params.get('level', [0])[0])
                    self._serve_json(organism.get_hierarchical_layout_data(level=level))
                else:
                    super().do_GET()

            def _serve_json(self, data: dict):
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(data).encode())

            def log_message(self, format, *args):
                pass  # Suppress logging

        # Allow address reuse to avoid "address already in use" errors
        socketserver.TCPServer.allow_reuse_address = True
        self.server = socketserver.TCPServer((self.bind, self.port), APIHandler)
        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.start()

        print(f"Code Organism (Instanced) running at http://localhost:{self.port}")
        print("   Press Ctrl+C to stop")

    def stop(self) -> None:
        """Stop the server."""
        if self.server:
            self.server.shutdown()

    def _generate_html(self) -> str:
        """Generate HTML with GPU-instanced Three.js renderer."""
        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Code Organism: {self.organism.name}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Segoe UI', system-ui, sans-serif;
            background: #0a0a0f;
            color: #e0e0e0;
            overflow: hidden;
        }}
        #container {{ width: 100vw; height: 100vh; }}

        #info-panel {{
            position: fixed;
            top: 20px;
            left: 20px;
            background: rgba(10, 10, 20, 0.95);
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
        }}

        .stat-row {{
            display: flex;
            justify-content: space-between;
            padding: 4px 0;
            border-bottom: 1px solid #222;
        }}

        .stat-label {{ color: #888; }}
        .stat-value {{ color: #aef; font-family: monospace; }}

        #controls {{
            position: fixed;
            bottom: 20px;
            left: 50%;
            transform: translateX(-50%);
            background: rgba(10, 10, 20, 0.95);
            border: 1px solid #333;
            border-radius: 8px;
            padding: 10px 20px;
            display: flex;
            gap: 15px;
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

        .control-btn:hover {{ background: #345; }}
        .control-btn.active {{ background: #456; border-color: #8af; }}

        #legend {{
            position: fixed;
            bottom: 20px;
            right: 20px;
            background: rgba(10, 10, 20, 0.95);
            border: 1px solid #333;
            border-radius: 8px;
            padding: 15px;
            z-index: 100;
        }}

        #legend h3 {{ font-size: 0.9em; color: #888; margin-bottom: 10px; }}

        .legend-item {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 3px 0;
            font-size: 0.85em;
        }}

        .legend-color {{ width: 16px; height: 16px; border-radius: 3px; }}

        #loading {{
            position: fixed;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            font-size: 1.5em;
            color: #8af;
            z-index: 1000;
        }}

        #loading.hidden {{ display: none; }}

        #fps {{
            position: fixed;
            top: 20px;
            right: 20px;
            background: rgba(10, 10, 20, 0.9);
            padding: 5px 10px;
            border-radius: 4px;
            font-family: monospace;
            color: #8f8;
            z-index: 100;
        }}
    </style>
</head>
<body>
    <div id="loading">Loading organism...</div>
    <div id="container"></div>
    <div id="fps">-- FPS</div>

    <div id="info-panel">
        <h1>{self.organism.name}</h1>
        <div class="stat-row">
            <span class="stat-label">Visible Nodes:</span>
            <span class="stat-value" id="stat-nodes">-</span>
        </div>
        <div class="stat-row">
            <span class="stat-label">Total Nodes:</span>
            <span class="stat-value" id="stat-total">-</span>
        </div>
        <div class="stat-row">
            <span class="stat-label">Edges:</span>
            <span class="stat-value" id="stat-edges">-</span>
        </div>
        <div class="stat-row">
            <span class="stat-label">Draw Calls:</span>
            <span class="stat-value" id="stat-draws">-</span>
        </div>
        <div class="stat-row">
            <span class="stat-label">Level:</span>
            <span class="stat-value" id="stat-level">0</span>
        </div>
    </div>

    <div id="controls">
        <button class="control-btn" id="btn-rotate">Rotate</button>
        <button class="control-btn" id="btn-reset">Reset View</button>
        <button class="control-btn" id="btn-expand">Expand All</button>
    </div>

    <div id="legend">
        <h3>Node Types</h3>
        <div class="legend-item">
            <div class="legend-color" style="background: #6699ff"></div>
            <span>Module/Cluster</span>
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
    </div>

    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>

    <script>
        // =================================================================
        // GPU-INSTANCED ORGANISM RENDERER
        // =================================================================

        let scene, camera, renderer, controls;
        let nodeInstances = {{}};  // One InstancedMesh per type
        let edgeMesh = null;
        let organismData = null;
        let autoRotate = false;

        // Performance tracking
        let frameCount = 0;
        let lastTime = performance.now();

        // Type colors
        const typeColors = {{
            cluster: 0x6699ff,
            module: 0x6699ff,
            package: 0x6699ff,
            class: 0xff6666,
            function: 0x66ff99,
            method: 0xcc99ff,
            external: 0xffcc66,
            builtin: 0x99ccff,
        }};

        // =================================================================
        // INITIALIZATION
        // =================================================================

        async function init() {{
            // Load data
            const response = await fetch('/organism_data.json');
            organismData = await response.json();

            console.log('Loaded', organismData.nodes?.length || 0, 'nodes');

            // Scene setup
            scene = new THREE.Scene();
            scene.background = new THREE.Color(0x0a0a0f);

            // Camera
            camera = new THREE.PerspectiveCamera(
                60,
                window.innerWidth / window.innerHeight,
                0.1,
                50000
            );
            camera.position.set(0, 50, 150);

            // Renderer
            renderer = new THREE.WebGLRenderer({{ antialias: true }});
            renderer.setSize(window.innerWidth, window.innerHeight);
            renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
            document.getElementById('container').appendChild(renderer.domElement);

            // Controls
            controls = new THREE.OrbitControls(camera, renderer.domElement);
            controls.enableDamping = true;
            controls.dampingFactor = 0.05;

            // Lighting
            scene.add(new THREE.AmbientLight(0x404040, 0.6));
            const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
            dirLight.position.set(50, 100, 50);
            scene.add(dirLight);

            // Initialize instanced meshes
            initInstancedMeshes();

            // Build organism
            buildOrganism();

            // Fit camera
            fitCameraToScene();

            // Event listeners
            window.addEventListener('resize', onResize);
            document.getElementById('btn-rotate').addEventListener('click', toggleRotate);
            document.getElementById('btn-reset').addEventListener('click', resetView);
            document.getElementById('btn-expand').addEventListener('click', expandAll);

            // Hide loading
            document.getElementById('loading').classList.add('hidden');

            // Update stats
            updateStats();

            // Start render loop
            animate();
        }}

        function initInstancedMeshes() {{
            // Pre-create instanced meshes for each node type
            const MAX_INSTANCES = 100000;

            const geometries = {{
                cluster: new THREE.BoxGeometry(1, 1, 1),
                module: new THREE.BoxGeometry(1, 1, 1),
                package: new THREE.BoxGeometry(1, 1, 1),
                class: new THREE.OctahedronGeometry(1),
                function: new THREE.SphereGeometry(1, 8, 8),
                method: new THREE.SphereGeometry(1, 6, 6),
                external: new THREE.TetrahedronGeometry(1),
                builtin: new THREE.TetrahedronGeometry(0.8),
            }};

            for (const [type, geometry] of Object.entries(geometries)) {{
                const material = new THREE.MeshPhongMaterial({{
                    color: typeColors[type] || 0xaaaaaa,
                    emissive: new THREE.Color(typeColors[type] || 0xaaaaaa).multiplyScalar(0.3),
                    transparent: true,
                    opacity: 0.9,
                }});

                const mesh = new THREE.InstancedMesh(geometry, material, MAX_INSTANCES);
                mesh.count = 0;  // Start with 0 visible
                mesh.frustumCulled = false;  // We handle our own culling
                scene.add(mesh);
                nodeInstances[type] = mesh;
            }}
        }}

        // =================================================================
        // BUILD ORGANISM FROM DATA
        // =================================================================

        function buildOrganism() {{
            if (!organismData || !organismData.nodes) return;

            const nodes = organismData.nodes;
            const edges = organismData.edges || [];

            // Group nodes by type
            const nodesByType = {{}};
            for (const node of nodes) {{
                const type = node.type || 'function';
                if (!nodesByType[type]) nodesByType[type] = [];
                nodesByType[type].push(node);
            }}

            // Update instanced meshes
            const matrix = new THREE.Matrix4();
            const position = new THREE.Vector3();
            const quaternion = new THREE.Quaternion();
            const scale = new THREE.Vector3();

            for (const [type, typeNodes] of Object.entries(nodesByType)) {{
                const mesh = nodeInstances[type];
                if (!mesh) continue;

                typeNodes.forEach((node, idx) => {{
                    // Position
                    position.set(
                        node.x || 0,
                        node.y || 0,
                        node.z || 0
                    );

                    // Scale based on node size (smaller for better visibility at scale)
                    const s = (node.size || 1) * 0.8;
                    scale.set(s, s, s);

                    // Compose matrix
                    matrix.compose(position, quaternion, scale);
                    mesh.setMatrixAt(idx, matrix);
                }});

                mesh.count = typeNodes.length;
                mesh.instanceMatrix.needsUpdate = true;
            }}

            // Build edges as line segments
            buildEdges(edges, nodes);
        }}

        function buildEdges(edges, nodes) {{
            if (edgeMesh) {{
                scene.remove(edgeMesh);
                edgeMesh.geometry.dispose();
            }}

            if (edges.length === 0) return;

            // Create node lookup
            const nodeLookup = {{}};
            for (const node of nodes) {{
                nodeLookup[node.id] = node;
            }}

            // Build line geometry
            const positions = [];
            const colors = [];

            const edgeColors = {{
                import: [0.27, 0.53, 1.0],
                call: [0.27, 1.0, 0.53],
                inheritance: [1.0, 0.53, 0.27],
            }};

            for (const edge of edges) {{
                const source = nodeLookup[edge.source];
                const target = nodeLookup[edge.target];

                if (!source || !target) continue;

                positions.push(
                    source.x || 0, source.y || 0, source.z || 0,
                    target.x || 0, target.y || 0, target.z || 0
                );

                const color = edgeColors[edge.type] || [0.4, 0.5, 0.6];
                colors.push(...color, ...color);
            }}

            const geometry = new THREE.BufferGeometry();
            geometry.setAttribute('position',
                new THREE.Float32BufferAttribute(positions, 3));
            geometry.setAttribute('color',
                new THREE.Float32BufferAttribute(colors, 3));

            const material = new THREE.LineBasicMaterial({{
                vertexColors: true,
                transparent: true,
                opacity: 0.4,
            }});

            edgeMesh = new THREE.LineSegments(geometry, material);
            scene.add(edgeMesh);
        }}

        // =================================================================
        // CAMERA & VIEW
        // =================================================================

        function fitCameraToScene() {{
            const box = new THREE.Box3();

            // Include all instanced meshes
            for (const mesh of Object.values(nodeInstances)) {{
                if (mesh.count > 0) {{
                    // Approximate bounds from instance matrices
                    const matrix = new THREE.Matrix4();
                    const position = new THREE.Vector3();

                    for (let i = 0; i < mesh.count; i++) {{
                        mesh.getMatrixAt(i, matrix);
                        position.setFromMatrixPosition(matrix);
                        box.expandByPoint(position);
                    }}
                }}
            }}

            if (box.isEmpty()) return;

            const center = box.getCenter(new THREE.Vector3());
            const size = box.getSize(new THREE.Vector3());
            const maxDim = Math.max(size.x, size.y, size.z);

            const fov = camera.fov * (Math.PI / 180);
            const distance = (maxDim / (2 * Math.tan(fov / 2))) * 1.5;

            camera.position.set(
                center.x + distance * 0.3,
                center.y + distance * 0.4,
                center.z + distance
            );
            controls.target.copy(center);
            controls.update();
        }}

        function resetView() {{
            fitCameraToScene();
        }}

        function toggleRotate() {{
            autoRotate = !autoRotate;
            controls.autoRotate = autoRotate;
            controls.autoRotateSpeed = 0.5;
            document.getElementById('btn-rotate').classList.toggle('active', autoRotate);
        }}

        async function expandAll() {{
            // TODO: Implement progressive expansion
            console.log('Expand all - not yet implemented');
        }}

        // =================================================================
        // STATS & UI
        // =================================================================

        function updateStats() {{
            const nodes = organismData?.nodes || [];
            const edges = organismData?.edges || [];

            document.getElementById('stat-nodes').textContent = nodes.length.toLocaleString();
            document.getElementById('stat-total').textContent =
                (organismData?.total_nodes || nodes.length).toLocaleString();
            document.getElementById('stat-edges').textContent = edges.length.toLocaleString();
            document.getElementById('stat-level').textContent = organismData?.level || 0;

            // Count draw calls (one per instanced mesh type with nodes)
            let drawCalls = 0;
            for (const mesh of Object.values(nodeInstances)) {{
                if (mesh.count > 0) drawCalls++;
            }}
            if (edgeMesh) drawCalls++;
            document.getElementById('stat-draws').textContent = drawCalls;
        }}

        function updateFPS() {{
            frameCount++;
            const now = performance.now();
            const elapsed = now - lastTime;

            if (elapsed >= 1000) {{
                const fps = Math.round((frameCount * 1000) / elapsed);
                document.getElementById('fps').textContent = fps + ' FPS';
                frameCount = 0;
                lastTime = now;
            }}
        }}

        // =================================================================
        // RENDER LOOP
        // =================================================================

        function onResize() {{
            camera.aspect = window.innerWidth / window.innerHeight;
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight);
        }}

        function animate() {{
            requestAnimationFrame(animate);
            controls.update();
            renderer.render(scene, camera);
            updateFPS();
        }}

        // Start
        init().catch(err => {{
            console.error('Init error:', err);
            document.getElementById('loading').textContent = 'Error: ' + err.message;
        }});
    </script>
</body>
</html>
'''


def render_organism_instanced(
    organism: Organism,
    port: int = 8765,
    open_browser: bool = True,
    use_clustering: bool = True,
    max_level: int = 2
) -> InstancedOrganismRenderer:
    """
    Render organism using GPU-instanced renderer.

    Args:
        organism: The organism to render
        port: Port for local web server
        open_browser: Whether to auto-open browser
        use_clustering: Whether to use hierarchical clustering for large graphs
        max_level: Maximum initial detail level (0=overview, 4=full detail)

    Returns:
        Renderer instance (call .stop() when done)
    """
    renderer = InstancedOrganismRenderer(organism, port, max_level)
    renderer.render(open_browser, use_clustering)
    return renderer
