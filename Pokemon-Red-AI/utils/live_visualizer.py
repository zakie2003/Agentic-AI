import json
import mimetypes
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


HTML = """<!doctype html>
<html>
<head>
<meta charset="utf-8">
<title>Pokemon RL Live Map</title>
<style>
body { margin: 0; background: #111827; color: #e5e7eb; font: 14px system-ui, sans-serif; }
header { padding: 12px 18px; display: flex; gap: 10px; align-items: center; background: #1f2937; }
button { background: #374151; color: white; border: 1px solid #4b5563; padding: 6px 11px; cursor: pointer; }
button:hover { background: #4b5563; }
#status { color: #9ca3af; }
main { padding: 16px; }
canvas { display: block; width: 100%; max-width: 1200px; height: auto; aspect-ratio: 1200 / 680; background: #f8fafc; border-radius: 6px; cursor: grab; touch-action: none; }
canvas.dragging { cursor: grabbing; }
</style>
</head>
<body>
<header><strong>Pokemon RL Live Map</strong><button id="zoomOut">-</button><button id="zoomIn">+</button><button id="resetView">Reset view</button><span id="status">Connecting...</span></header>
<main><canvas id="mapCanvas" width="1200" height="680"></canvas></main>
<script>
const TILE = 16;            // pixels per tile in kanto.png (must match the * 16 in Python snapshot())
const SPRITE_TILES = 1.5;   // sprite height in tiles; tweak to taste

const canvas = document.getElementById('mapCanvas');
const ctx = canvas.getContext('2d');
const colors = ['#ef4444', '#2563eb', '#16a34a', '#d97706', '#9333ea', '#0891b2', '#db2777', '#4b5563'];
const mapImage = new Image(); mapImage.src = '/assets/kanto.png';

// GIFs only animate on a canvas if the <img> is attached to the DOM.
const spriteImages = {};
for (const direction of ['down', 'up', 'left', 'right']) {
    const image = new Image();
    image.src = `/assets/red_walk_${direction}.gif`;
    image.style.cssText = 'position:absolute;left:0;top:0;width:1px;height:1px;opacity:0;pointer-events:none;';
    document.body.appendChild(image);
    spriteImages[direction] = image;
}

let state = {paths: []};
let zoom = 1;
let panX = 0;
let panY = 0;
let dragging = false;
let dragStart = null;
const displayedPositions = new Map();

function canvasScale() {
    return canvas.width / canvas.getBoundingClientRect().width;
}

function directionOf(path) {
    // Walk back to the last point that actually differs from the current one.
    const cur = path[path.length - 1];
    for (let i = path.length - 2; i >= 0; i--) {
        const dx = cur[0] - path[i][0];
        const dy = cur[1] - path[i][1];
        if (dx === 0 && dy === 0) continue;
        if (Math.abs(dx) > Math.abs(dy)) return dx > 0 ? 'right' : 'left';
        return dy > 0 ? 'down' : 'up';
    }
    return 'down';
}

function draw() {
    ctx.fillStyle = '#111827';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    if (!mapImage.complete || !mapImage.naturalWidth) return;

    const baseScale = Math.min(canvas.width / mapImage.naturalWidth, canvas.height / mapImage.naturalHeight);
    const scale = baseScale * zoom;
    const width = mapImage.naturalWidth * scale, height = mapImage.naturalHeight * scale;
    const offsetX = (canvas.width - width) / 2 + panX;
    const offsetY = (canvas.height - height) / 2 + panY;

    ctx.imageSmoothingEnabled = false; // Preserves pixel art quality
    ctx.drawImage(mapImage, offsetX, offsetY, width, height);

    const tx = x => offsetX + x * scale;
    const ty = y => offsetY + y * scale;
    const tileScreen = TILE * scale;

    for (const agent of state.paths) {
        if (!agent.path || !agent.path.length) continue;

        const currentPos = agent.path[agent.path.length - 1];
        let displayed = displayedPositions.get(agent.agent);
        if (!displayed) {
            displayed = [...currentPos];
            displayedPositions.set(agent.agent, displayed);
        } else {
            displayed[0] += (currentPos[0] - displayed[0]) * 0.2;
            displayed[1] += (currentPos[1] - displayed[1]) * 0.2;
        }
        const dir = directionOf(agent.path);
        const spriteImage = spriteImages[dir];
        const size = Math.max(10, tileScreen * SPRITE_TILES);

        // center of the tile, in screen space
        const cx = tx(displayed[0] + TILE / 2);
        const cy = ty(displayed[1] + TILE / 2);

        // dot so the exact position is visible even when zoomed far out
        ctx.fillStyle = colors[agent.agent % colors.length];
        ctx.beginPath();
        ctx.arc(cx, cy, Math.max(2, tileScreen * 0.3), 0, Math.PI * 2);
        ctx.fill();

        if (spriteImage.complete && spriteImage.naturalWidth) {
            const aspect = spriteImage.naturalWidth / spriteImage.naturalHeight;
            const w = size * aspect, h = size;
            ctx.drawImage(spriteImage, cx - w / 2, cy - h / 2, w, h);
        }

        ctx.fillStyle = '#ffffff';
        ctx.strokeStyle = '#000000';
        ctx.lineWidth = 3;
        ctx.font = '12px monospace';
        const label = `Agent ${agent.agent + 1}`;
        ctx.strokeText(label, cx - size / 2, cy - size / 2 - 4);
        ctx.fillText(label, cx - size / 2, cy - size / 2 - 4);
    }
}

function animate() {
    draw();
    requestAnimationFrame(animate);
}

function update(data) {
    state = data;
    document.getElementById('status').textContent = `${state.agents} agents | ${state.points} positions`;
}

let polling = false;
async function poll() {
    if (polling) return;
    polling = true;
    try { update(await (await fetch('/state')).json()); } catch (_) {} finally { polling = false; }
}
setInterval(poll, 250); poll(); animate();

document.getElementById('zoomIn').onclick = () => { zoom = Math.min(8, zoom * 1.25); };
document.getElementById('zoomOut').onclick = () => { zoom = Math.max(0.5, zoom / 1.25); };
document.getElementById('resetView').onclick = () => { zoom = 1; panX = 0; panY = 0; };

canvas.addEventListener('wheel', event => {
    event.preventDefault();
    zoom = Math.max(0.5, Math.min(8, zoom * (event.deltaY < 0 ? 1.15 : 0.87)));
}, {passive: false});

canvas.addEventListener('pointerdown', event => {
    dragging = true;
    const k = canvasScale();
    dragStart = {x: event.clientX * k - panX, y: event.clientY * k - panY};
    canvas.classList.add('dragging');
    canvas.setPointerCapture(event.pointerId);
});
canvas.addEventListener('pointermove', event => {
    if (!dragging) return;
    const k = canvasScale();
    panX = event.clientX * k - dragStart.x;
    panY = event.clientY * k - dragStart.y;
});
canvas.addEventListener('pointerup', () => {
    dragging = false;
    canvas.classList.remove('dragging');
});
canvas.addEventListener('pointercancel', () => {
    dragging = false;
    canvas.classList.remove('dragging');
});
</script>
</body>
</html>"""


