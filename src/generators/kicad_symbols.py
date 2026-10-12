"""
Reader for installed KiCad symbol libraries.

Why this exists
---------------
A schematic is only useful if KiCad can extract a netlist from it. Emitting
`(symbol (lib_id ...))` with no `lib_symbols` definition, no `(pin ...)`
instances, and no wires or labels produces a file that opens but has *no
electrical connectivity at all* — kicad-cli exports an empty netlist.

To connect anything we need each pin's real coordinates, which live in the
KiCad symbol libraries. This module parses those libraries and provides:

* the pin number, name and position for any symbol
* a re-emittable `lib_symbols` definition for the schematic

Pin-space vs sheet-space: KiCad symbol libraries use a Y-up axis, while
schematics use Y-down. The caller flips the Y sign; `pin_endpoints()` does that
for convenience.

Licensing: the KiCad symbol libraries are CC-BY-SA-4.0 with an exception that
permits generated designs to be used freely. They are read from the local KiCad
installation at runtime and are NOT vendored into this repository. See
CREDITS.md.

Verified against KiCad 9.0.2 (`/usr/share/kicad/symbols`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

# Standard locations, most specific first.
DEFAULT_SYMBOL_DIRS: Tuple[Path, ...] = (
    Path("/usr/share/kicad/symbols"),
    Path("/usr/local/share/kicad/symbols"),
    Path.home() / ".local/share/kicad/symbols",
    Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"),
)

_TOKEN_RE = re.compile(r'\(|\)|"(?:[^"\\]|\\.)*"|[^\s()]+')


def _tokenize(text: str) -> List[str]:
    return _TOKEN_RE.findall(text)


def _parse(tokens: Sequence[str]) -> List:
    """Parse S-expression tokens into nested lists (strings for atoms)."""
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


def _children(node: list, name: str) -> List[list]:
    return [
        child
        for child in node
        if isinstance(child, list) and child and child[0] == name
    ]


def _first_child(node: list, name: str) -> Optional[list]:
    matches = _children(node, name)
    return matches[0] if matches else None


@dataclass
class SymbolPin:
    number: str
    name: str
    x: float
    y: float
    length: float = 0.0
    orientation: float = 0.0
    electrical_type: str = "passive"

    def endpoint(self) -> Tuple[float, float]:
        """The coordinate where a wire attaches (pin origin + stub length)."""
        # In KiCad a pin's `at` is the connection point and it extends *toward*
        # the body by `length`; the connectable end is the `at` coordinate.
        return self.x, self.y


@dataclass
class SymbolDefinition:
    lib_id: str          # e.g. "Device:R"
    name: str            # e.g. "R"
    library: str         # e.g. "Device"
    pins: List[SymbolPin] = field(default_factory=list)
    definition_sexpr: str = ""   # ready to embed inside (lib_symbols ...)
    raw_node: Optional[list] = None
    extends: Optional[str] = None

    def pin(self, identifier: str) -> Optional[SymbolPin]:
        wanted = str(identifier).strip().lower()
        for pin in self.pins:
            if pin.number.lower() == wanted or pin.name.strip().lower() == wanted:
                return pin
        return None


class SymbolLibrary:
    """Loads and caches symbols from the installed KiCad libraries."""

    def __init__(self, search_dirs: Optional[Sequence[Path]] = None):
        self.search_dirs = tuple(search_dirs or DEFAULT_SYMBOL_DIRS)
        self._file_cache: Dict[str, Optional[str]] = {}

    # -- file loading --------------------------------------------------------

    def _library_text(self, library: str) -> Optional[str]:
        if library in self._file_cache:
            return self._file_cache[library]
        text: Optional[str] = None
        for directory in self.search_dirs:
            candidate = directory / f"{library}.kicad_sym"
            if candidate.exists():
                try:
                    text = candidate.read_text(errors="replace")
                except OSError:
                    text = None
                break
        self._file_cache[library] = text
        return text

    @staticmethod
    def _find_symbol_node(roots: list, name: str) -> Optional[list]:
        for node in roots:
            if not isinstance(node, list) or not node:
                continue
            if node[0] == "symbol" and len(node) > 1 and node[1] == name:
                return node
            found = SymbolLibrary._find_symbol_node(node, name)
            if found is not None:
                return found
        return None

    # -- parsing -------------------------------------------------------------

    @staticmethod
    def _extract_pins(node: list) -> List[SymbolPin]:
        pins: List[SymbolPin] = []
        for section in _children(node, "symbol"):  # sub-units like R_1_1
            for pin_node in _children(section, "pin"):
                at = _first_child(pin_node, "at")
                number = _first_child(pin_node, "number")
                name = _first_child(pin_node, "name")
                length = _first_child(pin_node, "length")
                pins.append(
                    SymbolPin(
                        number=str(number[1]) if number and len(number) > 1 else "",
                        name=str(name[1]) if name and len(name) > 1 else "~",
                        x=float(at[1]) if at and len(at) > 1 else 0.0,
                        y=float(at[2]) if at and len(at) > 2 else 0.0,
                        orientation=float(at[3]) if at and len(at) > 3 else 0.0,
                        length=float(length[1]) if length and len(length) > 1 else 0.0,
                        electrical_type=str(pin_node[1]) if len(pin_node) > 1 else "passive",
                    )
                )
        return pins

    def load(self, lib_id: str) -> Optional[SymbolDefinition]:
        """Load a symbol such as "Device:R" or "Regulator_Linear:AMS1117-3.3"."""
        if ":" not in lib_id:
            return None
        library, name = lib_id.split(":", 1)
        text = self._library_text(library)
        if not text:
            return None

        roots = _parse(_tokenize(text))
        node = self._find_symbol_node(roots, name)
        if node is None:
            return None

        extends_node = _first_child(node, "extends")
        extends = extends_node[1] if extends_node and len(extends_node) > 1 else None

        # An extending symbol inherits its pins and graphics from the base.
        source_node = node
        if extends:
            base = self._find_symbol_node(roots, extends)
            if base is not None:
                source_node = base

        pins = self._extract_pins(source_node)
        if not pins and source_node is not node:
            pins = self._extract_pins(node)

        definition = self._build_definition(
            lib_id=lib_id,
            name=name,
            node=node,
            source_node=source_node,
            pins=pins,
        )

        return SymbolDefinition(
            lib_id=lib_id,
            name=name,
            library=library,
            pins=pins,
            definition_sexpr=definition,
            raw_node=node,
            extends=extends,
        )

    # -- emission ------------------------------------------------------------

    _BARE_ATOM_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_\-\.]*$")
    _NUMBER_RE = re.compile(r"^-?\d+(?:\.\d+)?$")

    # Atoms that KiCad expects as quoted strings even when they contain no
    # spaces. Emitting `(number 1 ...)` instead of `(number "1" ...)` makes
    # kicad-cli refuse the whole file with "Failed to load schematic".
    _ALWAYS_QUOTED = frozenset(
        {
            "number", "name", "lib_id", "part", "lib", "value", "reference",
            "Footprint", "Datasheet", "Description", "Reference", "Value",
            "Sheetname", "Sheetfile", "page", "title", "company", "comment",
            "project", "path", "uuid", "description", "keywords",
        }
    )

    @classmethod
    def _render(cls, node, parent: str = "") -> str:
        """
        Render a parsed node back to an S-expression string.

        KiCad is strict about which atoms are quoted: pin numbers and names,
        lib_ids and property keys must be strings. We track the enclosing field
        name and quote its value, while leaving structural keywords and numbers
        bare.
        """
        if isinstance(node, str):
            if node == "":
                return '""'
            if parent in cls._ALWAYS_QUOTED:
                return '"' + node.replace("\\", "\\\\").replace('"', '\\"') + '"'
            if cls._NUMBER_RE.match(node):
                return node
            if cls._BARE_ATOM_RE.match(node):
                return node
            return '"' + node.replace("\\", "\\\\").replace('"', '\\"') + '"'

        head = node[0] if node and isinstance(node[0], str) else ""
        parts = [cls._render(head)]
        for child in node[1:]:
            # A two-element `(field value)` gives the value the field's name as
            # its parent context; nested lists recurse with their own head.
            parts.append(cls._render(child, head))
        return "(" + " ".join(parts) + ")"

    def _build_definition(
        self,
        lib_id: str,
        name: str,
        node: list,
        source_node: list,
        pins: List[SymbolPin],
    ) -> str:
        """
        Build a `(symbol "LIB:NAME" ...)` definition with the child's name but
        the base's graphics and pins, so pins resolve in the schematic.
        """
        header: List = ["symbol", lib_id]

        # Carry over the descriptive properties from the (possibly extending) node.
        for key in ("pin_numbers", "pin_names", "exclude_from_sim", "in_bom", "on_board"):
            found = _first_child(node, key)
            if found is not None:
                header.append(found)

        for prop in _children(node, "property"):
            header.append(prop)

        # Any properties the base defines and the child does not.
        child_names = {
            prop[1]
            for prop in _children(node, "property")
            if len(prop) > 1
        }
        for prop in _children(source_node, "property"):
            if len(prop) > 1 and prop[1] not in child_names:
                header.append(prop)

        # Graphics + pin sub-units, renamed to this symbol's name.
        for section in _children(source_node, "symbol"):
            if len(section) < 2 or not isinstance(section[1], str):
                continue
            renamed = list(section)
            renamed[1] = f"{name}{section[1][len(source_node[1]):]}" if isinstance(source_node[1], str) else section[1]
            header.append(renamed)

        return self._render(header)


_LIBRARY: Optional[SymbolLibrary] = None


def get_symbol_library() -> SymbolLibrary:
    """Process-wide symbol library instance."""
    global _LIBRARY
    if _LIBRARY is None:
        _LIBRARY = SymbolLibrary()
    return _LIBRARY


def load_symbol(lib_id: str) -> Optional[SymbolDefinition]:
    return get_symbol_library().load(lib_id)


__all__ = [
    "DEFAULT_SYMBOL_DIRS",
    "SymbolDefinition",
    "SymbolLibrary",
    "SymbolPin",
    "get_symbol_library",
    "load_symbol",
]
