"""
Shared pytest configuration.

Some acceptance tests need external EDA tools (kicad-cli, ngspice). They skip
when a tool is absent so the suite stays usable on a plain dev machine.

In CI those skips must not silently hide a missing dependency, so setting
``DSH_REQUIRE_KICAD=1`` turns a missing tool into a hard failure instead. That
way "verified against KiCad" means verified, not skipped.
"""

import os
import shutil

import pytest

REQUIRE_KICAD = os.environ.get("DSH_REQUIRE_KICAD") == "1"


def kicad_available() -> bool:
    return shutil.which("kicad-cli") is not None


def kicad_skip_reason() -> str:
    """Reason string for pytest.mark.skipif, or a hard failure in CI."""
    if kicad_available():
        return "kicad-cli is installed"
    if REQUIRE_KICAD:
        raise RuntimeError(
            "DSH_REQUIRE_KICAD=1 but kicad-cli was not found on PATH. "
            "Install KiCad before running the acceptance suite."
        )
    return "kicad-cli not installed"


requires_kicad = pytest.mark.skipif(
    not kicad_available() and not REQUIRE_KICAD,
    reason="kicad-cli not installed (set DSH_REQUIRE_KICAD=1 to require it)",
)