class LiveMapServer:
    def __init__(self, agent_paths, host="127.0.0.1", port=8765):
        self.agent_paths = agent_paths
        self.map_data = {
            region["id"]: region
            for region in json.loads(
                Path("assets/map_viz/map_data.json").read_text()
            )["regions"]
        }
        self.server = None
        self.thread = None
        self.host = host
        self.port = port

    def snapshot(self):
        paths = []
        total_points = 0
        for agent_index, path in enumerate(self.agent_paths):
            global_path = []
            for map_id, x, y in path:
                region = self.map_data.get(str(map_id))
                if region is None:
                    continue
                origin_x, origin_y = region["coordinates"]
                global_path.append([(origin_x + x) * 16, (origin_y + y) * 16])
                total_points += 1
            if global_path:
                paths.append({"agent": agent_index, "path": global_path})
        return {
            "agents": len(self.agent_paths),
            "points": total_points,
            "paths": paths,
        }

    def start(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/state":
                    body = json.dumps(owner.snapshot()).encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                elif self.path.startswith("/assets/"):
                    asset_path = Path(self.path.removeprefix("/assets/"))
                    asset_path = Path("assets/map_viz") / asset_path.name
                    if not asset_path.exists():
                        self.send_error(404)
                        return
                    body = asset_path.read_bytes()
                    self.send_response(200)
                    content_type = mimetypes.guess_type(asset_path.name)[0] or "application/octet-stream"
                    self.send_header("Content-Type", content_type)
                else:
                    body = HTML.encode()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, *_):
                return

        self.server = ThreadingHTTPServer((self.host, self.port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self):
        if self.server is not None:
            self.server.shutdown()
            self.server.server_close()
            self.server = None