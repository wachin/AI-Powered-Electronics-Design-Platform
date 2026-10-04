"""
AI Design Orchestrator for AI-Powered Electronics Design Platform.

Pipeline:
1. Natural language requirements -> Engineering spec
2. Component selection from catalog
3. Circuit IR synthesis
4. Deterministic ERC validation
5. SPICE simulation (ngspice)
6. KiCad project compilation & manufacturing exports
7. PCB auto-routing (FreeRouting)
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
from src.simulation.ngspice import simulate_circuit, SimulationResult
from src.routing.freerouting import route_kicad_pcb, RoutingResult


@dataclass
class DesignRequest:
    prompt: str
    project_name: str = "ai_generated_circuit"
    run_spice: bool = True
    run_routing: bool = True


@dataclass
class DesignSummary:
    project_name: str
    circuit_ir: CircuitIR
    erc_report: ERCReport
    spice_result: Optional[SimulationResult]
    routing_result: Optional[RoutingResult]
    generated_files: Dict[str, Path]
    bom: List[Dict[str, Any]]

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "project_name": self.project_name,
            "circuit_ir": self.circuit_ir.to_dict(),
            "erc_report": self.erc_report.to_dict(),
            "generated_files": {k: str(v) for k, v in self.generated_files.items()},
            "bom": self.bom,
        }
        if self.spice_result:
            result["spice_result"] = {
                "success": self.spice_result.success,
                "stdout": self.spice_result.stdout[:2000] if self.spice_result.stdout else "",
                "stderr": self.spice_result.stderr[:2000] if self.spice_result.stderr else "",
            }
        if self.routing_result:
            result["routing_result"] = {
                "success": self.routing_result.success,
                "routed_pcb": str(self.routing_result.routed_ses_path) if self.routing_result.routed_ses_path else None,
            }
        return result


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
        print("=" * 60)
        print("🤖 AI-Powered Electronics Design Platform")
        print("   Orchestration Flow")
        print("=" * 60)

        # Step 1: Synthesize Circuit IR based on natural language analysis
        print("\n📝 Step 1: Synthesizing Circuit IR from requirements...")
        circuit = self._synthesize_circuit_ir(request.prompt, request.project_name)
        print(f"   ✅ Circuit IR created: {len(circuit.components)} components, {len(circuit.nets)} nets")

        # Step 2: Validate circuit with ERC
        print("\n🔍 Step 2: Running ERC validation...")
        validator = ERCValidator(circuit)
        erc_report = validator.validate()
        status = "✅ PASSED" if erc_report.passed else "❌ FAILED"
        print(f"   {status} - Errors: {erc_report.summary['errors']}, Warnings: {erc_report.summary['warnings']}")

        # Step 3: SPICE Simulation (if requested)
        spice_result = None
        if request.run_spice:
            print("\n⚡ Step 3: Running SPICE simulation (ngspice)...")
            spice_result = simulate_circuit(circuit)
            if spice_result.success:
                print(f"   ✅ SPICE simulation completed successfully")
            else:
                print(f"   ⚠️  SPICE simulation failed: {spice_result.error or spice_result.stderr[:100]}")

        # Step 4: Compile KiCad EDA project files
        print("\n🔧 Step 4: Generating KiCad project files...")
        generator = KiCadGenerator(circuit)
        generated_files = generator.export_project(output_dir, request.project_name)
        print(f"   ✅ Generated: SCH, PCB, PRO")

        # Step 5: PCB Auto-routing with FreeRouting (if requested)
        routing_result = None
        if request.run_routing:
            print("\n🛣️  Step 5: Running PCB auto-routing (FreeRouting)...")
            pcb_path = generated_files["pcb"]
            routing_result = route_kicad_pcb(pcb_path)
            if routing_result.success:
                print(f"   ✅ PCB auto-routing completed")
                # Add routed PCB to generated files
                if routing_result.routed_ses_path and routing_result.routed_ses_path.exists():
                    generated_files["pcb_routed"] = routing_result.routed_ses_path
            else:
                print(f"   ⚠️  PCB auto-routing failed: {routing_result.error}")

        # Step 6: Generate Bill of Materials (BOM)
        print("\n📦 Step 6: Generating Bill of Materials...")
        bom = self._generate_bom(circuit)
        total_cost = sum(item["total_price"] for item in bom)
        print(f"   ✅ BOM generated: {len(bom)} unique parts, ~${total_cost:.2f} estimated")

        print("\n" + "=" * 60)
        print("🎉 Design synthesis complete!")
        print("=" * 60)

        return DesignSummary(
            project_name=request.project_name,
            circuit_ir=circuit,
            erc_report=erc_report,
            spice_result=spice_result,
            routing_result=routing_result,
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