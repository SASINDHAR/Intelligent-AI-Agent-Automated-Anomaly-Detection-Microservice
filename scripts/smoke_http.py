"""Real localhost HTTP smoke test with a temporary webhook receiver."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]
events = []
class Receiver(BaseHTTPRequestHandler):
    def do_POST(self):
        events.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"accepted":true}')
    def log_message(self, *args):
        pass

receiver = ThreadingHTTPServer(("127.0.0.1", 0), Receiver)
threading.Thread(target=receiver.serve_forever, daemon=True).start()
with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
env = {**os.environ, "LLM_MODE": "offline", "INGEST_API_KEY": "smoke-only",
       "WORKFLOW_WEBHOOK_URL": f"http://127.0.0.1:{receiver.server_port}/hook", "WORKFLOW_TOKEN": ""}
with (ROOT/"docs/http-server.log").open("w") as log:
    server = subprocess.Popen([sys.executable,"-m","uvicorn","app.main:app","--host","127.0.0.1","--port",str(port)], cwd=ROOT, env=env, stdout=log, stderr=log)
    try:
        with httpx.Client(base_url=f"http://127.0.0.1:{port}",timeout=20) as client:
            for _ in range(120):
                try:
                    if client.get("/healthz").status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if server.poll() is not None:
                    raise RuntimeError("Server exited; see log")
                time.sleep(.5)
            else:
                raise RuntimeError("Server not ready")
            outcomes={}
            for kind in ["normal", "anomaly"]:
                response=client.post("/v1/telemetry",json=json.loads((ROOT/f"examples/{kind}.json").read_text()),headers={"X-API-Key":"smoke-only"})
                response.raise_for_status()
                outcomes[kind]=response.json()
            assert outcomes["normal"]["workflow_status"] == "not_needed"
            assert outcomes["anomaly"]["workflow_status"] == "delivered"
            assert len(events) == 1
            assert events[0]["event"]["event_id"] == outcomes["anomaly"]["event_id"]
            (ROOT/"docs/http-smoke.json").write_text(json.dumps({"status":"passed","transport":"real localhost HTTP: uvicorn -> receiver","responses":outcomes,"received_events":events},indent=2))
            print("HTTP smoke passed: normal skipped notification; anomaly delivered exactly once")
    finally:
        server.terminate()
        server.wait(timeout=10)
        receiver.shutdown()
        receiver.server_close()
