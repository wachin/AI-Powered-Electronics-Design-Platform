"""
Manufacturing output: the files a board house and an assembly service need.

Why this exists
---------------
The pipeline produced a KiCad project, a BOM and a purchase list, and the
ROADMAP recorded that Gerber export had been *verified* — with `kicad-cli`, by
hand. No code produced them. A user who finished a design had a ``.kicad_pcb``,
which no board house accepts, and no position file, without which JLCPCB's
assembly service cannot place anything.

This module closes that: from the finished board it produces

* **Gerbers**, one file per layer, plus the drill files;
* a **single archive** of those, which is what an order form wants;
* a **position file** (``CPL``), which is what assembly needs alongside the BOM.

All three come from ``kicad-cli``. This project writes its own KiCad files but
does not reimplement KiCad's plotting, in the same way it does not reimplement
routing.

What is checked rather than assumed
-----------------------------------
Three things can go wrong quietly here, so each is checked:

1. ``kicad-cli`` can exit zero having written nothing. Every expected file must
   exist and be non-empty, and every Gerber must actually start with a Gerber
   header.
2. A board with no copper layers still plots something. The layer set is checked
   for the ones an order cannot be placed without.
3. **A part in the BOM that is missing from the position file would be left
   unsoldered**, and the board would come back with a hole where a component
   should be. The designator sets are compared and any difference is reported.
"""

from __future__ import annotations

import shutil
import subprocess
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

# The layers an order cannot be placed without. F_Cu and B_Cu are the copper,
# Edge_Cuts is the board outline, and the masks are what stops solder from
# bridging the pads together.
REQUIRED_GERBER_SUFFIXES = (".gtl", ".gbl", ".gts", ".gbs", ".gm1")

# A Gerber file starts with one of these. Used to tell a real plot from an empty
# file or an error message that was written to the output path.
_GERBER_MAGIC = ("%FS", "%MO", "G04", "%TF")

# An Excellon drill file starts with this.
_DRILL_MAGIC = "M48"


def kicad_cli_path() -> Optional[str]:
    """
    The KiCad CLI, or None when it is not installed.

    ``DSH_KICAD_CLI`` overrides discovery, which matters on systems with several
    KiCad versions installed. ``--diagnose`` asks the same function, so the two
    cannot disagree about whether KiCad is available.
    """
    import os

    override = os.environ.get("DSH_KICAD_CLI")
    if override:
        return override if Path(override).exists() else None
    return shutil.which("kicad-cli")


@dataclass
class FabricationOutput:
    """The manufacturing files, and what was found wrong with them."""

    gerber_files: List[Path] = field(default_factory=list)
    drill_files: List[Path] = field(default_factory=list)
    position_file: Optional[Path] = None
    archive: Optional[Path] = None
    warnings: List[str] = field(default_factory=list)
    errors: List[str] = field(default_factory=list)

    @property
    def usable(self) -> bool:
        """Whether an order could be placed with these files."""
        return bool(self.gerber_files) and bool(self.drill_files) and not self.errors

    @property
    def file_count(self) -> int:
        return len(self.gerber_files) + len(self.drill_files) + (
            1 if self.position_file else 0
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "usable": self.usable,
            "gerber_files": [p.name for p in self.gerber_files],
            "drill_files": [p.name for p in self.drill_files],
            "position_file": self.position_file.name if self.position_file else None,
            "archive": str(self.archive) if self.archive else None,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }

    def summary(self) -> str:
        return (
            f"{len(self.gerber_files)} Gerber(s), {len(self.drill_files)} drill "
            f"file(s)"
            + (", position file" if self.position_file else "")
            + (", archived" if self.archive else "")
        )


def _run(command: Sequence[str], timeout: float = 300.0) -> Tuple[int, str]:
    """Run a command, returning its exit status and combined output."""
    try:
        result = subprocess.run(
            list(command), capture_output=True, text=True, timeout=timeout
        )
    except FileNotFoundError:
        return (127, f"{command[0]} not found")
    except subprocess.TimeoutExpired:
        return (124, f"{command[0]} timed out after {timeout:g}s")
    return (result.returncode, (result.stdout or "") + (result.stderr or ""))


def _looks_like_gerber(path: Path) -> bool:
    try:
        head = path.read_text(errors="replace")[:64]
    except OSError:
        return False
    return any(marker in head for marker in _GERBER_MAGIC)


def _looks_like_drill(path: Path) -> bool:
    try:
        head = path.read_text(errors="replace")[:64]
    except OSError:
        return False
    return _DRILL_MAGIC in head


def read_position_designators(position_file: Path) -> List[str]:
    """
    The reference designators from a KiCad position file.

    Handles the CSV format, which is the one an assembly service wants. The
    ``Ref`` column is quoted by KiCad, hence the stripping.
    """
    import csv

    if not position_file.exists():
        return []
    with position_file.open(newline="", encoding="utf-8", errors="replace") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None:
            return []
        key = next(
            (name for name in reader.fieldnames if name.strip().lower() == "ref"),
            None,
        )
        if key is None:
            return []
        return [
            (row.get(key) or "").strip().strip('"')
            for row in reader
            if (row.get(key) or "").strip()
        ]


