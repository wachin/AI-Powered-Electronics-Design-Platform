"""
Registry of optional MCP servers this project can drive.

Why a registry (and why per-server virtual environments)
--------------------------------------------------------
MCP servers are launched as **subprocesses** and speak JSON-RPC over stdio, so
they do not share a Python environment with this application. That is
important: these servers have mutually incompatible dependencies. For example
`kicad-mcp-server` needs ``mcp[cli]>=1.27,<2`` while `pcbparts-mcp` pins
``mcp==1.25.0``.

Installing both into one environment is what causes the conflict reported in the
project notes. Giving each server its **own virtual environment** removes the
conflict entirely — no forks, no patched pins, no version negotiation. The
application only ever needs the path to the server's interpreter.

None of these servers are required to generate a design. They add validation and
analysis capabilities on top of the deterministic pipeline.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Sequence

# Repository root: this file is src/agents/mcp_registry.py
REPO_ROOT = Path(__file__).resolve().parents[2]


def _candidate_system_pythons() -> List[Path]:
    """
    Interpreters that might expose KiCad's `pcbnew` bindings.

    `sys.executable` is deliberately excluded: if this application is running
    inside its own virtual environment, that interpreter does not have `pcbnew`
    even though the distribution's Python does.
    """
    candidates = [Path("/usr/bin/python3"), Path("/usr/local/bin/python3")]
    candidates += [
        Path(f"/usr/bin/python3.{minor}") for minor in (13, 12, 11, 10)
    ]
    seen, unique = set(), []
    for path in candidates:
        if path.exists() and path not in seen:
            seen.add(path)
            unique.append(path)
    return unique


@lru_cache(maxsize=1)
def find_pcbnew_python() -> Optional[Path]:
    """Return a system interpreter that can `import pcbnew`, if one exists."""
    import subprocess

    for path in _candidate_system_pythons():
        try:
            probe = subprocess.run(
                [str(path), "-c", "import pcbnew"],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        if probe.returncode == 0:
            return path
    return None
EXTERNAL_DIR = REPO_ROOT / "external"
# Per-server environments live outside version control.
MCP_ENV_ROOT = REPO_ROOT / ".mcp_envs"


@dataclass(frozen=True)
class MCPServerSpec:
    """How to create and launch one optional MCP server."""

    key: str
    description: str
    license: str
    # What to install into the server's own virtual environment. Either a PyPI
    # requirement ("kicad-tools>=0.22") or an editable path in external/.
    install: Sequence[str]
    # The console script to launch, when the package defines one.
    script: Optional[str] = None
    # Fallback: run this module with the server's interpreter.
    module: Optional[str] = None
    # Extra environment needed to import the server when it is not installed as
    # a package (used only if `install` is empty).
    source_dir: Optional[Path] = None
    # Some servers call into KiCad's native Python bindings (`pcbnew`), which are
    # only available to the distribution's Python. For those we keep the
    # isolated packages but launch with the system interpreter.
    needs_system_python: bool = False
    notes: str = ""
    provides: List[str] = field(default_factory=list)

    @property
    def env_dir(self) -> Path:
        return MCP_ENV_ROOT / self.key

    @property
    def python(self) -> Path:
        """Interpreter inside this server's isolated environment."""
        if sys.platform == "win32":  # pragma: no cover - not the target platform
            return self.env_dir / "Scripts" / "python.exe"
        return self.env_dir / "bin" / "python"

    @property
    def site_packages(self) -> Optional[Path]:
        """The isolated environment's site-packages directory, if present."""
        for candidate in self.env_dir.glob("lib/python*/site-packages"):
            return candidate
        return None

    def launch_env(self) -> Dict[str, str]:
        """
        Extra environment for launching this server.

        When `needs_system_python` is set, the server's packages live in the
        isolated environment but the interpreter is the system one (so `pcbnew`
        is importable). We expose the packages through PYTHONPATH.
        """
        if not self.needs_system_python:
            return {}
        site = self.site_packages
        return {"PYTHONPATH": str(site)} if site else {}

    def launch_command(self) -> Optional[List[str]]:
        """Command list to start the server, or None if not set up yet."""
        isolated = self.python
        if not isolated.exists():
            return None

        if self.needs_system_python:
            # Interpreter that can see KiCad's native bindings; packages come
            # from the isolated environment via PYTHONPATH.
            if not self.module:
                return None
            system_python = find_pcbnew_python()
            if system_python is None:
                return None
            return [str(system_python), "-m", self.module]

        if self.script:
            executable = isolated.parent / self.script
            if executable.exists():
                return [str(executable)]
        if self.module:
            return [str(isolated), "-m", self.module]
        return None


