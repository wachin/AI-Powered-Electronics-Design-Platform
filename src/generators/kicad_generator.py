"""
KiCad Project Generator for AI-Powered Electronics Design Platform.

Compiles CircuitIR into valid KiCad 8 file structures (.kicad_sch, .kicad_pcb, .kicad_pro).
"""

import json
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from src.core.circuit_ir import CircuitIR, Component, Net, ComponentType


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
        """Generates valid KiCad 8 schematic S-expression format."""
        sch_uuid = str(uuid.uuid4())
        
        symbols_sexpr = []
        x_pos = 50.0
        y_pos = 50.0

        for ref, comp in self.circuit.components.items():
            comp_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"{self.circuit.id}_{ref}"))
            lib_symbol = comp.symbol if ":" in comp.symbol else f"Device:{comp.symbol}"
            
            # Form symbol entry
            symbols_sexpr.append(f"""  (symbol
    (lib_id "{lib_symbol}")
    (at {x_pos:.2f} {y_pos:.2f} 0)
    (unit 1)
    (in_bom yes)
    (on_board yes)
    (uuid "{comp_uuid}")
    (property "Reference" "{ref}" (at {x_pos:.2f} {y_pos - 3:.2f} 0)
      (effects (font (size 1.27 1.27)))
    )
    (property "Value" "{comp.value}" (at {x_pos:.2f} {y_pos + 3:.2f} 0)
      (effects (font (size 1.27 1.27)))
    )
    (property "Footprint" "{comp.footprint}" (at {x_pos:.2f} {y_pos + 6:.2f} 0)
      (effects (font (size 1.27 1.27)) hide)
    )
  )""")
            
            x_pos += 40.0
            if x_pos > 250.0:
                x_pos = 50.0
                y_pos += 40.0

        symbols_block = "\n".join(symbols_sexpr)

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
{symbols_block}
  (sheet_instances
    (path "/"
      (page "1")
    )
  )
)
"""

    def generate_pcb(self) -> str:
        """Generates valid KiCad 8 PCB layout S-expression format."""
        pcb_uuid = str(uuid.uuid4())
        
        footprints_sexpr = []
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
