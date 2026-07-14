#!/usr/bin/env python3
"""Cloud Run HTTP server wrapper for prewarm_morning_brief.py"""

import os
import json
import logging
import secrets
import subprocess
import threading
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATE_DIR = Path(os.getenv('AI_JOB_INTERN_STATE_DIR', '/workspace/state'))
ARTIFACT_FILE = STATE_DIR / 'morning_report_ready.json'
PORT = int(os.getenv('PORT', 8080))
PREWARM_API_TOKEN = os.getenv("PREWARM_API_TOKEN", "")
PREWARM_TOKEN_HEADER = "X-Prewarm-Token"
PREWARM_LOCK = threading.Lock()
PREWARM_RUNNING = False

if not PREWARM_API_TOKEN:
    raise RuntimeError("PREWARM_API_TOKEN must be set")


class PrewarmHandler(BaseHTTPRequestHandler):
    """HTTP handler for Cloud Run"""

    def _json_response(self, status: int, payload: dict[str, object]) -> None:
        self.send_response(status)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    def _is_authorized(self) -> bool:
        provided = self.headers.get(PREWARM_TOKEN_HEADER, "")
        return bool(provided) and secrets.compare_digest(provided, PREWARM_API_TOKEN)

    def do_POST(self):
        """Handle POST requests to trigger prewarm"""
        if self.path not in ("/", "/prewarm"):
            self._json_response(404, {"error": "Not found"})
            return
        if not self._is_authorized():
            self._json_response(401, {"error": "Unauthorized"})
            return

        global PREWARM_RUNNING
        if not PREWARM_LOCK.acquire(blocking=False):
            self._json_response(429, {"error": "Prewarm already running"})
            return

        PREWARM_RUNNING = True
        logger.info("Triggering prewarm...")
        try:
            # Run the prewarm script
            result = subprocess.run(
                ['python3', 'fetchers/prewarm_morning_brief.py'],
                capture_output=True,
                text=True,
                timeout=3600
            )
            
            if result.returncode != 0:
                logger.error(f"Prewarm failed: {result.stderr}")
                self._json_response(500, {'error': 'Prewarm failed'})
                return
            
            # Return success
            self._json_response(200, {'status': 'ok', 'message': 'Prewarm completed'})
            logger.info("Prewarm completed")
            
        except Exception as e:
            logger.error(f"Error during prewarm: {e}")
            self._json_response(500, {'error': 'Prewarm failed'})
        finally:
            PREWARM_RUNNING = False
            PREWARM_LOCK.release()

    def do_GET(self):
        """Handle GET requests - return artifact or health check"""
        if self.path == '/health':
            self._json_response(200, {'status': 'healthy', 'prewarm_running': PREWARM_RUNNING})
            return
        
        if self.path == '/artifact':
            if not self._is_authorized():
                self._json_response(401, {'error': 'Unauthorized'})
                return
            if ARTIFACT_FILE.exists():
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                with open(ARTIFACT_FILE, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self._json_response(404, {'error': 'Artifact not ready'})
            return
        
        # Default: not found
        self._json_response(404, {'error': 'Not found'})

    def log_message(self, format, *args):
        """Suppress default logging"""
        logger.info(f"{self.client_address[0]} - {format % args}")


def start_server():
    """Start HTTP server"""
    server_address = ('', PORT)
    httpd = ThreadingHTTPServer(server_address, PrewarmHandler)
    logger.info(f"Server listening on port {PORT}")
    httpd.serve_forever()


if __name__ == '__main__':
    start_server()
