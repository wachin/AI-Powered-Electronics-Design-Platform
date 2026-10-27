"""
Shared pytest configuration.

Some acceptance tests need external EDA tools (kicad-cli, ngspice). They skip
when a tool is absent so the suite stays usable on a plain dev machine.

In CI those skips must not silently hide a missing dependency, so setting
``DSH_REQUIRE_KICAD=1`` turns a missing tool into a hard failure instead. That
way "verified against KiCad" means verified, not skipped.

KiCad **9** is required, not merely "a KiCad": the generator writes the 8/9 file
format (``generator_version``, board version 20240108) and reads the 9 symbol and
footprint libraries, so a KiCad 7 — what Ubuntu's package used to provide, and
what CI installed — rejects every board and resolves no symbol at all. Rather
than 125 confusing failures, an older KiCad now skips these tests with the
version in the message, and CI asserts the version it installed.
"""

import os
import shutil
import subprocess

import pytest

REQUIRE_KICAD = os.environ.get("DSH_REQUIRE_KICAD") == "1"

# The oldest KiCad this project works with, as a major version.
MINIMUM_KICAD_MAJOR = 9


def kicad_version() -> str:
    """The installed kicad-cli version, or "" when it is absent."""
    executable = shutil.which("kicad-cli")
    if executable is None:
        return ""
    try:
        result = subprocess.run(
            [executable, "version"], capture_output=True, text=True, timeout=20
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if line:
            return line
    return ""


def kicad_available() -> bool:
    return shutil.which("kicad-cli") is not None


def kicad_is_supported() -> bool:
    """Whether the installed KiCad is new enough to read what this project writes."""
    version = kicad_version()
    if not version:
        return False
    try:
        major = int(version.split(".")[0])
    except ValueError:
        return False
    return major >= MINIMUM_KICAD_MAJOR


def kicad_skip_reason() -> str:
    """Reason string for pytest.mark.skipif, or a hard failure in CI."""
    if kicad_available() and kicad_is_supported():
        return "kicad-cli is installed"
    if REQUIRE_KICAD:
        if not kicad_available():
            raise RuntimeError(
                "DSH_REQUIRE_KICAD=1 but kicad-cli was not found on PATH. "
                "Install KiCad before running the acceptance suite."
            )
        raise RuntimeError(
            f"DSH_REQUIRE_KICAD=1 but kicad-cli is {kicad_version()}; this "
            f"project requires KiCad {MINIMUM_KICAD_MAJOR} or newer. The "
            "generated board uses the 8/9 file format, which an older KiCad "
            "rejects, so the suite would fail rather than verify anything."
        )
    if not kicad_available():
        return "kicad-cli not installed (set DSH_REQUIRE_KICAD=1 to require it)"
    return (
        f"KiCad {MINIMUM_KICAD_MAJOR}+ is required and kicad-cli is "
        f"{kicad_version()} (set DSH_REQUIRE_KICAD=1 to make this an error)"
    )


requires_kicad = pytest.mark.skipif(
    not (kicad_available() and kicad_is_supported()) and not REQUIRE_KICAD,
    reason=kicad_skip_reason(),
)
