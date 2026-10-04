"""
AI Design Orchestrator for AI-Powered Electronics Design Platform.

Pipeline:
1. Natural language requirements -> Engineering spec
2. Component selection from catalog
3. Circuit IR synthesis
4. Deterministic ERC validation
5. KiCad project compilation & manufacturing exports
"""

import json
from pathlib import Path
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional

from src.core.circuit_ir import (
    CircuitIR,
    Component,
    ComponentType,
    PinType,
    PowerDomain,
)
from src.core.erc import ERCValidator, ERCReport
from src.generators.kicad_generator import KiCadGenerator
from src.components.database import ComponentDatabase, ComponentSpec


@dataclass
class DesignRequest:
    prompt: str
    project_name: str = "ai_generated_circuit"


@dataclass
class DesignSummary:
    project_name: str
    circuit_ir: CircuitIR
    erc_report: ERCReport
    generated_files: Dict[str, Path]
    bom: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_name": self.project_name,
            "circuit_ir": self.circuit_ir.to_dict(),
            "erc_report": self.erc_report.to_dict(),
            "generated_files": {k: str(v) for k, v in self.generated_files.items()},
            "bom": self.bom,
        }


class AIDesignOrchestrator:
    """
    AI Orchestrator driving autonomous electronics design generation.
    """

    def __init__(self, db: Optional[ComponentDatabase] = None):
        self.db = db or ComponentDatabase()

    def process_request(self, request: DesignRequest, output_dir: Path) -> DesignSummary:
        """
        Executes full end-to-end circuit synthesis pipeline.
        """
        # Step 1: Synthesize Circuit IR based on natural language analysis
        circuit = self._synthesize_circuit_ir(request.prompt, request.project_name)

        # Step 2: Validate circuit with ERC
        validator = ERCValidator(circuit)
        erc_report = validator.validate()

        # Step 3: Compile KiCad EDA project files
        generator = KiCadGenerator(circuit)
        generated_files = generator.export_project(output_dir, request.project_name)

        # Step 4: Generate Bill of Materials (BOM)
        bom = self._generate_bom(circuit)

        return DesignSummary(
            project_name=request.project_name,
            circuit_ir=circuit,
            erc_report=erc_report,
            generated_files=generated_files,
            bom=bom,
        )

    def _synthesize_circuit_ir(self, prompt: str, project_name: str) -> CircuitIR:
        """
        Synthesizes a structured Circuit IR based on input requirements.
        """
        p = prompt.lower()
        circuit = CircuitIR(name=project_name, description=prompt)

        # Voltage Regulator Pattern
        if "regulator" in p or "5v to 3.3v" in p or "ldo" in p:
            # 1. Fetch Parts from DB
            ldo_spec = self.db.get_by_mpn("AMS1117-3.3") or self.db.search(category="regulator_ldo")[0]
            c_in_spec = self.db.get_by_mpn("C-10uF-0805") or self.db.search(category="capacitor")[0]
            c_out_spec = self.db.get_by_mpn("C-22uF-0805") or self.db.search(category="capacitor")[0]
            res_spec = self.db.get_by_mpn("R-330-0805") or self.db.search(category="resistor")[0]
            led_spec = self.db.get_by_mpn("LED-GREEN-0805") or self.db.search(category="led")[0]

            # 2. Instantiate LDO Regulator
            u1 = Component(
                ref="U1",
                value=ldo_spec.value,
                component_type=ComponentType.REGULATOR_LDO,
                footprint=ldo_spec.footprint,
                symbol=ldo_spec.symbol,
                mpn=ldo_spec.mpn,
                manufacturer=ldo_spec.manufacturer,
                description=ldo_spec.description,
            )
            u1.add_pin("1", "GND", PinType.POWER_IN)
            u1.add_pin("2", "VOUT", PinType.POWER_OUT)
            u1.add_pin("3", "VIN", PinType.POWER_IN)
            circuit.add_component(u1)

            # 3. Input Capacitor C1
            c1 = Component(
                ref="C1",
                value=c_in_spec.value,
                component_type=ComponentType.CAPACITOR,
                footprint=c_in_spec.footprint,
                symbol=c_in_spec.symbol,
                mpn=c_in_spec.mpn,
            )
            c1.add_pin("1", "1", PinType.PASSIVE)
            c1.add_pin("2", "2", PinType.PASSIVE)
            circuit.add_component(c1)

            # 4. Output Capacitor C2
            c2 = Component(
                ref="C2",
                value=c_out_spec.value,
                component_type=ComponentType.CAPACITOR,
                footprint=c_out_spec.footprint,
                symbol=c_out_spec.symbol,
                mpn=c_out_spec.mpn,
            )
            c2.add_pin("1", "1", PinType.PASSIVE)
            c2.add_pin("2", "2", PinType.PASSIVE)
            circuit.add_component(c2)

            # 5. Indicator LED D1 & Resistor R1
            d1 = Component(
                ref="D1",
                value=led_spec.value,
                component_type=ComponentType.LED,
                footprint=led_spec.footprint,
                symbol=led_spec.symbol,
                mpn=led_spec.mpn,
            )
            d1.add_pin("1", "K", PinType.PASSIVE)
            d1.add_pin("2", "A", PinType.PASSIVE)
            circuit.add_component(d1)

            r1 = Component(
                ref="R1",
                value=res_spec.value,
                component_type=ComponentType.RESISTOR,
                footprint=res_spec.footprint,
                symbol=res_spec.symbol,
                mpn=res_spec.mpn,
            )
            r1.add_pin("1", "1", PinType.PASSIVE)
            r1.add_pin("2", "2", PinType.PASSIVE)
            circuit.add_component(r1)

            # 6. Establish Net Connections
            circuit.connect("U1", "VIN", "5V")
            circuit.connect("C1", "1", "5V")

            circuit.connect("U1", "VOUT", "3.3V")
            circuit.connect("C2", "1", "3.3V")
            circuit.connect("R1", "1", "3.3V")

            circuit.connect("R1", "2", "NET_LED_ANODE")
            circuit.connect("D1", "2", "NET_LED_ANODE")

            circuit.connect("U1", "GND", "GND")
            circuit.connect("C1", "2", "GND")
            circuit.connect("C2", "2", "GND")
            circuit.connect("D1", "1", "GND")

            # Power Net metadata
            circuit.get_or_create_net("5V", is_power=True, voltage=5.0)
            circuit.get_or_create_net("3.3V", is_power=True, voltage=3.3)
            circuit.get_or_create_net("GND", is_power=True, voltage=0.0)

            circuit.power_domains["5V_Domain"] = PowerDomain(name="5V_Domain", voltage=5.0, max_current_ma=1000)
            circuit.power_domains["3V3_Domain"] = PowerDomain(name="3V3_Domain", voltage=3.3, max_current_ma=1000)

        else:
            # Generic simple circuit
            r_spec = self.db.search(category="resistor")[0]
            led_spec = self.db.search(category="led")[0]

            r1 = Component(
                ref="R1",
                value=r_spec.value,
                component_type=ComponentType.RESISTOR,
                footprint=r_spec.footprint,
                symbol=r_spec.symbol,
                mpn=r_spec.mpn,
            )
            r1.add_pin("1", "1", PinType.PASSIVE)
            r1.add_pin("2", "2", PinType.PASSIVE)
            circuit.add_component(r1)

            d1 = Component(
                ref="D1",
                value=led_spec.value,
                component_type=ComponentType.LED,
                footprint=led_spec.footprint,
                symbol=led_spec.symbol,
                mpn=led_spec.mpn,
            )
            d1.add_pin("1", "K", PinType.PASSIVE)
            d1.add_pin("2", "A", PinType.PASSIVE)
            circuit.add_component(d1)

            circuit.connect("R1", "1", "VCC")
            circuit.connect("R1", "2", "NET_LED_A")
            circuit.connect("D1", "2", "NET_LED_A")
            circuit.connect("D1", "1", "GND")

            circuit.get_or_create_net("VCC", is_power=True, voltage=5.0)
            circuit.get_or_create_net("GND", is_power=True, voltage=0.0)

        return circuit

    def _generate_bom(self, circuit: CircuitIR) -> List[Dict[str, Any]]:
        """Generates Bill of Materials (BOM) from Circuit IR."""
        bom_map: Dict[str, Dict[str, Any]] = {}

        for ref, comp in circuit.components.items():
            mpn = comp.mpn or comp.value
            if mpn not in bom_map:
                spec = self.db.get_by_mpn(mpn)
                price = spec.price if spec else 0.0
                mfr = comp.manufacturer or (spec.manufacturer if spec else "Generic")
                bom_map[mpn] = {
                    "mpn": mpn,
                    "value": comp.value,
                    "footprint": comp.footprint,
                    "manufacturer": mfr,
                    "quantity": 0,
                    "designators": [],
                    "unit_price": price,
                    "total_price": 0.0,
                }
            
            bom_map[mpn]["quantity"] += 1
            bom_map[mpn]["designators"].append(ref)
            bom_map[mpn]["total_price"] = bom_map[mpn]["quantity"] * bom_map[mpn]["unit_price"]

        return list(bom_map.values())
