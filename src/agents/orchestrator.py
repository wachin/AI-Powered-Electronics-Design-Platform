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
from src.components.ordering import build_purchase_list
from src.pcb.netclasses import (
    describe_netclasses,
    netclass_assignments,
    width_shortfalls,
)
from src.simulation.ngspice import simulate_circuit, SimulationResult
from src.routing.freerouting import route_kicad_pcb, RoutingResult
from src.llm.integration import NLToCircuitPipeline, create_nl_pipeline
from src.llm.providers import create_llm_client


@dataclass
class DesignRequest:
    prompt: str
    project_name: str = "ai_generated_circuit"
    run_spice: bool = True
    run_routing: bool = True
    # Ask an optional MCP server (kicad-mcp-server) for an independent ERC/DRC
    # opinion on the generated project. Off by default: it needs `mcp-setup`.
    mcp_validate: bool = False
    # How many boards are being built. Quantities in the purchase list scale with
    # this, and the distributor's own minimums and attrition are applied.
    boards: int = 1
    # Extra parts allowance as a fraction, e.g. 0.1 for 10% spares.
    spare_fraction: float = 0.0


@dataclass
class DesignSummary:
    project_name: str
    circuit_ir: CircuitIR
    erc_report: ERCReport
    spice_result: Optional[SimulationResult]
    routing_result: Optional[RoutingResult]
    generated_files: Dict[str, Path]
    bom: List[Dict[str, Any]]
    # The BOM turned into something orderable: LCSC part numbers, stock, prices
    # at the quantity being ordered, and the quantities to actually buy.
    purchase_list: Optional[Any] = None
    # Provenance: whether the design came from an LLM or the deterministic
    # template generator, and any substitution/inference notes.
    used_llm: bool = True
    topology: str = ""
    design_notes: List[str] = field(default_factory=list)
    validation: Optional[Dict[str, Any]] = None
    mcp_validation: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "project_name": self.project_name,
            "circuit_ir": self.circuit_ir.to_dict(),
            "erc_report": self.erc_report.to_dict(),
            "generated_files": {k: str(v) for k, v in self.generated_files.items()},
            "bom": self.bom,
            "total_cost": round(
                sum(item.get("total_price", 0.0) or 0.0 for item in self.bom), 4
            ),
            "used_llm": self.used_llm,
            "topology": self.topology,
            "design_notes": self.design_notes,
        }
        if self.validation is not None:
            result["validation"] = self.validation
        if self.purchase_list is not None:
            result["purchase_list"] = self.purchase_list.to_dict()
        if self.mcp_validation is not None:
            result["mcp_validation"] = self.mcp_validation
        if self.spice_result:
            result["spice_result"] = {
                "success": self.spice_result.success,
                "node_voltages": self.spice_result.node_voltages,
                "measurements": self.spice_result.measurements,
                "error": self.spice_result.error,
                "stdout": self.spice_result.stdout[:2000] if self.spice_result.stdout else "",
                "stderr": self.spice_result.stderr[:2000] if self.spice_result.stderr else "",
            }
        if self.routing_result:
            result["routing_result"] = {
                "success": self.routing_result.success,
                "routed_pcb": str(self.routing_result.routed_ses_path) if self.routing_result.routed_ses_path else None,
                "routed_widths": dict(self.routing_result.routed_widths),
                "width_warnings": list(self.routing_result.width_warnings),
            }
        return result


