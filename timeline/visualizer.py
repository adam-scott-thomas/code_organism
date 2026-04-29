# SPDX-License-Identifier: Apache-2.0
"""
CODE ORGANISM: TIMELINE VISUALIZER

Creates the visual timeline UI that shows:
- Progress bar with scrubber
- Playback controls
- Frame markers for calls/returns/exceptions
- Minimap of activity
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from .player import TimelinePlayer


@dataclass
class TimelineVisualizerConfig:
    """Configuration for timeline visualization."""
    height: int = 120
    show_minimap: bool = True
    show_markers: bool = True
    show_waveform: bool = True
    color_calls: str = "#4CAF50"
    color_returns: str = "#2196F3"
    color_exceptions: str = "#F44336"
    color_progress: str = "#FF9800"
    color_background: str = "#1a1a2e"


class TimelineVisualizer:
    """
    Generates the visual timeline component.

    The timeline shows a scrubber bar with markers for
    significant events, a minimap of activity density,
    and playback controls.
    """

    def __init__(self, player: TimelinePlayer, config: TimelineVisualizerConfig | None = None):
        self.player = player
        self.config = config or TimelineVisualizerConfig()

    def generate_html(self) -> str:
        """Generate the HTML/CSS/JS for the timeline component."""
        session = self.player.session
        markers = self._generate_markers()
        waveform = self._generate_waveform()

        return f"""
<div id="timeline-container" style="
    position: fixed;
    bottom: 0;
    left: 0;
    right: 0;
    height: {self.config.height}px;
    background: {self.config.color_background};
    border-top: 1px solid #333;
    padding: 10px 20px;
    box-sizing: border-box;
    font-family: 'Segoe UI', system-ui, sans-serif;
    color: #fff;
    z-index: 1000;
">
    <!-- Header with info -->
    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
        <div id="timeline-info" style="font-size: 12px; color: #888;">
            <span id="frame-counter">Frame 0/{session.metadata.total_frames}</span>
            <span style="margin-left: 20px;" id="event-type">Ready</span>
        </div>
        <div style="display: flex; gap: 10px; align-items: center;">
            <span id="speed-display" style="font-size: 11px; color: #888;">1x</span>
            <span id="time-display" style="font-size: 12px; color: #aaa;">00:00.000</span>
        </div>
    </div>

    <!-- Waveform / Minimap -->
    {self._render_waveform_svg(waveform) if self.config.show_waveform else ""}

    <!-- Timeline track -->
    <div id="timeline-track" style="
        position: relative;
        height: 24px;
        background: #2a2a4a;
        border-radius: 4px;
        margin: 8px 0;
        cursor: pointer;
    ">
        <!-- Markers -->
        {self._render_markers_html(markers) if self.config.show_markers else ""}

        <!-- Progress bar -->
        <div id="timeline-progress" style="
            position: absolute;
            left: 0;
            top: 0;
            bottom: 0;
            width: 0%;
            background: linear-gradient(90deg, {self.config.color_progress}40, {self.config.color_progress}80);
            border-radius: 4px 0 0 4px;
            pointer-events: none;
        "></div>

        <!-- Scrubber handle -->
        <div id="timeline-scrubber" style="
            position: absolute;
            left: 0%;
            top: -4px;
            width: 4px;
            height: 32px;
            background: {self.config.color_progress};
            border-radius: 2px;
            cursor: ew-resize;
            box-shadow: 0 0 8px {self.config.color_progress};
        "></div>
    </div>

    <!-- Controls -->
    <div style="display: flex; justify-content: center; gap: 8px; align-items: center;">
        <button id="btn-seek-start" class="timeline-btn" title="Go to start (Home)">⏮</button>
        <button id="btn-step-back" class="timeline-btn" title="Step back (←)">⏪</button>
        <button id="btn-play-pause" class="timeline-btn timeline-btn-primary" title="Play/Pause (Space)">▶</button>
        <button id="btn-step-forward" class="timeline-btn" title="Step forward (→)">⏩</button>
        <button id="btn-seek-end" class="timeline-btn" title="Go to end (End)">⏭</button>
        <div style="width: 20px;"></div>
        <button id="btn-speed-down" class="timeline-btn timeline-btn-small" title="Slow down (-)">🐢</button>
        <button id="btn-speed-up" class="timeline-btn timeline-btn-small" title="Speed up (+)">🐇</button>
        <div style="width: 20px;"></div>
        <button id="btn-loop" class="timeline-btn timeline-btn-small" title="Toggle loop (L)">🔁</button>
        <div style="width: 20px;"></div>
        <button id="btn-next-call" class="timeline-btn timeline-btn-small" title="Next call (C)" style="background: {self.config.color_calls}40;">📞</button>
        <button id="btn-next-return" class="timeline-btn timeline-btn-small" title="Next return (R)" style="background: {self.config.color_returns}40;">↩️</button>
        <button id="btn-next-exception" class="timeline-btn timeline-btn-small" title="Next exception (E)" style="background: {self.config.color_exceptions}40;">⚠️</button>
    </div>
