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
from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


class MCPRequest(BaseModel):
    """MCP JSON-RPC request model."""
    jsonrpc: str = "2.0"
    id: Any
    method: str
    params: Dict[str, Any] | None = None


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

    def send_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Send a request to the MCP server and get response."""
        if not self.process or self.process.poll() is not None:
            raise RuntimeError("Analytics MCP server is not running")

        try:
            # Send request as JSON to stdin
            request_json = json.dumps(request) + "\n"
            self.process.stdin.write(request_json)
            self.process.stdin.flush()

            # Read response from stdout
            response_line = self.process.stdout.readline()
            if not response_line:
                raise RuntimeError("No response from MCP server")

            response = json.loads(response_line)
            return response

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
    if bridge.process and bridge.process.poll() is None:
        return {"status": "healthy", "mcp_server": "running"}
    return {"status": "unhealthy", "mcp_server": "not_running"}


@app.post("/mcp")
async def mcp_request(request: MCPRequest):
    """
    Forward MCP requests to the stdio server.

    This endpoint accepts MCP JSON-RPC requests and forwards them
    to the analytics-mcp stdio server, returning the response.
    """
    try:
        logger.debug("Received MCP request: %s", request.method)

        # Convert Pydantic model to dict
        request_dict = request.model_dump(exclude_none=True)

        # Forward to MCP server
        response = bridge.send_request(request_dict)

        logger.debug("MCP response: %s", response)
        return response

    except RuntimeError as e:
        logger.error("Server error: %s", e)
        raise HTTPException(status_code=503, detail=str(e))
    except json.JSONDecodeError as e:
        logger.error("JSON decode error: %s", e)
        raise HTTPException(status_code=400, detail="Invalid JSON response from MCP server")
    except Exception as e:
        logger.error("Unexpected error: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Google Analytics MCP HTTP Bridge",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "mcp": "/mcp",
        },
        "documentation": "/docs",
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
