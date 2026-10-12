"""
Reader for installed KiCad footprint libraries.

Why this exists
---------------
A PCB file with `(footprint "Lib:Name")` but no `(pad ...)` elements is not a
board: there is nothing to route, nothing to fabricate, and KiCad cannot even
load it. The pad geometry lives in the KiCad footprint libraries, so this module
reads those files and re-emits them as placed board footprints.

Embedding the real pad definitions (rather than inventing geometry) also
guarantees the pad *numbers* match the pin numbers used by the schematic and
Circuit IR, which is what makes net assignment meaningful.

Footprint data is read from the locally installed KiCad libraries at runtime; it
is not vendored into this project.

Licensing: the KiCad footprint libraries are CC-BY-SA-4.0 with an explicit
exception permitting generated designs (including manufactured boards) to be
used without a share-alike obligation. The libraries themselves remain
CC-BY-SA-4.0. See CREDITS.md for the full text of the exception and the
attribution to the KiCad Community.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

DEFAULT_FOOTPRINT_DIRS: Tuple[Path, ...] = (
    Path("/usr/share/kicad/footprints"),
    Path("/usr/local/share/kicad/footprints"),
    Path.home() / ".local/share/kicad/footprints",
    Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints"),
)

_TOKEN_RE = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+')


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall(text)


def _parse(tokens: Sequence[str]) -> List:
    stack: List[list] = [[]]
    for token in tokens:
        if token == "(":
            node: list = []
            stack[-1].append(node)
            stack.append(node)
        elif token == ")":
            if len(stack) > 1:
                stack.pop()
        else:
            if len(token) >= 2 and token.startswith('"') and token.endswith('"'):
                token = token[1:-1]
            stack[-1].append(token)
    return stack[0]


@dataclass
class FootprintPad:
    number: str
    pad_type: str = "smd"
    shape: str = "rect"
    x: float = 0.0
    y: float = 0.0
    rotation: float = 0.0


@dataclass
class FootprintDefinition:
    lib_id: str          # e.g. "Resistor_SMD:R_0805_2012Metric"
    library: str
    name: str
    pads: List[FootprintPad] = field(default_factory=list)
    raw_text: str = ""   # full .kicad_mod source

    def pad(self, number: str) -> Optional[FootprintPad]:
        wanted = str(number).strip()
        for candidate in self.pads:
            if candidate.number.strip() == wanted:
                return candidate
        return None


class FootprintLibrary:
    """Loads and caches footprints from the installed KiCad libraries."""

    def __init__(self, search_dirs: Optional[Sequence[Path]] = None):
        self.search_dirs = tuple(search_dirs or DEFAULT_FOOTPRINT_DIRS)
        self._cache: Dict[str, Optional[FootprintDefinition]] = {}

    def _find_file(self, library: str, name: str) -> Optional[Path]:
        for directory in self.search_dirs:
            candidate = directory / f"{library}.pretty" / f"{name}.kicad_mod"
            if candidate.exists():
                return candidate
        return None

    @staticmethod
    def _extract_pads(roots: list) -> List[FootprintPad]:
        pads: List[FootprintPad] = []

        def walk(node):
            if not isinstance(node, list) or not node:
                return
            if node[0] == "pad" and len(node) > 1 and isinstance(node[1], str):
                pad = FootprintPad(number=node[1])
                if len(node) > 2 and isinstance(node[2], str):
                    pad.pad_type = node[2]
                if len(node) > 3 and isinstance(node[3], str):
                    pad.shape = node[3]
                for child in node:
                    if isinstance(child, list) and child and child[0] == "at":
                        pad.x = float(child[1]) if len(child) > 1 else 0.0
                        pad.y = float(child[2]) if len(child) > 2 else 0.0
                        pad.rotation = float(child[3]) if len(child) > 3 else 0.0
                pads.append(pad)
                return
            for child in node:
                walk(child)

        walk(roots)
        return pads

    def load(self, lib_id: str) -> Optional[FootprintDefinition]:
        """Load a footprint such as "Resistor_SMD:R_0805_2012Metric"."""
        if not lib_id or ":" not in lib_id:
            return None
        if lib_id in self._cache:
            return self._cache[lib_id]

        library, name = lib_id.split(":", 1)
        path = self._find_file(library, name)
        if path is None:
            self._cache[lib_id] = None
            return None

        try:
            text = path.read_text(errors="replace")
        except OSError:
            self._cache[lib_id] = None
            return None

        roots = _parse(_tokenize(text))
        definition = FootprintDefinition(
            lib_id=lib_id,
            library=library,
            name=name,
            pads=self._extract_pads(roots),
            raw_text=text,
        )
        self._cache[lib_id] = definition
        return definition


_LIBRARY: Optional[FootprintLibrary] = None


def get_footprint_library() -> FootprintLibrary:
    global _LIBRARY
    if _LIBRARY is None:
        _LIBRARY = FootprintLibrary()
    return _LIBRARY


def load_footprint(lib_id: str) -> Optional[FootprintDefinition]:
    return get_footprint_library().load(lib_id)


@dataclass
class PlacedPad:
    """A pad's absolute position on the board."""

    number: str
    x: float
    y: float


