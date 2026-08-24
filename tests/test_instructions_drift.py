"""Drift test - INSTRUCTIONS consistent with the tools actually registered.

Two directions, both load-bearing:
- instructions must not name a tool that is not registered (stale documentation)
- every registered tool must be named in the instructions (a capability shipped
  without routing the model to it)
"""

from __future__ import annotations

import re
from pathlib import Path

from br_eli_mcp.server import INSTRUCTIONS, mcp

SRC = (Path(__file__).parent.parent / "src" / "br_eli_mcp" / "server.py").read_text(encoding="utf-8")


def _registered_tool_names() -> set[str]:
    if hasattr(mcp, "_tool_manager"):
        tools = getattr(mcp._tool_manager, "_tools", {})
        if tools:
            return set(tools.keys())
    return set(re.findall(r"@mcp\.tool\([^)]*\)\s+async def (\w+)", SRC))


def _referenced_tool_names_in_instructions() -> set[str]:
    out: set[str] = set()
    for m in re.finditer(r"`([a-z][a-z0-9_]{3,})`", INSTRUCTIONS):
        token = m.group(1)
        if "_" in token:
            out.add(token)
    return out


def test_instructions_only_reference_registered_tools():
    registered = _registered_tool_names()
    referenced = {r for r in _referenced_tool_names_in_instructions() if r in registered or r.startswith("br_")}
    orphan = referenced - registered
    assert not orphan, (
        f"INSTRUCTIONS reference tools not registered: {orphan}. Registered: {sorted(registered)}."
    )


def test_all_registered_tools_mentioned_in_instructions():
    """A tool the instructions never mention is registered but not routed."""
    registered = _registered_tool_names()
    # a tool may be named bare (`tool`) or with a call example (`tool(arg=...)`) - both route the model
    missing = {
        t for t in registered
        if f"`{t}`" not in INSTRUCTIONS and f"`{t}(" not in INSTRUCTIONS
    }
    assert not missing, f"Registered tools absent from INSTRUCTIONS: {missing}"
