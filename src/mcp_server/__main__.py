"""Entry point for the EarthBound Zero AI MCP server.

Usage:
    python -m src.mcp_server

FCEUX must be running with the Lua bridge loaded before calling MCP tools:
    fceux64.exe -lua lua/main.lua <rom_path>
"""

from src.mcp_server.server import mcp

if __name__ == "__main__":
    mcp.run(transport="stdio")