class AIDesignOrchestrator:
    """
    AI Orchestrator driving autonomous electronics design generation.
    """

    def __init__(
        self,
        db: Optional[ComponentDatabase] = None,
        llm_provider: str = "mock",
        llm_model: Optional[str] = None,
        llm_base_url: Optional[str] = None,
        allow_fallback: bool = True,
        max_repairs: int = 2,
    ):
        self.db = db or ComponentDatabase()
        self.llm_provider = llm_provider
        self.llm_model = llm_model
        self.llm_base_url = llm_base_url

        # Build the configured client. "mock" keeps the deterministic
        # template path for tests; any real provider name drives the LLM.
        client_kwargs: Dict[str, Any] = {}
        if llm_model:
            client_kwargs["model"] = llm_model
        if llm_base_url:
            client_kwargs["base_url"] = llm_base_url
        llm_client = create_llm_client(llm_provider, **client_kwargs)

        self.nl_pipeline = NLToCircuitPipeline(
            llm_client=llm_client,
            component_db=self.db,
            allow_fallback=allow_fallback,
            max_repairs=max_repairs,
        )
        self.nl_pipeline.set_orchestrator(self)

    async def process_request(self, request: DesignRequest, output_dir: Path) -> DesignSummary:
        """
        Executes full end-to-end circuit synthesis pipeline.
        """
        print("=" * 60)
        print("🤖 AI-Powered Electronics Design Platform")
        print("   Orchestration Flow")
        print("=" * 60)

        # Step 1: Natural Language -> Circuit IR (using NL pipeline)
        print("\n📝 Step 1: Synthesizing Circuit IR from requirements...")
        print(f"   📝 Prompt: {request.prompt}")
        
        # Use NL pipeline to convert natural language to CircuitIR
        result = await self.nl_pipeline.process(request.prompt, request.project_name)
        circuit_ir = result.get("circuit_ir")
        requirements = result.get("requirements", {})
        specification = result.get("specification", {})
        print(f"   ✅ Circuit IR created: {len(circuit_ir.components)} components, {len(circuit_ir.nets)} nets")

        # Step 2: Validate circuit with ERC
        print("\n🔍 Step 2: Running ERC validation...")
        validator = ERCValidator(circuit_ir)
        erc_report = validator.validate()
        status = "✅ PASSED" if erc_report.passed else "❌ FAILED"
        print(f"   {status} - Errors: {erc_report.summary['errors']}, Warnings: {erc_report.summary['warnings']}")

        # Step 3: SPICE Simulation (if requested)
        spice_result = None
        if request.run_spice:
            print("\n⚡ Step 3: Running SPICE simulation (ngspice)...")
            spice_result = simulate_circuit(circuit_ir)
            if spice_result.success and spice_result.has_results:
                print("   ✅ SPICE operating point computed:")
                for net, volts in spice_result.node_voltages.items():
                    print(f"        {net:<16} {volts:>8.3f} V")
            elif spice_result.success:
                print("   ⚠️  SPICE ran but produced no operating point to report")
            else:
                print(
                    f"   ⚠️  SPICE simulation failed: "
                    f"{spice_result.error or spice_result.stderr[:100]}"
                )

        # Step 4: Compile KiCad EDA project files
        print("\n🔧 Step 4: Generating KiCad project files...")
        generator = KiCadGenerator(circuit_ir)
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

                # Check the router delivered the widths the net classes asked
                # for. A router may narrow a trace where the wider one does not
                # fit, and a narrower trace carries less current than the design
                # was checked against.
                assignments = netclass_assignments(
                    circuit_ir.nets.values(),
                    getattr(circuit_ir, "power_domains", None),
                )
                routing_result.width_warnings = width_shortfalls(
                    routing_result.routed_widths, assignments
                )
                for rationale in describe_netclasses(assignments):
                    print(f"   ℹ️  {rationale}")
                for warning in routing_result.width_warnings:
                    print(f"   ⚠️  {warning}")
                if routing_result.routed_widths and not routing_result.width_warnings:
                    print(
                        "   ✅ Every routed net meets its net class width"
                    )
            else:
                print(f"   ⚠️  PCB auto-routing failed: {routing_result.error}")

        # Step 6: Generate Bill of Materials (BOM) and the purchase list.
        print("\n📦 Step 6: Generating Bill of Materials...")
        bom = self._generate_bom(circuit_ir)
        total_cost = sum(item["total_price"] for item in bom)
        print(f"   ✅ BOM generated: {len(bom)} unique parts, ~${total_cost:.2f} estimated")

        boards = max(int(getattr(request, "boards", 1) or 1), 1)
        spare_fraction = max(float(getattr(request, "spare_fraction", 0.0) or 0.0), 0.0)
        purchase_list = build_purchase_list(
            circuit_ir, self.db, boards=boards, spare_fraction=spare_fraction
        )
        try:
            bom_csv_path = output_dir / f"{request.project_name}-bom.csv"
            bom_csv_path.write_text(purchase_list.to_jlcpcb_csv(), encoding="utf-8")
            purchase_md_path = output_dir / f"{request.project_name}-purchase-list.md"
            purchase_md_path.write_text(purchase_list.to_markdown(), encoding="utf-8")
            generated_files["bom_csv"] = bom_csv_path
            generated_files["purchase_list"] = purchase_md_path
            orderable = len(purchase_list.orderable_lines)
            print(
                f"   ✅ Purchase list: {orderable}/{len(purchase_list.lines)} lines "
                f"orderable, {purchase_list.total_parts} parts, "
                f"~${purchase_list.total_cost:.2f} for {boards} board(s)"
            )
            for warning in purchase_list.warnings():
                print(f"   ⚠️  {warning}")
        except OSError as exc:
            print(f"   ⚠️  Could not write the purchase list: {exc}")

        # Step 7: Export 3D glTF for visualization
        print("\n🎨 Step 7: Exporting 3D glTF for visualization...")
        try:
            from src.generators.gltf_exporter import export_pcb_gltf
            gltf_path = output_dir / f"{request.project_name}.gltf"
            export_pcb_gltf(circuit_ir, gltf_path, 100, 80)
            generated_files["gltf"] = gltf_path
            print(f"   ✅ 3D glTF exported: {gltf_path}")
        except Exception as e:
            print(f"   ⚠️  3D export failed: {e}")

        # Step 8: optional independent check via an MCP server.
        mcp_validation = None
        if getattr(request, "mcp_validate", False):
            print("\n🔎 Step 8: Independent validation via MCP server...")
            mcp_validation = await self._run_mcp_validation(
                generated_files, output_dir, request.project_name
            )

        print("\n" + "=" * 60)
        print("🎉 Design synthesis complete!")
        print("=" * 60)

        return DesignSummary(
            project_name=request.project_name,
            circuit_ir=circuit_ir,
            erc_report=erc_report,
            spice_result=spice_result,
            routing_result=routing_result,
            generated_files=generated_files,
            bom=bom,
            purchase_list=purchase_list,
            used_llm=getattr(specification, "used_llm", True),
            topology=getattr(specification, "topology", "") or "",
            design_notes=list(getattr(specification, "warnings", []) or []),
            validation=result.get("validation").to_dict()
            if result.get("validation") is not None
            else None,
            mcp_validation=mcp_validation,
        )

    async def _run_mcp_validation(
        self, generated_files: Dict[str, Path], output_dir: Path, project_name: str
    ) -> Optional[Dict[str, Any]]:
        """
        Ask an MCP server to validate the generated project independently.

        Failure here never aborts the design: the deterministic checks have
        already run, and this is an additional opinion.
        """
        from src.agents.mcp_validation import validate_with_mcp

        try:
            outcome = await validate_with_mcp(
                files=generated_files,
                workspace=Path(output_dir) / "mcp_workspace",
                project_name=project_name,
            )
        except Exception as exc:  # noqa: BLE001 - never break generation
            print(f"   ⚠️  MCP validation unavailable: {exc}")
            return {"available": False, "error": str(exc)}

        if not outcome.available:
            print(f"   ⚠️  MCP validation skipped: {outcome.error}")
        else:
            status = "✅ no design violations" if outcome.violations == 0 else (
                f"{outcome.violations} finding(s)"
            )
            print(f"   ERC violations: {(outcome.erc or {}).get('violations')}")
            print(f"   DRC violations: {(outcome.drc or {}).get('violations')} ({status})")
            if outcome.only_library_warnings:
                print(
                    "   Note: DRC findings are KiCad library-table notices only "
                    "(the board embeds its footprints)."
                )
        return outcome.to_dict()

    def _select_part(
        self,
        category: str,
        query: str,
        value: Optional[str] = None,
    ) -> ComponentSpec:
        """
        Choose a component for a template circuit.

        Order of preference:

        1. The curated built-in part matching ``value``, because its symbol and
           pinout have been checked against the rest of the pipeline.
        2. A downloaded-catalog part found by *value* (a real part with stock
           and a datasheet).
        3. A downloaded-catalog part found by category alone, as a last resort.

        Raises:
            LookupError: if nothing is available at all. Returning a wrong part
                silently is worse than stopping: the failure is visible here,
                whereas a wrong value is discovered after the boards arrive.
        """
        if value:
            builtin = self.db.find_builtin(category, value=value)
            if builtin is not None:
                return builtin

        parts = self.db.search(query=query, category=category, min_stock=100, limit=1)
        if not parts:
            parts = self.db.search(query=query, category=category, limit=1)
        if not parts:
            parts = self.db.search(category=category, limit=1)
        if not parts:
            raise LookupError(
                f"No component available for {category!r} matching {query!r}. "
                f"Install the component catalog with: "
                f"ai-electronics-design catalog-setup"
            )
        return parts[0]

    def _synthesize_circuit_ir(self, prompt: str, project_name: str) -> CircuitIR:
        """
        Synthesizes a structured Circuit IR based on input requirements.
        """
        p = prompt.lower()
        circuit = CircuitIR(name=project_name, description=prompt)

        # Voltage Regulator Pattern
        if "regulator" in p or "5v to 3.3v" in p or "ldo" in p:
            # 1. Fetch Parts from DB.
            #
            # The values are stated explicitly. Picking "the first capacitor in
            # the catalog" would return whatever the catalog ranks first, which
            # is not a 10 uF input capacitor — and a design that silently uses
            # the wrong value is worse than one that fails. The curated parts are
            # preferred because their symbols and pinouts have been checked; a
            # catalog search by value is the fallback.
            ldo_spec = self._select_part("regulator_ldo", "3.3v", value="3.3V")
            c_in_spec = self._select_part("capacitor", "10uF 0805", value="10uF")
            c_out_spec = self._select_part("capacitor", "22uF 0805", value="22uF")
            res_spec = self._select_part("resistor", "330 0805", value="330")
            led_spec = self._select_part("led", "green 0805", value="Green")

            # 2. Instantiate LDO Regulator
            u1 = Component(
                ref="U1",
                value=ldo_spec.value,
                component_type=ComponentType.REGULATOR_LDO,
                footprint=ldo_spec.footprint,
                symbol=ldo_spec.symbol,
                package=ldo_spec.package,
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
                package=c_in_spec.package,
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
                package=c_out_spec.package,
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
                package=led_spec.package,
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
                package=res_spec.package,
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
            # Generic simple circuit: an LED with a current-limiting resistor.
            # A 330 ohm resistor on 5 V gives roughly 5 mA through a green LED,
            # which is visible without over-driving it.
            r_spec = self._select_part("resistor", "330 0805", value="330")
            led_spec = self._select_part("led", "green 0805", value="Green")

            r1 = Component(
                ref="R1",
                value=r_spec.value,
                component_type=ComponentType.RESISTOR,
                footprint=r_spec.footprint,
                symbol=r_spec.symbol,
                package=r_spec.package,
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
                package=led_spec.package,
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
                description = (
                    comp.description
                    or (spec.description if spec else "")
                    or comp.value
                )
                bom_map[mpn] = {
                    "mpn": mpn,
                    "value": comp.value,
                    "description": description,
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