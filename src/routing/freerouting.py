"""
FreeRouting Integration for AI-Powered Electronics Design Platform.

Routes PCB traces with the FreeRouting autorouter.

Two details make this work on a modern KiCad install:

* **DSN/SES go through `pcbnew`, not `kicad-cli`.** The `kicad-cli pcb export
  dsn` and `kicad-cli pcb import ses` subcommands do not exist in KiCad 7+. The
  `pcbnew` Python bindings provide `ExportSpecctraDSN` and `ImportSpecctraSES`,
  which do.
* **FreeRouting needs Java 25.** The distributed jars are compiled to class-file
  version 69. An older runtime refuses to start them, so a suitable JDK is
  located explicitly rather than assuming the default `java` is new enough.

FreeRouting is not bundled with any Python package; the jar is looked up in
`libs/freerouting/` and in a few standard locations. See CREDITS.md.
"""

import subprocess
import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class RoutingResult:
    success: bool
    routed_dsn_path: Optional[Path] = None
    routed_ses_path: Optional[Path] = None
    routed_pcb_path: Optional[Path] = None
    drc_errors: int = 0
    # The narrowest track the router actually laid on each net, in millimetres.
    # Read back from the routed board so the design can check it got the widths
    # its net classes asked for, rather than assuming it did.
    routed_widths: Dict[str, float] = field(default_factory=dict)
    # Nets laid narrower than their net class requires.
    width_warnings: List[str] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""
    error: Optional[str] = None