REGISTRY: Dict[str, MCPServerSpec] = {
    "kicad": MCPServerSpec(
        key="kicad",
        description="KiCad analysis and validation tools (nets, pins, ERC/DRC, Gerbers)",
        license="MIT",
        install=["kicad-mcp-server"],
        script="kicad-mcp-server",
        module="kicad_mcp_server",
        needs_system_python=True,
        notes=(
            "Launched with the system interpreter so KiCad's native `pcbnew` "
            "bindings are importable (needed by get_board_info, auto_route and "
            "the 3D/STEP exports); the server's own packages stay isolated. "
            "Also available as an editable install from external/kicad-mcp-server."
        ),
        provides=[
            "validate_pin_configuration",
            "extract_power_domains",
            "generate_netlist",
            "run_erc",
            "run_drc",
            "analyze_pcb_signal_integrity",
            "export_gerber",
        ],
    ),
    "pcbparts": MCPServerSpec(
        key="pcbparts",
        description=(
            "Cross-distributor part search (JLCPCB/Mouser/DigiKey), PCB design "
            "rules, reference boards, alternatives"
        ),
        license="MIT",
        # No PyPI release and no console script, so install the local source.
        install=[],
        module="pcbparts_mcp.server",
        source_dir=EXTERNAL_DIR / "pcbparts-mcp" / "src",
        notes=(
            "Not published on PyPI and defines no console script. Its "
            "`mcp==1.25.0` pin is conservative — the code imports fine with "
            "newer versions — and isolation makes it moot either way."
        ),
        provides=[
            "cross-distributor part search",
            "parametric filtering",
            "component alternatives",
            "PCB design rules",
            "reference board schematics",
        ],
    ),
}


def get_spec(key: str) -> MCPServerSpec:
    try:
        return REGISTRY[key]
    except KeyError:
        raise KeyError(
            f"Unknown MCP server '{key}'. Known: {', '.join(sorted(REGISTRY))}"
        ) from None


def launch_recipe(
    key: str, extra_env: Optional[Dict[str, str]] = None
) -> Optional[tuple[List[str], Dict[str, str]]]:
    """
    Resolve everything needed to start a server: (command, environment).

    Returns None when the server's environment has not been created yet.
    ``extra_env`` is merged on top, for server-specific settings such as
    KICAD_MCP_PROJECTS_BASE.
    """
    spec = get_spec(key)
    command = spec.launch_command()
    if command is None:
        return None
    env = dict(spec.launch_env())
    if extra_env:
        env.update(extra_env)
    return command, env


def is_ready(spec: MCPServerSpec) -> bool:
    """True when the server's isolated environment looks runnable."""
    if not spec.python.exists():
        return False
    if spec.script and not (spec.python.parent / spec.script).exists():
        return False
    return spec.launch_command() is not None


def status() -> List[Dict[str, object]]:
    """Human-readable readiness for every registered server."""
    report = []
    for spec in REGISTRY.values():
        report.append(
            {
                "key": spec.key,
                "description": spec.description,
                "license": spec.license,
                "ready": is_ready(spec),
                "env_dir": str(spec.env_dir),
                "command": spec.launch_command(),
                "launch_env": spec.launch_env(),
                "notes": spec.notes,
            }
        )
    return report


__all__ = [
    "EXTERNAL_DIR",
    "find_pcbnew_python",
    "MCP_ENV_ROOT",
    "MCPServerSpec",
    "REGISTRY",
    "REPO_ROOT",
    "get_spec",
    "is_ready",
    "launch_recipe",
    "status",
]
