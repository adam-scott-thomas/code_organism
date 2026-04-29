"""
CODE ORGANISM: PLAYBACK RENDERER

Integrates the 3D organism visualization with timeline playback.
Watch your code execute in real-time, with the ability to
pause, rewind, and slow down to see every detail.
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
from ..timeline.recorder import RecordingSession
from ..timeline.player import TimelinePlayer
from ..timeline.visualizer import TimelineVisualizer, TimelineVisualizerConfig


class PlaybackRenderer:
    """
    Renders an organism with timeline playback controls.

    Combines the 3D visualization with execution recording,
    allowing you to watch code run like a nature documentary.
    """

    def __init__(
        self,
        session: RecordingSession,
        port: int = 8765,
        timeline_config: Optional[TimelineVisualizerConfig] = None,
        bind: str = "127.0.0.1",
    ):
        self.session = session
        self.port = port
        self.bind = bind
        self.player = TimelinePlayer(session)
        self.timeline_viz = TimelineVisualizer(self.player, timeline_config)

        self.server: Optional[socketserver.TCPServer] = None
        self.server_thread: Optional[threading.Thread] = None

    @classmethod
    def from_file(
        cls, filepath: Path, port: int = 8765, bind: str = "127.0.0.1"
    ) -> PlaybackRenderer:
        """Load from a recording file."""
        session = RecordingSession.load(filepath)
        return cls(session, port, bind=bind)

    def render(self, open_browser: bool = True) -> str:
        """Start the visualization and return the URL."""
        html_content = self._generate_html()

        # Create temp directory
        self.temp_dir = tempfile.mkdtemp(prefix="code_organism_playback_")
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
        """Start the HTTP server."""
        os.chdir(self.temp_dir)
        handler = http.server.SimpleHTTPRequestHandler
        self.server = socketserver.TCPServer((self.bind, self.port), handler)

        self.server_thread = threading.Thread(target=self.server.serve_forever)
        self.server_thread.daemon = True
        self.server_thread.start()

        print(f"Code Organism Playback at http://localhost:{self.port}")
        print("   Press Ctrl+C to stop")

    def stop(self) -> None:
        """Stop the server."""
        if self.server:
            self.server.shutdown()

    def _generate_html(self) -> str:
        """Generate the complete playback HTML."""
        organism_data = self.session.organism_snapshot
        timeline_html = self.timeline_viz.generate_html()

        return f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Code Organism Playback: {self.session.metadata.organism_name}</title>
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
            height: calc(100vh - 120px);
        }}

        #info-panel {{
            position: fixed;
            top: 20px;
            left: 20px;
            background: rgba(10, 10, 20, 0.95);
            border: 1px solid #333;
            border-radius: 8px;
            padding: 15px;
            min-width: 300px;
            max-width: 400px;
            backdrop-filter: blur(10px);
            z-index: 100;
        }}

        #info-panel h1 {{
            font-size: 1.2em;
            color: #fa8;
            margin-bottom: 10px;
            display: flex;
            align-items: center;
            gap: 8px;
        }}

        #info-panel h1::before {{
            content: "🎬";
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

        #current-frame-info {{
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #444;
        }}

        #current-frame-info h2 {{
            font-size: 1em;
            color: #8af;
            margin-bottom: 8px;
        }}

        .event-call {{ color: #4CAF50; }}
        .event-return {{ color: #2196F3; }}
        .event-exception {{ color: #F44336; }}

        #call-stack {{
            margin-top: 10px;
            font-size: 0.85em;
            max-height: 150px;
            overflow-y: auto;
        }}

        #call-stack .stack-frame {{
            padding: 2px 0;
            color: #888;
            font-family: monospace;
        }}

        #call-stack .stack-frame.current {{
            color: #fa8;
            font-weight: bold;
        }}

        #variables {{
            margin-top: 10px;
            font-size: 0.85em;
            max-height: 120px;
            overflow-y: auto;
        }}

        .var-row {{
            display: flex;
            justify-content: space-between;
            padding: 2px 0;
        }}

        .var-name {{
            color: #a8f;
            font-family: monospace;
        }}

        .var-value {{
            color: #8af;
            font-family: monospace;
            max-width: 180px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}

        #legend {{
            position: fixed;
            top: 20px;
            right: 20px;
            background: rgba(10, 10, 20, 0.95);
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
            color: #fa8;
            z-index: 1000;
        }}

        #loading.hidden {{
            display: none;
        }}

        .pulse {{
            animation: pulse 1s infinite;
        }}

        @keyframes pulse {{
            0%, 100% {{ opacity: 1; }}
            50% {{ opacity: 0.5; }}
        }}
    </style>
</head>
<body>
    <div id="loading">🎬 Loading playback...</div>

    <div id="container"></div>

    <div id="info-panel">
        <h1>Playback: {self.session.metadata.organism_name}</h1>
        <div class="stat-row">
            <span class="stat-label">Recording:</span>
            <span class="stat-value">{self.session.metadata.session_id}</span>
        </div>
        <div class="stat-row">
            <span class="stat-label">Frames:</span>
            <span class="stat-value">{self.session.metadata.total_frames}</span>
        </div>
        <div class="stat-row">
            <span class="stat-label">Nodes:</span>
            <span class="stat-value">{self.session.metadata.node_count}</span>
        </div>
        <div class="stat-row">
            <span class="stat-label">Files:</span>
            <span class="stat-value">{self.session.metadata.file_count}</span>
        </div>

        <div id="current-frame-info">
            <h2 id="current-event">Ready</h2>
            <div class="stat-row">
                <span class="stat-label">Function:</span>
                <span class="stat-value" id="current-function">-</span>
            </div>
            <div class="stat-row">
                <span class="stat-label">Location:</span>
                <span class="stat-value" id="current-location">-</span>
            </div>

            <div id="call-stack">
                <strong style="color: #666;">Call Stack:</strong>
            </div>

            <div id="variables">
                <strong style="color: #666;">Local Variables:</strong>
            </div>
        </div>
    </div>

    <div id="legend">
        <h3>Event Types</h3>
        <div class="legend-item">
            <div class="legend-color" style="background: #4CAF50"></div>
            <span>Call</span>
        </div>
        <div class="legend-item">
            <div class="legend-color" style="background: #2196F3"></div>
            <span>Return</span>
        </div>
        <div class="legend-item">
            <div class="legend-color" style="background: #F44336"></div>
            <span>Exception</span>
        </div>
        <h3 style="margin-top: 15px;">Keyboard Shortcuts</h3>
        <div class="legend-item">
            <span style="color: #aef; font-family: monospace;">Space</span>
            <span>Play/Pause</span>
        </div>
        <div class="legend-item">
            <span style="color: #aef; font-family: monospace;">←/→</span>
            <span>Step</span>
        </div>
        <div class="legend-item">
            <span style="color: #aef; font-family: monospace;">+/-</span>
            <span>Speed</span>
        </div>
    </div>

    <!-- Timeline (injected from TimelineVisualizer) -->
    {timeline_html}

    <!-- Three.js -->
    <script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
    <script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>

    <script>
        // Organism and frame data
        const organismData = {json.dumps(organism_data)};
        const allFrames = {json.dumps([f for f in self.session.frames])};

        // Scene setup
        let scene, camera, renderer, controls;
        let nodeMeshes = {{}};
        let edgeLines = [];
        let activeNodeId = null;

        function init() {{
            // Scene
            scene = new THREE.Scene();
            scene.background = new THREE.Color(0x0a0a0f);

            // Camera
            camera = new THREE.PerspectiveCamera(
                60,
                window.innerWidth / (window.innerHeight - 120),
                0.1,
                1000
            );
            camera.position.set(0, 20, 40);

            // Renderer
            renderer = new THREE.WebGLRenderer({{ antialias: true }});
            renderer.setSize(window.innerWidth, window.innerHeight - 120);
            renderer.setPixelRatio(window.devicePixelRatio);
            document.getElementById('container').appendChild(renderer.domElement);

            // Controls
            controls = new THREE.OrbitControls(camera, renderer.domElement);
            controls.enableDamping = true;
            controls.dampingFactor = 0.05;

            // Lighting
            scene.add(new THREE.AmbientLight(0x404040, 0.5));
            const dirLight = new THREE.DirectionalLight(0xffffff, 0.8);
            dirLight.position.set(10, 20, 10);
            scene.add(dirLight);

            scene.fog = new THREE.FogExp2(0x0a0a0f, 0.01);

            // Build organism
            buildOrganism();

            // Events
            window.addEventListener('resize', onWindowResize);

            // Hook into timeline
            window.onTimelineFrame = onTimelineFrame;

            // Hide loading
            document.getElementById('loading').classList.add('hidden');

            animate();
        }}

        function buildOrganism() {{
            const nodes = organismData.nodes || [];
            const edges = organismData.edges || [];

            // Layout
            const positions = layoutNodes(nodes, edges);

            // Create nodes
            nodes.forEach(node => {{
                const pos = positions[node.id] || {{ x: 0, y: 0, z: 0 }};

                let geometry;
                const size = node.size || 1;

                switch (node.type) {{
                    case 'module':
                    case 'package':
                        geometry = new THREE.BoxGeometry(size, size, size);
                        break;
                    case 'class':
                        geometry = new THREE.OctahedronGeometry(size * 0.6);
                        break;
                    default:
                        geometry = new THREE.SphereGeometry(size * 0.4, 16, 16);
                }}

                const color = new THREE.Color(
                    node.color ? node.color[0] : 0.5,
                    node.color ? node.color[1] : 0.5,
                    node.color ? node.color[2] : 0.8
                );

                const material = new THREE.MeshPhongMaterial({{
                    color: color,
                    emissive: new THREE.Color(0x000000),
                    transparent: true,
                    opacity: 0.7,
                }});

                const mesh = new THREE.Mesh(geometry, material);
                mesh.position.set(pos.x, pos.y, pos.z);
                mesh.userData = {{ ...node, baseColor: color.clone() }};

                scene.add(mesh);
                nodeMeshes[node.id] = mesh;
            }});

            // Create edges
            edges.forEach(edge => {{
                const source = nodeMeshes[edge.source];
                const target = nodeMeshes[edge.target];

                if (source && target) {{
                    const geometry = new THREE.BufferGeometry().setFromPoints([
                        source.position.clone(),
                        target.position.clone()
                    ]);

                    const material = new THREE.LineBasicMaterial({{
                        color: 0x334455,
                        transparent: true,
                        opacity: 0.2,
                    }});

                    const line = new THREE.Line(geometry, material);
                    scene.add(line);
                    edgeLines.push({{ line, source: edge.source, target: edge.target }});
                }}
            }});
        }}

        function layoutNodes(nodes, edges) {{
            const positions = {{}};

            nodes.forEach((node, i) => {{
                const theta = Math.random() * Math.PI * 2;
                const phi = Math.acos(2 * Math.random() - 1);
                const r = 15 + Math.random() * 10;

                positions[node.id] = {{
                    x: r * Math.sin(phi) * Math.cos(theta),
                    y: r * Math.sin(phi) * Math.sin(theta),
                    z: r * Math.cos(phi),
                    vx: 0, vy: 0, vz: 0
                }};
            }});

            // Force simulation
            for (let iter = 0; iter < 80; iter++) {{
                const ids = Object.keys(positions);

                // Repulsion
                for (let i = 0; i < ids.length; i++) {{
                    for (let j = i + 1; j < ids.length; j++) {{
                        const a = positions[ids[i]], b = positions[ids[j]];
                        const dx = b.x - a.x, dy = b.y - a.y, dz = b.z - a.z;
                        const dist = Math.sqrt(dx*dx + dy*dy + dz*dz) + 0.1;
                        const force = 400 / (dist * dist);
                        const fx = (dx/dist)*force, fy = (dy/dist)*force, fz = (dz/dist)*force;
                        a.vx -= fx; a.vy -= fy; a.vz -= fz;
                        b.vx += fx; b.vy += fy; b.vz += fz;
                    }}
                }}

                // Attraction
                edges.forEach(e => {{
                    const a = positions[e.source], b = positions[e.target];
                    if (!a || !b) return;
                    const dx = b.x-a.x, dy = b.y-a.y, dz = b.z-a.z;
                    const dist = Math.sqrt(dx*dx + dy*dy + dz*dz) + 0.1;
                    const force = dist * 0.04;
                    const fx = (dx/dist)*force, fy = (dy/dist)*force, fz = (dz/dist)*force;
                    a.vx += fx; a.vy += fy; a.vz += fz;
                    b.vx -= fx; b.vy -= fy; b.vz -= fz;
                }});

                // Apply
                ids.forEach(id => {{
                    const p = positions[id];
                    p.x += p.vx; p.y += p.vy; p.z += p.vz;
                    p.vx *= 0.9; p.vy *= 0.9; p.vz *= 0.9;
                }});
            }}

            return positions;
        }}

        function onTimelineFrame(frameIndex, frameData) {{
            if (!frameData) return;

            const frame = allFrames[frameIndex];
            if (!frame) return;

            // Update info panel
            const eventType = frame.event_type || '';
            const eventEl = document.getElementById('current-event');
            eventEl.textContent = eventType.charAt(0).toUpperCase() + eventType.slice(1);
            eventEl.className = 'event-' + eventType;

            const eventData = frame.event_data || {{}};
            document.getElementById('current-function').textContent =
                eventData.qualified_name || eventData.function || '-';
            document.getElementById('current-location').textContent =
                (eventData.filename ? eventData.filename.split(/[\\/]/).pop() : '') +
                (eventData.lineno ? ':' + eventData.lineno : '');

            // Update call stack
            const stackEl = document.getElementById('call-stack');
            const stack = frame.call_stack || [];
            stackEl.innerHTML = '<strong style="color: #666;">Call Stack:</strong>' +
                stack.map((s, i) => `<div class="stack-frame ${{i === stack.length-1 ? 'current' : ''}}">${{s}}</div>`).join('');

            // Update variables
            const varsEl = document.getElementById('variables');
            const vars = frame.local_vars || {{}};
            const varEntries = Object.entries(vars).slice(0, 8);
            varsEl.innerHTML = '<strong style="color: #666;">Local Variables:</strong>' +
                varEntries.map(([k, v]) =>
                    `<div class="var-row"><span class="var-name">${{k}}</span><span class="var-value">${{v}}</span></div>`
                ).join('');

            // Highlight active node
            highlightNode(frame.node_id, eventType);
        }}

        function highlightNode(nodeId, eventType) {{
            // Reset previous
            if (activeNodeId && nodeMeshes[activeNodeId]) {{
                const mesh = nodeMeshes[activeNodeId];
                mesh.material.emissive.setHex(0x000000);
                mesh.material.opacity = 0.7;
                mesh.scale.setScalar(1);
            }}

            // Highlight new
            activeNodeId = nodeId;
            if (nodeId && nodeMeshes[nodeId]) {{
                const mesh = nodeMeshes[nodeId];
                const colors = {{
                    call: 0x4CAF50,
                    return: 0x2196F3,
                    exception: 0xF44336,
                }};
                mesh.material.emissive.setHex(colors[eventType] || 0xFF9800);
                mesh.material.opacity = 1.0;
                mesh.scale.setScalar(1.3);

                // Highlight connected edges
                edgeLines.forEach(e => {{
                    if (e.source === nodeId || e.target === nodeId) {{
                        e.line.material.opacity = 0.6;
                        e.line.material.color.setHex(colors[eventType] || 0xFF9800);
                    }} else {{
                        e.line.material.opacity = 0.2;
                        e.line.material.color.setHex(0x334455);
                    }}
                }});
            }}
        }}

        function onWindowResize() {{
            camera.aspect = window.innerWidth / (window.innerHeight - 120);
            camera.updateProjectionMatrix();
            renderer.setSize(window.innerWidth, window.innerHeight - 120);
        }}

        function animate() {{
            requestAnimationFrame(animate);
            controls.update();

            // Pulse active node
            if (activeNodeId && nodeMeshes[activeNodeId]) {{
                const t = Date.now() * 0.005;
                const scale = 1.2 + Math.sin(t) * 0.15;
                nodeMeshes[activeNodeId].scale.setScalar(scale);
            }}

            renderer.render(scene, camera);
        }}

        document.addEventListener('DOMContentLoaded', init);
    </script>
</body>
</html>
'''


def render_playback(
    session: RecordingSession,
    port: int = 8765,
    open_browser: bool = True
) -> PlaybackRenderer:
    """
    Render a recording session with playback controls.

    Args:
        session: The recorded session to play back
        port: Port for the web server
        open_browser: Whether to open browser automatically

    Returns:
        The renderer instance
    """
    renderer = PlaybackRenderer(session, port)
    renderer.render(open_browser)
    return renderer


def render_playback_file(
    filepath: Path,
    port: int = 8765,
    open_browser: bool = True
) -> PlaybackRenderer:
    """
    Render a playback from a saved recording file.

    Args:
        filepath: Path to the .corg or .corg.gz file
        port: Port for the web server
        open_browser: Whether to open browser automatically

    Returns:
        The renderer instance
    """
    renderer = PlaybackRenderer.from_file(filepath, port)
    renderer.render(open_browser)
    return renderer
