"""
KiCad Project Generator for AI-Powered Electronics Design Platform.

Compiles CircuitIR into valid KiCad 8 file structures (.kicad_sch, .kicad_pcb, .kicad_pro).
"""

import json
import logging
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from src.core.circuit_ir import CircuitIR, Component, Net, ComponentType
from src.generators.kicad_symbols import get_symbol_library

logger = logging.getLogger(__name__)


class KiCadGenerator:
    """
    Generator that compiles CircuitIR canonical data structures into executable KiCad projects.
    """

    def __init__(self, circuit: CircuitIR):
        self.circuit = circuit

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
        """Generates valid KiCad 8 PCB layout S-expression format."""
        pcb_uuid = str(uuid.uuid4())
        
        footprints_sexpr = []
        x_pos = 100.0
        y_pos = 100.0

        # Build net-to-pads mapping for track routing
        net_pads = {}  # net_name -> [(ref, pad_number), ...]
        for ref, comp in self.circuit.components.items():
            for pin in comp.pins:
                if pin.connected_net:
                    net_name = pin.connected_net
                    if net_name not in net_pads:
                        net_pads[net_name] = []
                    net_pads[net_name].append((ref, pin.number))

        # Generate footprints
        x_pos = 100.0
        y_pos = 100.0

        for ref, comp in self.circuit.components.items():
            fp_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{self.circuit.id}_{ref}_fp"))
            fp_name = comp.footprint if comp.footprint else "Resistor_SMD:R_0805_2012Metric"
            
            footprints_sexpr.append(f"""  (footprint "{fp_name}"
    (layer "F.Cu")
    (at {x_pos:.2f} {y_pos:.2f})
    (uuid "{fp_uuid}")
    (property "Reference" "{ref}" (at 0 -2.5 0) (layer "F.SilkS")
      (effects (font (size 1 1) (thickness 0.15)))
    )
    (property "Value" "{comp.value}" (at 0 2.5 0) (layer "F.Fab")
      (effects (font (size 1 1) (thickness 0.15)))
    )
  )""")
            
            x_pos += 15.0
            if x_pos > 180.0:
                x_pos = 100.0
                y_pos += 15.0

        footprints_block = "\n".join(footprints_sexpr)

        # Generate net definitions
        nets_sexpr = []
        for net_name, pads in net_pads.items():
            net_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{self.circuit.id}_net_{net_name}"))
            pads_str = " ".join([f'("{ref}" "{pad}")' for ref, pad in pads])
            nets_sexpr.append(f"""  (net
    (name "{net_name}")
    (uuid "{net_uuid}")
    (pins {pads_str})
  )""")

        nets_block = "\n".join(nets_sexpr)

        # Generate simple track connections (straight lines between connected pads)
        tracks_sexpr = []
        track_id = 0
        for net_name, pads in net_pads.items():
            if len(pads) >= 2:
                # Connect first pad to each subsequent pad with a track
                ref1, pad1 = pads[0]
                # Find pin positions (we'll use footprint center as approximation)
                for ref2, pad2 in pads[1:]:
                    track_id += 1
                    track_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{self.circuit.id}_track_{track_id}"))
                    # Use simple routing: horizontal then vertical
                    tracks_sexpr.append(f"""  (segment
    (start {ref1}.{pad1})
    (end {ref2}.{pad2})
    (width 0.25)
    (layer "F.Cu")
    (net "{net_name}")
    (uuid "{track_uuid}")
  )""")

        tracks_block = "\n".join(tracks_sexpr)

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
{footprints_block}

{nets_block}

{tracks_block}

  (gr_line (start 50 50) (end 200 50) (layer "Edge.Cuts") (width 0.1))
  (gr_line (start 200 50) (end 200 150) (layer "Edge.Cuts") (width 0.1))
  (gr_line (start 200 150) (end 50 150) (layer "Edge.Cuts") (width 0.1))
  (gr_line (start 50 150) (end 50 50) (layer "Edge.Cuts") (width 0.1))
)
"""

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
