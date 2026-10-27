"""
Create and inspect isolated virtual environments for optional MCP servers.

Each server gets its own environment under ``.mcp_envs/<key>``. Because the
servers are launched as separate processes, they can hold conflicting
dependencies without affecting this project or each other.

This is deliberately a *manager*, not an installer that runs automatically
during setup: creating environments downloads packages, so it is an explicit
action (``ai-electronics-design mcp-setup``) rather than a side effect.
"""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

from src.agents.mcp_registry import (
    MCP_ENV_ROOT,
    MCPServerSpec,
    get_spec,
    is_ready,
    status,
)


@dataclass
class SetupResult:
    key: str
    ok: bool
    created_venv: bool = False
    installed: List[str] = None  # type: ignore[assignment]
    error: str = ""
    command: Optional[List[str]] = None

    def __post_init__(self) -> None:
        if self.installed is None:
            self.installed = []


class MCPServerManager:
    """Creates per-server environments and reports their readiness."""

    def __init__(self, base_dir: Optional[Path] = None, verbose: bool = False):
        self.base_dir = Path(base_dir) if base_dir else MCP_ENV_ROOT
        self.verbose = verbose

    # -- helpers -------------------------------------------------------------

    def _log(self, message: str) -> None:
        if self.verbose:
            print(f"    {message}")

    def _run(self, cmd: List[str], cwd: Optional[Path] = None) -> subprocess.CompletedProcess:
        self._log("$ " + " ".join(cmd))
        return subprocess.run(
            cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True
        )

    def _venv_python(self, spec: MCPServerSpec) -> Path:
        env_dir = self.base_dir / spec.key
        if sys.platform == "win32":  # pragma: no cover
            return env_dir / "Scripts" / "python.exe"
        return env_dir / "bin" / "python"

    # -- creation ------------------------------------------------------------

    def ensure_env(self, spec: MCPServerSpec) -> tuple[bool, bool, str]:
        """Create the server's venv if missing. Returns (ok, created, error)."""
        env_dir = self.base_dir / spec.key
        python = self._venv_python(spec)

        if python.exists():
            return True, False, ""

        self.base_dir.mkdir(parents=True, exist_ok=True)
        result = self._run([sys.executable, "-m", "venv", str(env_dir)])
        if result.returncode != 0:
            return False, False, (
                f"could not create virtual environment: "
                f"{(result.stderr or result.stdout).strip()[:300]}"
            )
        if not python.exists():
            return False, True, "virtual environment created but interpreter missing"
        return True, True, ""

    def install(self, key: str) -> SetupResult:
        """Set up one server's environment and install its dependencies."""
        spec = get_spec(key)
        result = SetupResult(key=key, ok=False)

        ok, created, error = self.ensure_env(spec)
        result.created_venv = created
        if not ok:
            result.error = error
            return result

        python = self._venv_python(spec)

        requirements: List[str] = []
        if spec.install:
            requirements = list(spec.install)
        elif spec.source_dir is not None:
            if not spec.source_dir.exists():
                # `external/` was removed and must not come back (AGENTS.md):
                # installable code is declared in pyproject.toml, never cloned
                # into the tree. This branch only runs for a server that has no
                # published package, and the message has to say so instead of
                # pointing at a submodule that no longer exists.
                result.error = (
                    f"source not found: {spec.source_dir}. This server has no "
                    "published package; declare it in pyproject.toml (PyPI or a "
                    "git+https:// URL) instead of vendoring a checkout."
                )
                return result
            requirements = [str(spec.source_dir.parent)]

        if not requirements:
            result.error = "nothing to install (no PyPI package and no source directory)"
            return result

        upgrade = self._run(
            [str(python), "-m", "pip", "install", "--upgrade", "pip"]
        )
        if upgrade.returncode != 0:
            self._log((upgrade.stderr or "").strip()[:200])

        install = self._run(
            [str(python), "-m", "pip", "install", *requirements]
        )
        result.installed = requirements
        if install.returncode != 0:
            result.error = (install.stderr or install.stdout).strip()[-500:]
            return result

        # For source-only servers, make the package importable from the venv.
        if not spec.install and spec.source_dir is not None:
            self._add_source_path(python, spec.source_dir)

        result.ok = is_ready(spec)
        result.command = spec.launch_command()
        if not result.ok and not result.error:
            result.error = (
                "installed, but the launch command was not found. "
                f"Expected script '{spec.script}' or module '{spec.module}'."
            )
        return result

    @staticmethod
    def _add_source_path(python: Path, source_dir: Path) -> None:
        """Drop a .pth so the venv sees the package without installing it."""
        site_packages = next(
            (p for p in python.parent.parent.glob("lib/python*/site-packages")), None
        )
        if site_packages is None:
            return
        (site_packages / "_mcp_source_path.pth").write_text(f"{source_dir}\n")

    def install_all(self, keys: Optional[List[str]] = None) -> List[SetupResult]:
        from src.agents.mcp_registry import REGISTRY

        targets = keys or list(REGISTRY)
        return [self.install(key) for key in targets]

    # -- reporting -----------------------------------------------------------

    def report(self) -> List[Dict[str, object]]:
        return status()


def render_status(report: List[Dict[str, object]]) -> str:
    """Format the registry status for the CLI."""
    lines = ["Optional MCP servers:", ""]
    for entry in report:
        mark = "ready   " if entry["ready"] else "not set up"
        lines.append(f"  [{mark}] {entry['key']:<9} {entry['description']}")
        lines.append(f"              license: {entry['license']}")
        if entry["ready"] and entry["command"]:
            lines.append(f"              command: {' '.join(entry['command'])}")
        else:
            lines.append(f"              env:     {entry['env_dir']}")
        if entry.get("notes"):
            lines.append(f"              note:    {entry['notes']}")
        lines.append("")
    lines.append("Set up with: ai-electronics-design mcp-setup")
    lines.append(
        "These servers are optional: design generation does not require them."
    )
    return "\n".join(lines)


__all__ = ["MCPServerManager", "SetupResult", "render_status"]
