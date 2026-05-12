#!/usr/bin/env python3
"""
Google Analytics MCP Server wrapper for HTTP transport.
Enables deployment on Railway with Relevance AI integration.
"""

import argparse
import logging
import os
import sys
import socket
from dotenv import load_dotenv

# Load environment variables
dotenv_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
load_dotenv(dotenv_path=dotenv_path)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def safe_print(text):
    """Print safely to stderr to avoid JSON parsing errors."""
    try:
        print(text, file=sys.stderr)
    except UnicodeEncodeError:
        print(text.encode("ascii", errors="replace").decode(), file=sys.stderr)


def main():
    """
    Main entry point for Google Analytics MCP Server.
    Uses FastMCP's native streamable-http transport.
    """
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Google Analytics MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "streamable-http"],
        default="streamable-http",
        help="Transport mode: stdio (default) or streamable-http",
    )
    parser.add_argument(
        "--single-user",
        action="store_true",
        help="Run in single-user mode",
    )
    args = parser.parse_args()

    # Set port and host from environment or defaults
    port = int(os.getenv("PORT", os.getenv("ANALYTICS_MCP_PORT", 8000)))
    host = os.getenv("ANALYTICS_MCP_HOST", "0.0.0.0")
    base_uri = os.getenv("ANALYTICS_MCP_BASE_URI", "http://localhost")
    external_url = os.getenv("ANALYTICS_EXTERNAL_URL")
    display_url = external_url if external_url else f"{base_uri}:{port}"

    safe_print("🔧 Google Analytics MCP Server")
    safe_print("=" * 40)
    safe_print("📋 Server Information:")
    safe_print(f"   🌐 Transport: {args.transport}")
    if args.transport == "streamable-http":
        safe_print(f"   🔗 URL: {display_url}")
    safe_print(f"   🐍 Python: {sys.version.split()[0]}")
    safe_print("")

    # Active Configuration
    safe_print("⚙️ Active Configuration:")
    config_vars = {
        "GOOGLE_PROJECT_ID": os.getenv("GOOGLE_PROJECT_ID", "Not Set"),
        "GOOGLE_APPLICATION_CREDENTIALS": (
            "Set" if os.getenv("GOOGLE_APPLICATION_CREDENTIALS") else "Not Set"
        ),
    }

    for key, value in config_vars.items():
        safe_print(f"   - {key}: {value}")
    safe_print("")

    try:
        # Import the analytics MCP server
        from analytics_mcp.server import app as analytics_app

        safe_print("✅ Google Analytics MCP server imported successfully")
        safe_print("")

        safe_print("📊 Configuration Summary:")
        safe_print(f"   🔧 Transport: {args.transport}")
        safe_print(f"   📝 Log Level: {logging.getLogger().getEffectiveLevel()}")
        safe_print("")

        if args.transport == "streamable-http":
            # Check port availability before starting HTTP server
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.bind((host, port))
            except OSError as e:
                safe_print(f"Socket error: {e}")
                safe_print(
                    f"❌ Port {port} is already in use. Cannot start HTTP server."
                )
                sys.exit(1)

            safe_print(f"🚀 Starting HTTP server on {base_uri}:{port}")
            if external_url:
                safe_print(f"   External URL: {external_url}")
            safe_print("✅ Ready for MCP connections")
            safe_print("")

            # Run with streamable-http transport
            analytics_app.run(
                transport="streamable-http",
                host=host,
                port=port,
                stateless_http=True,
            )
        else:
            safe_print("🚀 Starting STDIO server")
            safe_print("✅ Ready for MCP connections")
            safe_print("")

            # Run with stdio transport (default)
            analytics_app.run()

    except KeyboardInterrupt:
        safe_print("\n👋 Server shutdown requested")
        sys.exit(0)
    except Exception as e:
        safe_print(f"\n❌ Server error: {e}")
        logger.error(f"Unexpected error running server: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
