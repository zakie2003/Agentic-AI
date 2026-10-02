import json
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
canvas { display: block; width: 100%; max-width: 1200px; height: 680px; background: #f8fafc; border-radius: 6px; cursor: grab; }
canvas.dragging { cursor: grabbing; }
</style>
</head>
<body>
<header><strong>Pokemon RL Live Map</strong><button id="zoomOut">-</button><button id="zoomIn">+</button><button id="resetView">Reset view</button><span id="status">Connecting...</span></header>
<main><canvas id="mapCanvas" width="1200" height="680"></canvas></main>
<script>
const canvas = document.getElementById('mapCanvas');
const ctx = canvas.getContext('2d');
const colors = ['#ef4444', '#2563eb', '#16a34a', '#d97706', '#9333ea', '#0891b2', '#db2777', '#4b5563'];
const mapImage = new Image(); mapImage.src = '/assets/kanto.png';
const spriteImage = new Image(); spriteImage.src = '/assets/characters.png';
let state = {paths: []};
let zoom = 1;
let panX = 0;
let panY = 0;
let dragging = false;
let dragStart = null;
function draw() {
    const baseScale = Math.min(canvas.width / mapImage.width, canvas.height / mapImage.height);
    const scale = baseScale * zoom;
    const width = mapImage.width * scale, height = mapImage.height * scale;
    const offsetX = (canvas.width - width) / 2 + panX;
    const offsetY = (canvas.height - height) / 2 + panY;
    ctx.fillStyle = '#111827'; ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.imageSmoothingEnabled = false;
    ctx.drawImage(mapImage, offsetX, offsetY, width, height);
    const tx = x => offsetX + x * scale, ty = y => offsetY + y * scale;
    for (const agent of state.paths) {
    ctx.strokeStyle = colors[agent.agent % colors.length]; ctx.lineWidth = 2;
    ctx.beginPath();
        agent.path.forEach((q, i) => i ? ctx.lineTo(tx(q[0]), ty(q[1])) : ctx.moveTo(tx(q[0]), ty(q[1])));
    ctx.stroke();
    const last = agent.path[agent.path.length - 1];
    ctx.fillStyle = colors[agent.agent % colors.length];
        ctx.drawImage(spriteImage, 0, 0, 16, 16, tx(last[0]) - 8, ty(last[1]) - 8, 16, 16);
        ctx.beginPath(); ctx.arc(tx(last[0]), ty(last[1]), 3, 0, Math.PI * 2); ctx.fill();
        ctx.fillStyle = '#111827'; ctx.fillText('Agent ' + (agent.agent + 1), tx(last[0]) + 8, ty(last[1]) - 8);
  }
}
function update(data) {
  state = data;
  document.getElementById('status').textContent = `${state.agents} agents | ${state.points} positions`;
  draw();
}
async function poll() { try { update(await (await fetch('/state')).json()); } catch (_) {} }
mapImage.onload = draw; spriteImage.onload = draw; setInterval(poll, 1000); poll();
document.getElementById('zoomIn').onclick = () => { zoom = Math.min(8, zoom * 1.25); draw(); };
document.getElementById('zoomOut').onclick = () => { zoom = Math.max(0.5, zoom / 1.25); draw(); };
document.getElementById('resetView').onclick = () => { zoom = 1; panX = 0; panY = 0; draw(); };
canvas.addEventListener('wheel', event => {
    event.preventDefault();
    zoom = Math.max(0.5, Math.min(8, zoom * (event.deltaY < 0 ? 1.15 : 0.87)));
    draw();
}, {passive: false});
canvas.addEventListener('pointerdown', event => {
    dragging = true;
    dragStart = {x: event.clientX - panX, y: event.clientY - panY};
    canvas.classList.add('dragging');
    canvas.setPointerCapture(event.pointerId);
});
canvas.addEventListener('pointermove', event => {
    if (!dragging) return;
    panX = event.clientX - dragStart.x;
    panY = event.clientY - dragStart.y;
    draw();
});
canvas.addEventListener('pointerup', () => {
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
                    self.send_header("Content-Type", "image/png")
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