def export_fabrication(
    pcb_path: Path,
    output_dir: Path,
    project_name: str = "design",
    expected_designators: Optional[Iterable[str]] = None,
    archive: bool = True,
    position_sides: Sequence[str] = ("front",),
) -> FabricationOutput:
    """
    Produce the Gerbers, drill files and position file for a finished board.

    Args:
        pcb_path: The board to plot. Use the routed board when there is one, so
            the Gerbers match what was routed.
        output_dir: Where to write everything.
        project_name: Used for the file names and the archive.
        expected_designators: The designators the BOM lists. Any that the
            position file lacks are reported, because they would be left
            unsoldered.
        archive: Also write a single zip of the Gerbers and drill files, which is
            what an order form accepts.
        position_sides: Which sides to include in the position file. Assembly
            services want one file per side; front is the common case.

    Returns:
        A :class:`FabricationOutput`. ``errors`` is non-empty when the output is
        not good enough to order from, and the caller should say so rather than
        presenting the files as ready.
    """
    output = FabricationOutput()
    pcb_path = Path(pcb_path)
    output_dir = Path(output_dir)

    if not pcb_path.exists():
        output.errors.append(f"board not found: {pcb_path}")
        return output

    cli = kicad_cli_path()
    if cli is None:
        output.errors.append(
            "kicad-cli was not found, so no Gerbers could be produced. Install "
            "KiCad, or point DSH_KICAD_CLI at it."
        )
        return output

    gerber_dir = output_dir / "gerbers"
    gerber_dir.mkdir(parents=True, exist_ok=True)

    # -- Gerbers -----------------------------------------------------------
    status, text = _run([cli, "pcb", "export", "gerbers", "-o", f"{gerber_dir}/", str(pcb_path)])
    if status != 0:
        output.errors.append(f"Gerber export failed: {text.strip()[:300]}")
        return output

    for path in sorted(gerber_dir.iterdir()):
        if not path.is_file() or path.suffix == ".gbrjob":
            continue
        if path.suffix in (".drl",):
            continue
        if not _looks_like_gerber(path):
            output.warnings.append(
                f"{path.name} was written but does not start with a Gerber header"
            )
        output.gerber_files.append(path)

    if not output.gerber_files:
        output.errors.append(
            "kicad-cli reported success but wrote no Gerber files"
        )
        return output

    missing = [
        suffix
        for suffix in REQUIRED_GERBER_SUFFIXES
        if not any(p.name.endswith(suffix) for p in output.gerber_files)
    ]
    if missing:
        output.errors.append(
            "these layers are missing from the Gerber set, so the board cannot "
            f"be made: {', '.join(missing)}"
        )

    # -- Drill files -------------------------------------------------------
    status, text = _run([
        cli, "pcb", "export", "drill",
        "-o", f"{gerber_dir}/",
        "--format", "excellon",
        "--excellon-separate-th",
        str(pcb_path),
    ])
    if status != 0:
        output.errors.append(f"drill export failed: {text.strip()[:300]}")
    else:
        for path in sorted(gerber_dir.glob("*.drl")):
            if not _looks_like_drill(path):
                output.warnings.append(
                    f"{path.name} does not start with an Excellon header"
                )
            output.drill_files.append(path)
        if not output.drill_files:
            output.errors.append(
                "kicad-cli reported success but wrote no drill file; a board "
                "with no drill file cannot be made"
            )

    # -- Position file -----------------------------------------------------
    for side in position_sides:
        position_file = output_dir / f"{project_name}-cpl-{side}.csv"
        status, text = _run([
            cli, "pcb", "export", "pos",
            "--format", "csv",
            "--units", "mm",
            "--side", side,
            "-o", str(position_file),
            str(pcb_path),
        ])
        if status != 0 or not position_file.exists():
            output.warnings.append(
                f"no position file for the {side} side: {text.strip()[:200]}"
            )
            continue
        if output.position_file is None:
            output.position_file = position_file

        if expected_designators is not None:
            listed = {d.strip().upper() for d in read_position_designators(position_file)}
            expected = {d.strip().upper() for d in expected_designators if d}
            absent = sorted(expected - listed)
            if absent:
                output.warnings.append(
                    f"the {side} position file does not place {', '.join(absent)}, "
                    f"which the BOM lists. Those parts would not be fitted by an "
                    f"assembly service; add them by hand or check the board."
                )
            if side == "front" and (listed - expected):
                extra = ", ".join(sorted(listed - expected))
                output.warnings.append(
                    f"the position file places {extra}, which the BOM does not "
                    f"list. Check the board against the design."
                )

    # -- One archive, which is what an order form accepts -------------------
    if archive and output.gerber_files:
        archive_path = output_dir / f"{project_name}-gerbers.zip"
        try:
            with zipfile.ZipFile(archive_path, "w", zipfile.ZIP_DEFLATED) as bundle:
                for path in output.gerber_files + output.drill_files:
                    bundle.write(path, arcname=path.name)
            output.archive = archive_path
        except OSError as exc:
            output.warnings.append(f"could not write the Gerber archive: {exc}")

    return output