</div>

<style>
.timeline-btn {{
    background: #3a3a5a;
    border: none;
    color: #fff;
    padding: 8px 16px;
    border-radius: 4px;
    cursor: pointer;
    font-size: 16px;
    transition: all 0.2s;
}}
.timeline-btn:hover {{
    background: #4a4a7a;
    transform: scale(1.05);
}}
.timeline-btn:active {{
    transform: scale(0.95);
}}
.timeline-btn-primary {{
    background: {self.config.color_progress};
    padding: 12px 24px;
    font-size: 20px;
}}
.timeline-btn-primary:hover {{
    background: {self.config.color_progress}cc;
}}
.timeline-btn-small {{
    padding: 6px 12px;
    font-size: 14px;
}}
.timeline-marker {{
    position: absolute;
    top: 0;
    bottom: 0;
    width: 2px;
    opacity: 0.7;
}}
.timeline-marker:hover {{
    opacity: 1;
    transform: scaleX(2);
}}
</style>

<script>
(function() {{
    const timeline = {{
        totalFrames: {session.metadata.total_frames},
        currentFrame: 0,
        isPlaying: false,
        speed: 1.0,
        loop: false,
        frames: {json.dumps(self._get_frame_summary())},
    }};

    // Elements
    const track = document.getElementById('timeline-track');
    const progress = document.getElementById('timeline-progress');
    const scrubber = document.getElementById('timeline-scrubber');
    const playBtn = document.getElementById('btn-play-pause');
    const frameCounter = document.getElementById('frame-counter');
    const eventType = document.getElementById('event-type');
    const speedDisplay = document.getElementById('speed-display');
    const timeDisplay = document.getElementById('time-display');
    const loopBtn = document.getElementById('btn-loop');

    // Update display
    function updateDisplay() {{
        const percent = (timeline.currentFrame / Math.max(1, timeline.totalFrames - 1)) * 100;
        progress.style.width = percent + '%';
        scrubber.style.left = percent + '%';
        frameCounter.textContent = `Frame ${{timeline.currentFrame + 1}}/${{timeline.totalFrames}}`;

        const frame = timeline.frames[timeline.currentFrame];
        if (frame) {{
            eventType.textContent = frame.type;
            eventType.style.color = frame.type === 'call' ? '{self.config.color_calls}'
                : frame.type === 'return' ? '{self.config.color_returns}'
                : frame.type === 'exception' ? '{self.config.color_exceptions}'
                : '#888';

            // Time display
            const ns = frame.elapsed_ns || 0;
            const ms = ns / 1_000_000;
            const secs = Math.floor(ms / 1000);
            const remainder = (ms % 1000).toFixed(3).padStart(7, '0');
            timeDisplay.textContent = `${{String(Math.floor(secs / 60)).padStart(2, '0')}}:${{String(secs % 60).padStart(2, '0')}}.${{remainder.slice(0, 3)}}`;
        }}

        playBtn.textContent = timeline.isPlaying ? '⏸' : '▶';
        speedDisplay.textContent = timeline.speed === 1 ? '1x' : timeline.speed < 1 ? timeline.speed.toFixed(2) + 'x' : timeline.speed + 'x';
        loopBtn.style.opacity = timeline.loop ? 1 : 0.5;

        // Notify 3D renderer
        if (window.onTimelineFrame) {{
            window.onTimelineFrame(timeline.currentFrame, frame);
        }}
    }}

    // Seek to position
    function seekToPercent(percent) {{
        timeline.currentFrame = Math.round(percent * (timeline.totalFrames - 1));
        timeline.currentFrame = Math.max(0, Math.min(timeline.currentFrame, timeline.totalFrames - 1));
        updateDisplay();
    }}

    // Track click
    track.addEventListener('click', (e) => {{
        const rect = track.getBoundingClientRect();
        const percent = (e.clientX - rect.left) / rect.width;
        seekToPercent(percent);
    }});

    // Scrubber drag
    let isDragging = false;
    scrubber.addEventListener('mousedown', () => isDragging = true);
    document.addEventListener('mousemove', (e) => {{
        if (isDragging) {{
            const rect = track.getBoundingClientRect();
            const percent = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
            seekToPercent(percent);
        }}
    }});
    document.addEventListener('mouseup', () => isDragging = false);

    // Playback
    let playInterval = null;
    function play() {{
        if (timeline.isPlaying) return;
        timeline.isPlaying = true;
        updateDisplay();

        const baseInterval = 50; // Base interval in ms
        playInterval = setInterval(() => {{
            timeline.currentFrame++;
            if (timeline.currentFrame >= timeline.totalFrames) {{
                if (timeline.loop) {{
                    timeline.currentFrame = 0;
                }} else {{
                    pause();
                    timeline.currentFrame = timeline.totalFrames - 1;
                }}
            }}
            updateDisplay();
        }}, baseInterval / timeline.speed);
    }}

    function pause() {{
        timeline.isPlaying = false;
        if (playInterval) {{
            clearInterval(playInterval);
            playInterval = null;
        }}
        updateDisplay();
    }}

    function togglePlayPause() {{
        if (timeline.isPlaying) {{
            pause();
        }} else {{
            if (timeline.currentFrame >= timeline.totalFrames - 1) {{
                timeline.currentFrame = 0;
            }}
            play();
        }}
    }}

    // Speed presets
    const speeds = [0.1, 0.25, 0.5, 1.0, 2.0, 4.0, 10.0, 50.0];
    let speedIndex = 3;

    function speedUp() {{
        if (speedIndex < speeds.length - 1) {{
            speedIndex++;
            timeline.speed = speeds[speedIndex];
            if (timeline.isPlaying) {{
                pause();
                play();
            }}
            updateDisplay();
        }}
    }}

    function speedDown() {{
        if (speedIndex > 0) {{
            speedIndex--;
            timeline.speed = speeds[speedIndex];
            if (timeline.isPlaying) {{
                pause();
                play();
            }}
            updateDisplay();
        }}
    }}

    // Button handlers
    document.getElementById('btn-play-pause').addEventListener('click', togglePlayPause);
    document.getElementById('btn-seek-start').addEventListener('click', () => {{ timeline.currentFrame = 0; updateDisplay(); }});
    document.getElementById('btn-seek-end').addEventListener('click', () => {{ timeline.currentFrame = timeline.totalFrames - 1; updateDisplay(); }});
    document.getElementById('btn-step-forward').addEventListener('click', () => {{ timeline.currentFrame = Math.min(timeline.currentFrame + 1, timeline.totalFrames - 1); updateDisplay(); }});
    document.getElementById('btn-step-back').addEventListener('click', () => {{ timeline.currentFrame = Math.max(timeline.currentFrame - 1, 0); updateDisplay(); }});
    document.getElementById('btn-speed-up').addEventListener('click', speedUp);
    document.getElementById('btn-speed-down').addEventListener('click', speedDown);
    document.getElementById('btn-loop').addEventListener('click', () => {{ timeline.loop = !timeline.loop; updateDisplay(); }});

    document.getElementById('btn-next-call').addEventListener('click', () => {{
        for (let i = timeline.currentFrame + 1; i < timeline.totalFrames; i++) {{
            if (timeline.frames[i]?.type === 'call') {{
                timeline.currentFrame = i;
                updateDisplay();
                return;
            }}
        }}
    }});

    document.getElementById('btn-next-return').addEventListener('click', () => {{
        for (let i = timeline.currentFrame + 1; i < timeline.totalFrames; i++) {{
            if (timeline.frames[i]?.type === 'return') {{
                timeline.currentFrame = i;
                updateDisplay();
                return;
            }}
        }}
    }});

    document.getElementById('btn-next-exception').addEventListener('click', () => {{
        for (let i = timeline.currentFrame + 1; i < timeline.totalFrames; i++) {{
            if (timeline.frames[i]?.type === 'exception') {{
                timeline.currentFrame = i;
                updateDisplay();
                return;
            }}
        }}
    }});

    // Keyboard shortcuts
    document.addEventListener('keydown', (e) => {{
        if (e.target.tagName === 'INPUT') return;

        switch(e.code) {{
            case 'Space':
                e.preventDefault();
                togglePlayPause();
                break;
            case 'ArrowRight':
                e.preventDefault();
                timeline.currentFrame = Math.min(timeline.currentFrame + (e.shiftKey ? 10 : 1), timeline.totalFrames - 1);
                updateDisplay();
                break;
            case 'ArrowLeft':
                e.preventDefault();
                timeline.currentFrame = Math.max(timeline.currentFrame - (e.shiftKey ? 10 : 1), 0);
                updateDisplay();
                break;
            case 'Home':
                e.preventDefault();
                timeline.currentFrame = 0;
                updateDisplay();
                break;
            case 'End':
                e.preventDefault();
                timeline.currentFrame = timeline.totalFrames - 1;
                updateDisplay();
                break;
            case 'KeyC':
                document.getElementById('btn-next-call').click();
                break;
            case 'KeyR':
                document.getElementById('btn-next-return').click();
                break;
            case 'KeyE':
                document.getElementById('btn-next-exception').click();
                break;
            case 'KeyL':
                document.getElementById('btn-loop').click();
                break;
            case 'Equal':
            case 'NumpadAdd':
                speedUp();
                break;
            case 'Minus':
            case 'NumpadSubtract':
                speedDown();
                break;
        }}
    }});

    // Expose API
    window.timelineAPI = {{
        play,
        pause,
        togglePlayPause,
        seekToFrame: (frame) => {{ timeline.currentFrame = frame; updateDisplay(); }},
        seekToPercent,
        getCurrentFrame: () => timeline.currentFrame,
        getFrameData: () => timeline.frames[timeline.currentFrame],
        isPlaying: () => timeline.isPlaying,
    }};

    // Initial display
    updateDisplay();
}})();
</script>
"""

    def _generate_markers(self) -> list[dict]:
        """Generate marker data for the timeline."""
        markers = []
        total = self.player.total_frames

        for i, frame in enumerate(self.player.session.frames):
            event_type = frame.get("event_type", "")
            if event_type in ("call", "return", "exception"):
                markers.append({
                    "index": i,
                    "percent": (i / max(1, total - 1)) * 100,
                    "type": event_type,
                })

        return markers

    def _render_markers_html(self, markers: list[dict]) -> str:
        """Render markers as HTML."""
        html_parts = []

        for marker in markers:
            color = (
                self.config.color_calls if marker["type"] == "call"
                else self.config.color_returns if marker["type"] == "return"
                else self.config.color_exceptions
            )
            html_parts.append(f"""
                <div class="timeline-marker" style="
                    left: {marker['percent']}%;
                    background: {color};
                " title="Frame {marker['index']}: {marker['type']}"></div>
            """)

        return "\n".join(html_parts)

    def _generate_waveform(self) -> list[float]:
        """Generate waveform data showing activity density."""
        if not self.player.session.frames:
            return []

        # Divide timeline into buckets
        bucket_count = 100
        buckets = [0] * bucket_count
        total = len(self.player.session.frames)

        for i, frame in enumerate(self.player.session.frames):
            bucket = int((i / total) * bucket_count)
            bucket = min(bucket, bucket_count - 1)

            # Weight by event type
            event_type = frame.get("event_type", "")
            weight = 1.0
            if event_type == "call":
                weight = 1.5
            elif event_type == "exception":
                weight = 2.0

            buckets[bucket] += weight

        # Normalize
        max_val = max(buckets) if buckets else 1
        return [b / max_val for b in buckets]

    def _render_waveform_svg(self, waveform: list[float]) -> str:
        """Render waveform as SVG."""
        if not waveform:
            return ""

        width = 100
        height = 20
        points = []

        for i, val in enumerate(waveform):
            x = (i / len(waveform)) * width
            y = height - (val * height)
            points.append(f"{x},{y}")

        # Close the path
        points.append(f"{width},{height}")
        points.append(f"0,{height}")

        return f"""
        <svg width="100%" height="{height}px" viewBox="0 0 {width} {height}" preserveAspectRatio="none" style="display: block; margin-bottom: 4px; opacity: 0.5;">
            <polygon points="{' '.join(points)}" fill="{self.config.color_progress}40" stroke="{self.config.color_progress}" stroke-width="0.5"/>
        </svg>
        """

    def _get_frame_summary(self) -> list[dict]:
        """Get a summary of each frame for JavaScript."""
        summaries = []
        for frame in self.player.session.frames:
            summaries.append({
                "type": frame.get("event_type", ""),
                "node_id": frame.get("node_id", ""),
                "elapsed_ns": frame.get("elapsed_ns", 0),
            })
        return summaries