def place_pads(
    definition: FootprintDefinition,
    at_x: float,
    at_y: float,
    rotation_deg: float = 0.0,
) -> List[PlacedPad]:
    """
    Compute absolute pad coordinates for a placed footprint.

    Uses the same transform KiCad applies: rotate the pad offset, then add the
    footprint origin. Board Y increases downward, matching pad coordinates, so
    no axis flip is needed here (unlike schematics).
    """
    import math

    theta = math.radians(rotation_deg)
    cos_t, sin_t = math.cos(theta), math.sin(theta)
    placed: List[PlacedPad] = []
    for pad in definition.pads:
        x = pad.x * cos_t - pad.y * sin_t
        y = pad.x * sin_t + pad.y * cos_t
        placed.append(PlacedPad(number=pad.number, x=at_x + x, y=at_y + y))
    return placed


__all__ = [
    "DEFAULT_FOOTPRINT_DIRS",
    "FootprintDefinition",
    "FootprintLibrary",
    "FootprintPad",
    "PlacedPad",
    "get_footprint_library",
    "load_footprint",
    "place_pads",
]

# ---------------------------------------------------------------------------
# Shared S-expression helpers
#
# Used by the PCB generator to rewrite a library footprint into a placed board
# instance. Kept here so symbol and footprint handling share one implementation.
# ---------------------------------------------------------------------------

def _find_node(nodes: list, name: str):
    """Depth-first search for the first `(name ...)` node."""
    for node in nodes:
        if not isinstance(node, list) or not node:
            continue
        if node[0] == name:
            return node
        found = _find_node(node, name)
        if found is not None:
            return found
    return None


def _set_property(footprint_node: list, key: str, value: str) -> None:
    """Set a footprint property, adding it when absent."""
    for child in footprint_node:
        if (
            isinstance(child, list)
            and len(child) > 2
            and child[0] == "property"
            and child[1] == key
        ):
            child[2] = value
            return
    footprint_node.append(["property", key, value])


_NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
_BARE_ATOM_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_\-\.]*$")
_ALWAYS_QUOTED = frozenset(
    {
        "number", "name", "lib_id", "part", "lib", "value", "reference",
        "Footprint", "Datasheet", "Description", "Reference", "Value",
        "layer", "net_name", "uuid", "property", "descr", "tags",
    }
)


def _render_sexpr(node, parent: str = "", indent: int = 0) -> str:
    """
    Render a parsed node back to S-expression text.

    KiCad is strict about quoting: pad numbers, net names and layer names must
    be strings. Structural keywords and plain numbers stay bare.
    """
    pad = "  " * indent
    if isinstance(node, str):
        if node == "":
            return '""'
        if parent in _ALWAYS_QUOTED:
            return '"' + node.replace("\\", "\\\\").replace('"', '\\"') + '"'
        if _NUMBER_RE.match(node):
            return node
        if _BARE_ATOM_RE.match(node):
            return node
        return '"' + node.replace("\\", "\\\\").replace('"', '\\"') + '"'

    head = node[0] if node and isinstance(node[0], str) else ""
    parts = [_render_sexpr(head)]
    for child in node[1:]:
        parts.append(_render_sexpr(child, head, indent + 1))
    return "(" + " ".join(parts) + ")"

