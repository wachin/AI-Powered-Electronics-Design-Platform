"""
Independent validation of a generated design using an optional MCP server.

This project already validates its own output deterministically (schema, MPN
existence, pin resolution, ERC, and a `kicad-cli` netlist/DRC/Gerber check). This
module adds a *second, independent* opinion: it hands the generated project to
the `kicad-mcp-server` and asks it to run ERC and DRC.

Why a second opinion is worth having: the round-trip through another tool can
catch mistakes our own checks cannot see, because our checks share assumptions
with our generators. If the MCP server disagrees with us, that is worth reading.

Nothing here is required to produce a design. If no MCP server is configured,
the functions return an "unavailable" result and the pipeline continues.

The server reads projects from a directory given by ``KICAD_MCP_PROJECTS_BASE``,
so a generated project is copied into a scratch directory and never modified in
place.
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.agents.mcp_client import MCPResult, create_mcp_client
from src.agents.mcp_registry import get_spec, is_ready, launch_recipe

logger = logging.getLogger(__name__)

_PROJECT_SUFFIXES = (".kicad_sch", ".kicad_pcb", ".kicad_pro")

# KiCad reports these when its *global* library table is not populated, even
# though the board embeds the footprint. They are an environment notice rather
# than a defect in the design.
_LIBRARY_NOTICE_TYPES = {"lib_footprint_issues", "lib_symbol_issues"}


@dataclass
class MCPValidation:
    """Outcome of asking an MCP server to validate a design."""

    available: bool
    project_name: str = ""
    erc: Optional[Dict[str, Any]] = None
    drc: Optional[Dict[str, Any]] = None
    error: str = ""
    notes: List[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        """True when both checks ran, regardless of violation count."""
        if not self.available:
            return False
        erc_ok = (self.erc or {}).get("success") is True
        drc_ok = (self.drc or {}).get("success") is True
        return erc_ok and drc_ok

    @property
    def violations(self) -> int:
        """Total violations reported by ERC and DRC."""
        return int((self.erc or {}).get("violations") or 0) + int(
            (self.drc or {}).get("violations") or 0
        )

    @property
    def only_library_warnings(self) -> bool:
        """True when every DRC finding is a missing-library notice."""
        summary = (self.drc or {}).get("summary") or []
        kinds = {item.get("type") for item in summary if isinstance(item, dict)}
        return bool(kinds) and kinds <= _LIBRARY_NOTICE_TYPES

    def to_dict(self) -> Dict[str, Any]:
        return {
            "available": self.available,
            "project_name": self.project_name,
            "passed": self.passed,
            "violations": self.violations,
            "only_library_warnings": self.only_library_warnings,
            "erc": self.erc,
            "drc": self.drc,
            "error": self.error,
            "notes": self.notes,
        }


def mcp_validation_available(server: str = "kicad") -> bool:
    """True when the named MCP server is set up and launchable."""
    try:
        return is_ready(get_spec(server))
    except KeyError:
        return False


def _stage_project(files: Dict[str, Path], workspace: Path, name: str) -> Optional[Path]:
    """Copy a generated KiCad project into the MCP server's workspace."""
    copied: List[Path] = []
    for path in files.values():
        candidate = Path(path)
        if candidate.suffix in _PROJECT_SUFFIXES and candidate.exists():
            destination = workspace / name / candidate.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate, destination)
            copied.append(destination)
    return copied[0].parent if copied else None


def _parse(result: MCPResult) -> Dict[str, Any]:
    """
    Extract the JSON payload a tool returned.

    The client returns the JSON-RPC result, whose own ``content`` key holds a
    list of MCP content blocks, each carrying a JSON string in ``text``.
    """
    if not getattr(result, "success", False):
        return {
            "success": False,
            "error": getattr(result, "error", None) or "tool call failed",
        }

    content = getattr(result, "content", None)
    if isinstance(content, dict) and "content" in content:
        content = content["content"]

    if isinstance(content, dict):
        return content

    for block in content if isinstance(content, list) else []:
        text = block.get("text") if isinstance(block, dict) else block
        if not text:
            continue
        try:
            parsed = json.loads(text)
        except (TypeError, ValueError):
            return {"success": True, "raw": text}
        if isinstance(parsed, dict):
            return parsed
        return {"success": True, "result": parsed}

    return {"success": True, "raw": str(content)}


async def validate_with_mcp(
    files: Dict[str, Path],
    workspace: Path,
    project_name: str = "design",
    server: str = "kicad",
) -> MCPValidation:
    """
    Run ERC and DRC on a generated project through an MCP server.

    Never raises for infrastructure reasons: a missing or failing server yields a
    result with ``available=False`` so callers can report it without aborting the
    primary pipeline.
    """
    if not mcp_validation_available(server):
        return MCPValidation(
            available=False,
            error=(
                f"MCP server '{server}' is not set up. "
                "Run: ai-electronics-design mcp-setup"
            ),
        )

    workspace = Path(workspace).resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    staged = _stage_project(files, workspace, project_name)
    if staged is None:
        return MCPValidation(
            available=False,
            error="no .kicad_sch/.kicad_pcb files were available to validate",
        )

    recipe = launch_recipe(
        server,
        {
            "KICAD_MCP_PROJECTS_BASE": str(workspace),
            "KICAD_MCP_TASKS_DIR": str(workspace / ".tasks"),
        },
    )
    if recipe is None:
        return MCPValidation(available=False, error=f"could not launch '{server}'")

    command, env = recipe
    validation = MCPValidation(available=True, project_name=project_name)
    try:
        async with create_mcp_client(
            command=command[0], args=command[1:], env=env
        ) as client:
            for tool, attribute in (("run_erc", "erc"), ("run_drc", "drc")):
                try:
                    result = await client.call_tool(tool, {"project": project_name})
                    setattr(validation, attribute, _parse(result))
                except Exception as exc:  # noqa: BLE001 - report, do not abort
                    logger.warning("MCP %s failed: %s", tool, exc)
                    validation.notes.append(f"{tool} failed: {exc}")
    except Exception as exc:  # noqa: BLE001 - infrastructure problem
        logger.warning("MCP validation could not run: %s", exc)
        validation.available = False
        validation.error = str(exc)
    return validation


__all__ = [
    "MCPValidation",
    "mcp_validation_available",
    "validate_with_mcp",
]
