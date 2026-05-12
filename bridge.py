#!/usr/bin/env python3
"""
HTTP-to-stdio MCP bridge for Google Analytics MCP Server.
Allows HTTP clients (like Relevance AI) to communicate with stdio MCP servers.
"""

import json
import logging
import os
import subprocess
import sys
import threading
from contextlib import asynccontextmanager
from typing import Any, Dict
from queue import Queue, Empty
import time

from fastapi import FastAPI, HTTPException, Request
import uvicorn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Timeout for MCP server responses (seconds)
MCP_RESPONSE_TIMEOUT = 10


class BridgeServer:
    """Manages communication between HTTP and stdio MCP server."""

    def __init__(self):
        self.process = None
        self.request_id = 0

    def start_server(self):
        """Start the analytics-mcp stdio server."""
        try:
            logger.info("Starting analytics-mcp server...")
            self.process = subprocess.Popen(
                [sys.executable, "-m", "analytics_mcp.server"],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            logger.info("Analytics MCP server started (PID: %d)", self.process.pid)
        except Exception as e:
            logger.error("Failed to start analytics-mcp server: %s", e)
            raise

    def stop_server(self):
        """Stop the analytics-mcp stdio server."""
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
                logger.info("Analytics MCP server stopped")
            except subprocess.TimeoutExpired:
                self.process.kill()
                logger.warning("Analytics MCP server forcefully terminated")
            except Exception as e:
                logger.error("Error stopping server: %s", e)

    def is_server_running(self) -> bool:
        """Check if server process is still running."""
        return self.process is not None and self.process.poll() is None

    def send_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Send a request to the MCP server and get response."""
        if not self.is_server_running():
            raise RuntimeError("Analytics MCP server is not running")

        try:
            # Send request as JSON to stdin with timeout
            request_json = json.dumps(request) + "\n"
            logger.debug("Sending to MCP server: %s", request_json)
            
            try:
                self.process.stdin.write(request_json)
                self.process.stdin.flush()
            except BrokenPipeError:
                raise RuntimeError("MCP server process disconnected")

            # Read response from stdout with timeout
            start_time = time.time()
            response_line = ""
            
            while time.time() - start_time < MCP_RESPONSE_TIMEOUT:
                try:
                    # Non-blocking read with small timeout
                    response_line = self.process.stdout.readline()
                    if response_line:
                        break
                    time.sleep(0.01)  # Small delay to prevent busy waiting
                except Exception as e:
                    logger.error("Error reading from stdout: %s", e)
                    raise RuntimeError("Failed to read MCP server response")

            if not response_line:
                raise RuntimeError(f"No response from MCP server after {MCP_RESPONSE_TIMEOUT}s")

            logger.debug("Received from MCP server: %s", response_line)
            response = json.loads(response_line)
            return response

        except json.JSONDecodeError as e:
            logger.error("Invalid JSON from MCP server: %s", e)
            raise RuntimeError("MCP server returned invalid JSON")
        except Exception as e:
            logger.error("Error communicating with MCP server: %s", e)
            raise


# Global bridge instance
bridge = BridgeServer()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage server lifecycle."""
    # Startup
    try:
        bridge.start_server()
        logger.info("Bridge server started and ready for connections")
    except Exception as e:
        logger.error("Failed to start bridge: %s", e)
        raise

    yield

    # Shutdown
    bridge.stop_server()
    logger.info("Bridge server shut down")


# Create FastAPI app
app = FastAPI(
    title="Google Analytics MCP HTTP Bridge",
    description="HTTP bridge for stdio-based Google Analytics MCP server",
    lifespan=lifespan,
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    running = bridge.is_server_running()
    logger.debug("Health check: process running = %s", running)
    
    if running:
        return {"status": "healthy", "mcp_server": "running"}
    return {"status": "unhealthy", "mcp_server": "not_running"}


@app.post("/mcp")
async def mcp_request(request: Request):
    """
    Forward MCP requests to the stdio server.
    Accepts raw JSON body.
    """
    try:
        # Read raw body
        body = await request.body()
        logger.debug("Received request body: %s", body.decode() if body else "empty")
        
        if not body:
            raise HTTPException(status_code=400, detail="Empty request body")
        
        # Parse JSON
        request_dict = json.loads(body)
        logger.info("Processing MCP request: %s", request_dict.get("method", "unknown"))

        # Forward to MCP server
        response = bridge.send_request(request_dict)
        logger.debug("MCP response: %s", response)
        return response

    except json.JSONDecodeError as e:
        logger.error("JSON decode error: %s", e)
        raise HTTPException(status_code=400, detail="Invalid JSON in request body")
    except RuntimeError as e:
        logger.error("Server error: %s", e)
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "name": "Google Analytics MCP HTTP Bridge",
        "version": "1.0.0",
        "status": "running" if bridge.is_server_running() else "stopped",
    }


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "0.0.0.0")

    logger.info("Starting HTTP bridge on %s:%d", host, port)
    uvicorn.run(
        app,
        host=host,
        port=port,
        log_level="info",
    )