class FreeRoutingRunner:
    """
    Runs FreeRouting autorouter on KiCad DSN files.
    """

    def __init__(
        self,
        freerouting_jar: Optional[str] = None,
        java: Optional[str] = None,
    ):
        self.freerouting_jar = freerouting_jar or self._find_freerouting_jar()
        self.java = java or self._find_java()

    @staticmethod
    def _find_freerouting_jar() -> Optional[str]:
        """Locate the FreeRouting jar, preferring the project's own copy."""
        from src.agents.mcp_registry import find_freerouting_jar

        found = find_freerouting_jar()
        return str(found) if found else None

    @staticmethod
    def _find_java() -> str:
        """
        Find a Java runtime new enough for the FreeRouting jars (Java 25+).

        Falls back to plain `java` so a system with a suitably new default still
        works even if discovery fails.
        """
        from src.agents.mcp_registry import find_java25

        found = find_java25()
        return str(found) if found else "java"

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
        import_result = self._import_ses(routed_ses_path, pcb_path, routed_pcb_path)
        if not import_result.success:
            return import_result

        tracks = self._count_tracks(routed_pcb_path)
        return RoutingResult(
            success=True,
            routed_dsn_path=dsn_path,
            routed_ses_path=routed_ses_path,
            routed_pcb_path=routed_pcb_path,
            drc_errors=0,
            # Carried through from the import step, which reads them back off the
            # routed board. Dropping them here is how the widths the router
            # actually used would go unreported.
            routed_widths=dict(import_result.routed_widths),
            stdout=f"routed board: {routed_pcb_path} ({tracks} tracks)",
        )

    @staticmethod
    def _count_tracks(pcb_path: Path) -> int:
        """Number of track segments in the routed board, or 0 if unreadable."""
        import re

        try:
            text = pcb_path.read_text(errors="replace")
        except OSError:
            return 0
        return len(re.findall(r"\n\s*\(segment\b", text))

    def _pcbnew(self, code: str) -> subprocess.CompletedProcess:
        """
        Run a snippet against KiCad's `pcbnew` bindings.

        `pcbnew` ships with KiCad and is not importable from this project's
        virtual environment, so the snippet runs in a system interpreter that
        has it. The interpreter is discovered once and reused.
        """
        from src.agents.mcp_registry import find_pcbnew_python

        python = find_pcbnew_python()
        if python is None:
            return subprocess.CompletedProcess(
                args=["pcbnew"], returncode=1, stdout="", stderr=(
                    "KiCad's pcbnew Python bindings were not found. Install KiCad, "
                    "or run `python3 -c 'import pcbnew'` to check the interpreter."
                ),
            )
        return subprocess.run(
            [str(python), "-c", code], capture_output=True, text=True, timeout=300
        )

    def _export_dsn(self, pcb_path: Path, dsn_path: Path) -> RoutingResult:
        """
        Export a KiCad PCB to Specctra DSN via `pcbnew`.

        `kicad-cli` has no DSN export from KiCad 7 onward, so this uses the
        `pcbnew.ExportSpecctraDSN` API instead.
        """
        code = (
            "import pcbnew, sys\n"
            f"board = pcbnew.LoadBoard({str(pcb_path)!r})\n"
            f"ok = pcbnew.ExportSpecctraDSN(board, {str(dsn_path)!r})\n"
            "print('OK' if ok else 'FAILED')\n"
        )
        try:
            result = self._pcbnew(code)
        except Exception as exc:  # noqa: BLE001
            return RoutingResult(success=False, error=f"DSN export failed: {exc}")

        if result.returncode != 0 or "OK" not in (result.stdout or ""):
            return RoutingResult(
                success=False,
                stdout=result.stdout,
                stderr=result.stderr,
                error=(
                    "DSN export failed via pcbnew: "
                    f"{(result.stderr or result.stdout or '').strip()[:400]}"
                ),
            )
        if not dsn_path.exists():
            return RoutingResult(success=False, error=f"DSN not written: {dsn_path}")
        return RoutingResult(success=True, routed_dsn_path=dsn_path)

    def _run_freerouting(self, dsn_path: Path, ses_output: Path) -> RoutingResult:
        """Run FreeRouting with Java 25 and the modern CLI flags."""
        if not self.freerouting_jar:
            return RoutingResult(
                success=False,
                error=(
                    "FreeRouting jar not found. Place it at "
                    "libs/freerouting/freerouting.jar or set "
                    "KICAD_MCP_FREEROUTING_JAR."
                ),
            )
        try:
            result = subprocess.run(
                [
                    self.java, "-jar", self.freerouting_jar,
                    "-de", str(dsn_path),
                    "-do", str(ses_output),
                ],
                capture_output=True,
                text=True,
                timeout=900,
            )
            if result.returncode != 0:
                return RoutingResult(
                    success=False,
                    stdout=result.stdout,
                    stderr=result.stderr,
                    error=f"FreeRouting failed: {(result.stderr or '')[-400:]}",
                )
            if not ses_output.exists():
                return RoutingResult(
                    success=False,
                    stdout=result.stdout,
                    error="FreeRouting reported success but produced no SES file",
                )
            return RoutingResult(success=True, routed_ses_path=ses_output)
        except Exception as exc:  # noqa: BLE001
            return RoutingResult(success=False, error=str(exc))

    def _import_ses(
        self, ses_path: Path, source_pcb: Path, pcb_output: Path
    ) -> RoutingResult:
        """
        Import a routed SES back into the PCB via `pcbnew`.

        Loads `source_pcb` (the original, unrouted board) and writes the routed
        result to `pcb_output`, so the original is preserved.
        """
        if not ses_path.exists():
            return RoutingResult(
                success=False, error=f"routed SES file is missing: {ses_path}"
            )
        code = (
            "import json, pcbnew\n"
            f"board = pcbnew.LoadBoard({str(source_pcb)!r})\n"
            f"ok = pcbnew.ImportSpecctraSES(board, {str(ses_path)!r})\n"
            "widths = {}\n"
            "if ok:\n"
            f"    board.Save({str(pcb_output)!r})\n"
            "    for item in board.GetTracks():\n"
            "        if item.Type() == pcbnew.PCB_VIA_T:\n"
            "            continue\n"
            "        net = item.GetNetname() or ''\n"
            "        width = item.GetWidth() / 1e6\n"
            "        if net and (net not in widths or width < widths[net]):\n"
            "            widths[net] = round(width, 4)\n"
            "print('OK' if ok else 'FAILED')\n"
            "print('WIDTHS ' + json.dumps(widths))\n"
        )
        try:
            result = self._pcbnew(code)
        except Exception as exc:  # noqa: BLE001
            return RoutingResult(success=False, error=f"SES import failed: {exc}")

        if result.returncode != 0 or "OK" not in (result.stdout or ""):
            return RoutingResult(
                success=False,
                stdout=result.stdout,
                stderr=result.stderr,
                error=(
                    "SES import failed via pcbnew: "
                    f"{(result.stderr or result.stdout or '').strip()[:400]}"
                ),
            )

        widths: Dict[str, float] = {}
        for line in (result.stdout or "").splitlines():
            if not line.startswith("WIDTHS "):
                continue
            try:
                parsed = json.loads(line[len("WIDTHS "):])
            except (TypeError, ValueError):
                continue
            if isinstance(parsed, dict):
                widths = {
                    str(net): float(value)
                    for net, value in parsed.items()
                    if isinstance(value, (int, float))
                }

        return RoutingResult(success=True, routed_widths=widths)


def route_kicad_pcb(pcb_path: Path, freerouting_jar: Optional[str] = None) -> RoutingResult:
    """
    High-level function to route a KiCad PCB using FreeRouting.
    """
    runner = FreeRoutingRunner(freerouting_jar)
    return runner.route_pcb(pcb_path)