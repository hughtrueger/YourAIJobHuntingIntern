#!/usr/bin/env python3
"""Cloud Run HTTP server wrapper for prewarm_morning_brief.py"""

import os
import json
import logging
import subprocess
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

STATE_DIR = Path(os.getenv('AI_JOB_INTERN_STATE_DIR', '/workspace/state'))
ARTIFACT_FILE = STATE_DIR / 'morning_report_ready.json'
PORT = int(os.getenv('PORT', 8080))


class PrewarmHandler(BaseHTTPRequestHandler):
    """HTTP handler for Cloud Run"""

    def do_POST(self):
        """Handle POST requests to trigger prewarm"""
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
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Prewarm failed'}).encode())
                return
            
            # Return success
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok', 'message': 'Prewarm completed'}).encode())
            logger.info("Prewarm completed")
            
        except Exception as e:
            logger.error(f"Error during prewarm: {e}")
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(e)}).encode())

    def do_GET(self):
        """Handle GET requests - return artifact or health check"""
        if self.path == '/health':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'healthy'}).encode())
            return
        
        if self.path == '/artifact':
            if ARTIFACT_FILE.exists():
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                with open(ARTIFACT_FILE, 'rb') as f:
                    self.wfile.write(f.read())
            else:
                self.send_response(404)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Artifact not ready'}).encode())
            return
        
        # Default: not found
        self.send_response(404)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'error': 'Not found'}).encode())

    def log_message(self, format, *args):
        """Suppress default logging"""
        logger.info(f"{self.client_address[0]} - {format % args}")


def start_server():
    """Start HTTP server"""
    server_address = ('', PORT)
    httpd = HTTPServer(server_address, PrewarmHandler)
    logger.info(f"Server listening on port {PORT}")
    httpd.serve_forever()


if __name__ == '__main__':
    start_server()
