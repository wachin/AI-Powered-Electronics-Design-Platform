"""
KiCad Project Generator for AI-Powered Electronics Design Platform.

Compiles CircuitIR into valid KiCad 8 file structures (.kicad_sch, .kicad_pcb, .kicad_pro).
"""

import json
import logging
import math
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

from src.core.circuit_ir import CircuitIR, Component, Net, ComponentType
from src.generators.kicad_symbols import get_symbol_library
from src.generators.kicad_footprints import (
    get_footprint_library,
    place_pads,
    _parse,
    _render_sexpr,
    _set_property,
    _tokenize,
    _find_node,
)

logger = logging.getLogger(__name__)


class KiCadGenerator:
    """
    Generator that compiles CircuitIR canonical data structures into executable KiCad projects.
    """

    def __init__(self, circuit: CircuitIR, route_pcb: bool = False):
        self.circuit = circuit
        # Straight-line stub routing usually shorts other nets, producing DRC
        # errors. Real routing belongs to FreeRouting, so leave the board
        # unrouted by default: pads carry the nets, which is what matters.
        self.route_pcb = route_pcb

    def export_project(self, output_dir: Path, project_name: str = "design") -> Dict[str, Path]:
        """
        Exports all project files to specified directory.
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        sch_file = output_dir / f"{project_name}.kicad_sch"
        pcb_file = output_dir / f"{project_name}.kicad_pcb"
        pro_file = output_dir / f"{project_name}.kicad_pro"

        sch_file.write_text(self.generate_schematic())
        pcb_file.write_text(self.generate_pcb())
        pro_file.write_text(self.generate_project_config(project_name))

        return {
            "sch": sch_file,
            "pcb": pcb_file,
            "pro": pro_file,
        }

    def generate_schematic(self) -> str:
        """
        Generate a KiCad schematic that actually has electrical connectivity.

        The previous implementation emitted only `(symbol (lib_id ...))` blocks:
        no `lib_symbols` definitions, no pin instances, and no wires or labels.
        KiCad could open such a file but extracted an *empty netlist*, so the
        schematic was decorative.

        A usable schematic needs three things, all emitted here:

        1. a `lib_symbols` definition for every symbol used;
        2. a symbol instance that declares each of its pins with a UUID;
        3. a wire stub plus a local label on every connected pin. Labels with
           the same text are the same net, so connectivity does not depend on
           drawing geometrically perfect wires between parts.

        Verified by exporting a netlist with `kicad-cli sch export netlist`.
        """
        sch_uuid = str(uuid.uuid4())
        project_name = self.circuit.name or "design"

        library = get_symbol_library()
        x_pos, y_pos = 50.0, 50.0
        step_x, step_y = 50.0, 45.0

        lib_defs: List[str] = []
        seen_lib_defs: set = set()
        symbols_sexpr: List[str] = []
        wires: List[str] = []
        labels: List[str] = []
        unresolved: List[str] = []

        for ref, comp in self.circuit.components.items():
            lib_id = comp.symbol if ":" in (comp.symbol or "") else ""
            definition = library.load(lib_id) if lib_id else None

            # Place the symbol.
            symbols_sexpr.append(
                self._render_symbol_instance(
                    ref, comp, lib_id, definition, x_pos, y_pos, project_name, sch_uuid
                )
            )

            if definition is not None and definition.definition_sexpr not in seen_lib_defs:
                seen_lib_defs.add(definition.definition_sexpr)
                lib_defs.append(definition.definition_sexpr)

            # Wire stubs and labels for every connected pin.
            if definition is not None:
                for pin in comp.pins:
                    if not pin.connected_net:
                        continue
                    symbol_pin = self._match_symbol_pin(definition, pin)
                    if symbol_pin is None:
                        continue
                    # Symbol space is Y-up; the sheet is Y-down.
                    abs_x = x_pos + symbol_pin.x
                    abs_y = y_pos - symbol_pin.y
                    stub_end_y = abs_y - 2.54
                    wires.append(
                        f'  (wire (pts (xy {abs_x:.4f} {abs_y:.4f}) '
                        f'(xy {abs_x:.4f} {stub_end_y:.4f}))\n'
                        f'    (stroke (width 0) (type default))\n'
                        f'    (uuid "{self._uuid(ref, pin.number, "wire")}")\n  )'
                    )
                    labels.append(
                        f'  (label "{pin.connected_net}" '
                        f'(at {abs_x:.4f} {stub_end_y:.4f} 0)\n'
                        f'    (effects (font (size 1.27 1.27)) (justify left bottom))\n'
                        f'    (uuid "{self._uuid(ref, pin.number, "label")}")\n  )'
                    )
            else:
                unresolved.append(f"{ref} ({comp.symbol or 'no symbol'})")

            x_pos += step_x
            if x_pos > 250.0:
                x_pos = 50.0
                y_pos += step_y

        if unresolved:
            logger.warning(
                "Schematic connectivity incomplete; symbol library not found for: %s",
                ", ".join(unresolved),
            )

        lib_block = "\n".join(f"    {d}" for d in lib_defs)
        symbols_block = "\n".join(symbols_sexpr)
        wires_block = "\n".join(wires)
        labels_block = "\n".join(labels)

        return f"""(kicad_sch
  (version 20231121)
  (generator "ai-electronics-platform")
  (generator_version "1.0.0")
  (uuid "{sch_uuid}")
  (paper "A4")
  (title_block
    (title "{self.circuit.name}")
    (comment 1 "{self.circuit.description}")
  )
  (lib_symbols
{lib_block}
  )
{symbols_block}
{wires_block}
{labels_block}
  (sheet_instances
    (path "/"
      (page "1")
    )
  )
)
"""

    @staticmethod
    def _uuid(*parts: Any) -> str:
        """Deterministic UUID so regenerating a project is reproducible."""
        return str(uuid.uuid5(uuid.NAMESPACE_DNS, "|".join(str(p) for p in parts)))

    @staticmethod
    def _match_symbol_pin(definition, pin):
        """Match a Circuit IR pin to the symbol's pin (by number, then name)."""
        wanted_number = str(pin.number).strip().lower()
        for candidate in definition.pins:
            if candidate.number.strip().lower() == wanted_number:
                return candidate
        wanted_name = str(pin.name).strip().lower()
        for candidate in definition.pins:
            if candidate.name.strip().lower() == wanted_name:
                return candidate
        return None

    def _render_symbol_instance(
        self, ref, comp, lib_id, definition, x_pos, y_pos, project_name, sch_uuid
    ) -> str:
        """Render one `(symbol ...)` instance, including its pin declarations."""
        if definition is not None:
            pin_lines = "\n".join(
                f'    (pin "{p.number}" (uuid "{self._uuid(ref, p.number, "pin")}"))'
                for p in definition.pins
            )
        else:
            pin_lines = ""

        return f"""  (symbol
    (lib_id "{lib_id}")
    (at {x_pos:.2f} {y_pos:.2f} 0)
    (unit 1)
    (exclude_from_sim no)
    (in_bom yes)
    (on_board yes)
    (dnp no)
    (uuid "{self._uuid(ref, "symbol")}")
    (property "Reference" "{ref}" (at {x_pos + 3:.2f} {y_pos - 2:.2f} 0)
      (effects (font (size 1.27 1.27)))
    )
    (property "Value" "{comp.value}" (at {x_pos + 3:.2f} {y_pos + 2:.2f} 0)
      (effects (font (size 1.27 1.27)))
    )
    (property "Footprint" "{comp.footprint}" (at {x_pos:.2f} {y_pos:.2f} 0)
      (effects (font (size 1.27 1.27)) hide)
    )
{pin_lines}
    (instances
      (project "{project_name}"
        (path "/{sch_uuid}"
          (reference "{ref}") (unit 1)
        )
      )
    )
  )"""

    def generate_pcb(self) -> str:
        """
        Generate a KiCad PCB whose footprints carry real pads and assigned nets.

        The previous implementation wrote `(footprint "Lib:Name" ...)` blocks
        containing no `(pad ...)` elements and connected nets with
        `(segment (start D1.2) (end R1.2) ...)` -- designator references where
        KiCad requires coordinates. `kicad-cli` refused to load the result
        ("Failed to load board"), so DRC, Gerber export and routing could not
        work on a generated design.

        Pads are copied from the locally installed KiCad footprint libraries
        (see `src/generators/kicad_footprints.py`). Using the real definitions
        guarantees pad numbers match the pin numbers from the netlist, which is
        what makes net assignment meaningful.

        Every net is declared at board level and assigned to the pads that
        belong to it, so KiCad reports no unconnected pads and FreeRouting has
        the correct connectivity to route. Copper is left to the router
        (`route_pcb=True` emits naive stub tracks for inspection only).
        """
        library = get_footprint_library()

        # Assign a stable number to every net (0 is reserved for "no net").
        net_numbers: Dict[str, int] = {}
        for comp in self.circuit.components.values():
            for pin in comp.pins:
                if pin.connected_net and pin.connected_net not in net_numbers:
                    net_numbers[pin.connected_net] = len(net_numbers) + 1

        footprints: List[str] = []
        placements: Dict[str, Dict[str, Tuple[float, float]]] = {}
        pad_nets_by_ref: Dict[str, Dict[str, str]] = {}
        unresolved: List[str] = []

        positions_by_ref, board_size = self._plan_placement()
        total = max(len(self.circuit.components), 1)
        cols = max(1, int(math.ceil(math.sqrt(total))))
        x0, y0, pitch = 60.0, 60.0, 30.0

        for index, (ref, comp) in enumerate(self.circuit.components.items()):
            if ref in positions_by_ref:
                at_x, at_y = positions_by_ref[ref]
            else:
                # Fallback grid, used only if placement could not run.
                col, row = index % cols, index // cols
                at_x = x0 + col * pitch
                at_y = y0 + row * pitch

            definition = library.load(comp.footprint) if comp.footprint else None
            if definition is None:
                unresolved.append(f"{ref} ({comp.footprint or 'no footprint'})")
                continue

            # Nets for this footprint's pads, keyed by pad number.
            pad_nets: Dict[str, Tuple[int, str]] = {}
            for pin in comp.pins:
                if not pin.connected_net:
                    continue
                pad_nets[str(pin.number)] = (
                    net_numbers[pin.connected_net],
                    pin.connected_net,
                )

            footprints.append(
                self._render_footprint(ref, comp, definition, at_x, at_y, pad_nets)
            )

            # Absolute pad coordinates, and which net each pad belongs to.
            positions: Dict[str, Tuple[float, float]] = {}
            net_names: Dict[str, str] = {}
            for pad in place_pads(definition, at_x, at_y, 0.0):
                positions.setdefault(pad.number, (pad.x, pad.y))
                net = pad_nets.get(pad.number)
                if net is not None:
                    net_names.setdefault(pad.number, net[1])
            placements[ref] = positions
            pad_nets_by_ref[ref] = net_names

        if unresolved:
            logger.warning(
                "PCB incomplete; footprint not found in installed KiCad "
                "libraries for: %s",
                ", ".join(unresolved),
            )

        tracks = (
            self._route_tracks(placements, pad_nets_by_ref, net_numbers)
            if self.route_pcb
            else []
        )

        net_decls = ['  (net 0 "")']
        for name, number in sorted(net_numbers.items(), key=lambda kv: kv[1]):
            net_decls.append(f'  (net {number} "{name}")')

        footprints_block = "\n".join(footprints)
        tracks_block = "\n".join(tracks)
        nets_block = "\n".join(net_decls)
        outline = self._render_board_outline(board_size, placements)

        return f"""(kicad_pcb
  (version 20240108)
  (generator "ai-electronics-platform")
  (generator_version "1.0.0")
  (general
    (thickness 1.6)
  )
  (paper "A4")
  (layers
    (0 "F.Cu" signal)
    (31 "B.Cu" signal)
    (36 "B.SilkS" user "B.Silkscreen")
    (37 "F.SilkS" user "F.Silkscreen")
    (38 "B.Mask" user)
    (39 "F.Mask" user)
    (44 "Edge.Cuts" user)
  )
  (setup
    (pad_to_mask_clearance 0.05)
  )
{nets_block}
{footprints_block}
{tracks_block}
{outline}
)
"""

    def _render_footprint(self, ref, comp, definition, at_x, at_y, pad_nets) -> str:
        """Place one library footprint onto the board with nets attached."""
        roots = _parse(_tokenize(definition.raw_text))
        fp_node = _find_node(roots, "footprint")
        if fp_node is None:  # pragma: no cover - defensive
            return ""

        # Use the library-qualified id so KiCad can match the library symbol.
        fp_node[1] = definition.lib_id

        # Drop library-file-level metadata that does not belong on a board.
        for key in ("version", "generator", "generator_version"):
            for child in list(fp_node):
                if isinstance(child, list) and child and child[0] == key:
                    fp_node.remove(child)

        _set_property(fp_node, "Reference", ref)
        _set_property(fp_node, "Value", comp.value)

        # Position the footprint just after its layer declaration.
        for i, child in enumerate(fp_node):
            if isinstance(child, list) and child and child[0] == "layer":
                fp_node.insert(i + 1, ["at", f"{at_x:.4f}", f"{at_y:.4f}"])
                break
        fp_node.append(["uuid", self._uuid(ref, "footprint")])

        # Attach a net to every pad that has one. Pads sharing a number (for
        # example a SOT-223 tab) all receive the same net.
        for child in fp_node:
            if not isinstance(child, list) or not child or child[0] != "pad":
                continue
            if len(child) < 2:
                continue
            net = pad_nets.get(str(child[1]))
            if net is None:
                continue
            number, name = net
            child.append(["net", str(number), name])

        return "  " + _render_sexpr(fp_node).replace("\n", "\n  ")

    def _route_tracks(
        self,
        placements: Dict[str, Dict[str, Tuple[float, float]]],
        pad_nets_by_ref: Dict[str, Dict[str, str]],
        net_numbers: Dict[str, int],
    ) -> List[str]:
        """
        Emit a starting track for each pair of pads sharing a net.

        Each connection becomes two orthogonal segments (an L route) using real
        pad coordinates, giving the board actual copper and giving FreeRouting a
        connected starting point.
        """
        # net name -> [(ref, pad number, x, y)]
        net_pads: Dict[str, List[Tuple[str, str, float, float]]] = {}
        for ref, net_names in pad_nets_by_ref.items():
            positions = placements.get(ref, {})
            for pad_number, net_name in net_names.items():
                position = positions.get(pad_number)
                if position is None:
                    continue
                net_pads.setdefault(net_name, []).append(
                    (ref, pad_number, position[0], position[1])
                )

        tracks: List[str] = []
        track_count = 0
        for net_name, pins in net_pads.items():
            if len(pins) < 2:
                continue
            anchor = pins[0]
            for other in pins[1:]:
                # L-shaped route: horizontal from the anchor, then vertical.
                corner = (other[2], anchor[3])
                for start, end in (
                    ((anchor[2], anchor[3]), corner),
                    (corner, (other[2], other[3])),
                ):
                    if start == end:
                        continue
                    track_count += 1
                    tracks.append(
                        f'  (segment (start {start[0]:.4f} {start[1]:.4f}) '
                        f'(end {end[0]:.4f} {end[1]:.4f}) (width 0.25) '
                        f'(layer "F.Cu") (net {net_numbers[net_name]}) '
                        f'(uuid "{self._uuid("track", track_count)}"))'
                    )
        return tracks

    def _plan_placement(self) -> Tuple[Dict[str, Tuple[float, float]], Tuple[float, float]]:
        """
        Decide where each component goes, using the smart placement engine.

        Returns a mapping of reference designator to (x, y) and the required
        board size (width, height). Placement considers collision avoidance,
        thermal separation and signal-integrity grouping
        (`src/pcb/smart_placement.py`).

        On any failure this returns an empty mapping, and the caller falls back
        to the simple grid so that PCB generation never fails because of the
        placer.
        """
        try:
            from src.pcb.smart_placement import SmartPlacer

            # Start generous; the placer packs into the area it is given, and the
            # outline is tightened afterwards from the real pads.
            side = max(60.0, 25.0 * math.sqrt(max(len(self.circuit.components), 1)))
            placer = SmartPlacer(
                self.circuit, board_width=side, board_height=side * 0.8
            )
            placed = placer.place_all()
        except Exception as exc:  # noqa: BLE001 - placement must never be fatal
            logger.warning(
                "Smart placement unavailable (%s: %s); falling back to a grid",
                type(exc).__name__,
                exc,
            )
            return {}, (180.0, 120.0)

        positions = {ref: pc.position for ref, pc in placed.items()}
        return positions, (side, side * 0.8)

    @staticmethod
    def _render_board_outline(
        board_size: Optional[Tuple[float, float]] = None,
        placements: Optional[Dict[str, Dict[str, Tuple[float, float]]]] = None,
    ) -> str:
        """
        A rectangular board outline sized around the actual placement.

        The outline is derived from real pad coordinates with a margin, so the
        board fits what is on it instead of using a fixed rectangle that may be
        far larger (or smaller) than necessary.
        """
        margin = 5.0
        xs: List[float] = []
        ys: List[float] = []
        for pads in (placements or {}).values():
            for x, y in pads.values():
                xs.append(x)
                ys.append(y)

        if xs and ys:
            left, right = min(xs) - margin, max(xs) + margin
            top, bottom = min(ys) - margin, max(ys) + margin
        else:
            width, height = board_size or (60.0, 40.0)
            left, top, right, bottom = 0.0, 0.0, width, height

        # Keep a sensible minimum size so a tiny circuit does not produce a
        # board that is awkward to handle or fabricate.
        min_side = 20.0
        if right - left < min_side:
            centre = (left + right) / 2
            left, right = centre - min_side / 2, centre + min_side / 2
        if bottom - top < min_side:
            centre = (top + bottom) / 2
            top, bottom = centre - min_side / 2, centre + min_side / 2

        corners = [
            (left, top), (right, top), (right, bottom), (left, bottom), (left, top),
        ]
        lines = []
        for (x1, y1), (x2, y2) in zip(corners, corners[1:]):
            lines.append(
                f'  (gr_line (start {x1:.4f} {y1:.4f}) (end {x2:.4f} {y2:.4f}) '
                f'(layer "Edge.Cuts") (width 0.1))'
            )
        return "\n".join(lines)

    def generate_project_config(self, project_name: str) -> str:
        """Generates KiCad project JSON file (.kicad_pro)."""
        config = {
            "meta": {
                "filename": f"{project_name}.kicad_pro",
                "version": 1
            },
            "schematic": {
                "annotate_start_num": 1,
                "drawing": {
                    "field_names": []
                }
            },
            "board": {
                "design_settings": {
                    "defaults": {
                        "track_width": 0.25,
                        "via_diameter": 0.8,
                        "via_hole": 0.4
                    }
                }
            }
        }
        return json.dumps(config, indent=2)
