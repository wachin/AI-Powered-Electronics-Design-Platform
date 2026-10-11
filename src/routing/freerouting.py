"""
FreeRouting Integration for AI-Powered Electronics Design Platform.

Automatically routes PCB traces using the FreeRouting open-source autorouter.
"""

import subprocess
import tempfile
import json
from pathlib import Path
from dataclasses import dataclass
from typing import Dict, Any, List, Optional


@dataclass
class RoutingResult:
    success: bool
    routed_dsn_path: Optional[Path] = None
    routed_ses_path: Optional[Path] = None
    drc_errors: int = 0
    stdout: str = ""
    stderr: str = ""
    error: Optional[str] = None


class FreeRoutingRunner:
    """
    Runs FreeRouting autorouter on KiCad DSN files.
    """

    def __init__(self, freerouting_jar: Optional[str] = None):
        self.freerouting_jar = freerouting_jar or self._find_freerouting_jar()

    def _find_freerouting_jar(self) -> str:
        # Check common locations
        candidates = [
            "freerouting.jar",
            "external/freerouting/freerouting.jar",
            "/usr/local/bin/freerouting.jar",
            str(Path.home() / "freerouting.jar"),
        ]
        for c in candidates:
            if Path(c).exists():
                return c
        return "freerouting.jar"  # Assume in PATH

    def route_pcb(self, kicad_pcb_path: Path, output_dir: Optional[Path] = None) -> RoutingResult:
        """
        Route a KiCad PCB using FreeRouting.
        
        Process:
        1. Export KiCad PCB to DSN format
        2. Run FreeRouting on DSN
        3. Import routed SES back to KiCad
        """
        pcb_path = Path(kicad_pcb_path)
        if not pcb_path.exists():
            return RoutingResult(
                success=False,
                error=f"PCB file not found: {pcb_path}"
            )

        out_dir = output_dir or pcb_path.parent
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        dsn_path = out_dir / f"{pcb_path.stem}.dsn"
        ses_path = out_dir / f"{pcb_path.stem}.ses"
        routed_ses_path = out_dir / f"{pcb_path.stem}_routed.ses"
        routed_pcb_path = out_dir / f"{pcb_path.stem}_routed.kicad_pcb"

        # Step 1: Export to DSN
        export_result = self._export_dsn(pcb_path, dsn_path)
        if not export_result.success:
            return export_result

        # Step 2: Run FreeRouting
        route_result = self._run_freerouting(dsn_path, routed_ses_path)
        if not route_result.success:
            return route_result

        # Step 3: Import routed SES back to KiCad
        import_result = self._import_ses(routed_ses_path, routed_pcb_path)
        if not import_result.success:
            return import_result

        return RoutingResult(
            success=True,
            routed_dsn_path=dsn_path,
            routed_ses_path=routed_ses_path,
            drc_errors=0,
        )

    def _export_dsn(self, pcb_path: Path, dsn_path: Path) -> RoutingResult:
        """Export KiCad PCB to DSN format using kicad-cli.
        
        Note: KiCad 7+ removed DSN export support. This will fail on KiCad 7+.
        For DSN export, you need KiCad 6 or use an external converter.
        """
        # Check KiCad version first
        try:
            version_result = subprocess.run(
                ["kicad-cli", "--version"],
                capture_output=True,
                text=True,
                timeout=10
            )
            if version_result.returncode == 0:
                version_str = version_result.stdout.strip()
                # Parse version (e.g., "9.0.1" or "8.0.4")
                major_version = int(version_str.split('.')[0]) if version_str.split('.')[0].isdigit() else 0
                if major_version >= 7:
                    return RoutingResult(
                        success=False,
                        error=(
                            f"KiCad {version_str} detected: DSN export was removed in KiCad 7+.\n"
                            "FreeRouting requires DSN format which is no longer supported.\n"
                            "Workarounds:\n"
                            "  1. Use KiCad's built-in interactive router (Route -> Auto Route)\n"
                            "  2. Use an external DSN converter (e.g., kicad-dsn-exporter)\n"
                            "  3. Install KiCad 6.x alongside for DSN export\n"
                            "  4. Use pcbnew Python scripting for custom routing"
                        )
                    )
        except Exception:
            pass  # Version check failed, try anyway
        
        try:
            result = subprocess.run(
                ["kicad-cli", "pcb", "export", "dsn", str(pcb_path), "-o", str(dsn_path)],
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode != 0:
                return RoutingResult(
                    success=False,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    error=(
                        f"DSN export failed: {result.stderr}\n"
                        "Note: KiCad 7+ removed DSN export support. "
                        "You need KiCad 6.x for DSN export, or use an external converter."
                    )
                )
            return RoutingResult(success=True)
        except Exception as e:
            return RoutingResult(success=False, error=str(e))

    def _run_freerouting(self, dsn_path: Path, ses_output: Path) -> RoutingResult:
        """Execute FreeRouting on DSN file."""
        try:
            result = subprocess.run(
                [
                    "java", "-jar", self.freerouting_jar,
                    "-d", str(dsn_path),
                    "-o", str(ses_output)
                ],
                capture_output=True,
                text=True,
                timeout=300
            )
            if result.returncode != 0:
                return RoutingResult(
                    success=False,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    error=f"FreeRouting failed: {result.stderr}"
                )
            return RoutingResult(success=True)
        except Exception as e:
            return RoutingResult(success=False, error=str(e))

    def _import_ses(self, ses_path: Path, pcb_output: Path) -> RoutingResult:
        """Import routed SES file back to KiCad PCB format."""
        try:
            result = subprocess.run(
                ["kicad-cli", "pcb", "import", "ses", str(ses_path), "-o", str(pcb_output)],
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode != 0:
                return RoutingResult(
                    success=False,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    error=f"SES import failed: {result.stderr}"
                )
            return RoutingResult(success=True)
        except Exception as e:
            return RoutingResult(success=False, error=str(e))


def route_kicad_pcb(pcb_path: Path, freerouting_jar: Optional[str] = None) -> RoutingResult:
    """
    High-level function to route a KiCad PCB using FreeRouting.
    """
    runner = FreeRoutingRunner(freerouting_jar)
    return runner.route_pcb(pcb_path)