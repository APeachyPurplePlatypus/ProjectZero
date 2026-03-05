"""MCP server entry point for Claude Desktop.

Claude Desktop spawns MCP servers without setting the working directory,
so 'python -m src.mcp_server' would fail (can't find the src package).
This script adds the project root to sys.path before importing.

Registered in Claude Desktop's claude_desktop_config.json as:
  "command": "python",
  "args": ["C:/Users/david/ProjectZero/project_begin/scripts/mcp_entry.py"]
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.mcp_server.server import mcp

mcp.run(transport="stdio")
