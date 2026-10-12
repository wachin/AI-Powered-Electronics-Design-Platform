"""
SPICE Simulation Integration for AI-Powered Electronics Design Platform.

Compiles CircuitIR to SPICE netlists and runs ngspice for circuit verification.
"""

import re
import subprocess
import tempfile
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
from src.core.circuit_ir import CircuitIR, Component, ComponentType, PinType


@dataclass
class SimulationResult:
    success: bool
    stdout: str
    stderr: str
    measurements: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    @property
    def node_voltages(self) -> Dict[str, float]:
        """DC node voltages from the operating point, keyed by net name."""
        return dict(self.measurements.get("node_voltages", {}))

    @property
    def has_results(self) -> bool:
        """True when the run produced actual numbers, not just a clean exit."""
        return bool(self.node_voltages)


class NgSpiceRunner:
    """
    Runs SPICE simulations via ngspice CLI.
    """

    def __init__(self, ngspice_path: str = "ngspice"):
        self.ngspice_path = ngspice_path

    def run_simulation(self, netlist: str) -> SimulationResult:
        """Execute ngspice with given netlist and return results."""
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.cir', delete=False) as f:
                f.write(netlist)
                netlist_path = f.name

            result = subprocess.run(
                [self.ngspice_path, '-b', netlist_path],
                capture_output=True,
                text=True,
                timeout=60
            )

            Path(netlist_path).unlink(missing_ok=True)

            success = result.returncode == 0
            measurements = parse_operating_point(result.stdout)
            return SimulationResult(
                success=success,
                stdout=result.stdout,
                stderr=result.stderr,
                measurements=measurements,
                error=(
                    None
                    if measurements
                    else "ngspice ran but reported no operating point; "
                    "the netlist may be missing a DC source or a .op directive"
                ),
            )
        except subprocess.TimeoutExpired:
            return SimulationResult(
                success=False,
                stdout="",
                stderr="Simulation timeout (60s)",
                error="timeout"
            )
        except FileNotFoundError:
            return SimulationResult(
                success=False,
                stdout="",
                stderr="ngspice not found in PATH",
                error="not_found"
            )
        except Exception as e:
            return SimulationResult(
                success=False,
                stdout="",
                stderr=str(e),
                error=str(e)
            )


class CircuitIRToSpice:
    """
    Compiles CircuitIR to SPICE netlist format.
    """

    def __init__(self, circuit: CircuitIR):
        self.circuit = circuit
        self._net_name_map: Dict[str, str] = {}

    def _sanitize_net_name(self, net_name: str) -> str:
        """Convert net name to valid SPICE node name.

        SPICE node names must:
        - Start with a letter
        - Contain only alphanumeric characters and underscores
        """
        if not net_name:
            return "NET"

        # Replace invalid characters
        sanitized = re.sub(r'[^a-zA-Z0-9_]', '_', net_name)

        # Ensure starts with letter
        if sanitized and not sanitized[0].isalpha():
            sanitized = 'N_' + sanitized

        # Handle common voltage net names
        sanitized = sanitized.replace('V_', 'V').replace('_V', 'V')

        return sanitized

    def _get_spice_net_name(self, net_name: str) -> str:
        """Get SPICE-safe net name, caching the mapping."""
        if net_name not in self._net_name_map:
            self._net_name_map[net_name] = self._sanitize_net_name(net_name)
        return self._net_name_map[net_name]

    def compile(self) -> str:
        """Generates a SPICE netlist from Circuit IR."""
        lines = [
            f"* {self.circuit.name}",
            f"* Auto-generated from Circuit IR",
            "",
        ]

        # Component models and instances
        for ref, comp in self.circuit.components.items():
            spice_lines = self._component_to_spice(ref, comp)
            lines.extend(spice_lines)

        # Ground reference
        lines.append(".global GND")

        # Diode model definitions
        lines.extend([
            "",
            "* Diode Models",
            ".model 1N4148 D (IS=2.52e-9 RS=0.568 N=1.75 BV=100 IBV=5e-6 CJO=4pF VJ=0.7 M=0.333 TT=4nS)",
            ".model 1N4148W D (IS=2.52e-9 RS=0.568 N=1.75 BV=100 IBV=5e-6 CJO=4pF VJ=0.7 M=0.333 TT=4nS)",  # SOD-123 version
            ".model SS14 D (IS=3.2e-8 RS=0.035 N=1.1 BV=40 IBV=1e-3 CJO=110pF VJ=0.4 M=0.5 TT=0)",  # Schottky 1A/40V
            ".model SS34 D (IS=3.2e-8 RS=0.035 N=1.1 BV=40 IBV=1e-3 CJO=110pF VJ=0.4 M=0.5 TT=0)",  # Schottky 3A/40V
            ".model BAT54 D (IS=1.5e-7 RS=0.5 N=1.1 BV=30 IBV=1e-4 CJO=10pF VJ=0.5 M=0.33)",  # Schottky 0.2A/30V
            ".model 1N5819 D (IS=5e-7 RS=0.04 N=1.1 BV=40 IBV=1e-3 CJO=50pF VJ=0.5 M=0.33)",  # Schottky 1A/40V
        ])

        # Standard simulation commands - DC analysis only for now
        lines.extend([
            "",
            "* DC Operating Point Analysis",
            ".op",
            "",
            ".end",
        ])

        return "\n".join(lines)

    def _component_to_spice(self, ref: str, comp: Component) -> List[str]:
        lines = []

        def get_net(pin) -> str:
            return self._get_spice_net_name(pin.connected_net) if pin.connected_net else "NC"

        if comp.component_type == ComponentType.RESISTOR:
            lines.append(f"R{ref} {get_net(comp.pins[0])} {get_net(comp.pins[1])} {comp.value}")

        elif comp.component_type == ComponentType.CAPACITOR:
            lines.append(f"C{ref} {get_net(comp.pins[0])} {get_net(comp.pins[1])} {comp.value}")

        elif comp.component_type == ComponentType.INDUCTOR:
            lines.append(f"L{ref} {get_net(comp.pins[0])} {get_net(comp.pins[1])} {comp.value}")

        elif comp.component_type == ComponentType.DIODE:
            # Assume pin 1 = cathode, pin 2 = anode
            cathode = self._get_spice_net_name(comp.pins[0].connected_net) if comp.pins[0].name in ('K', 'CATHODE', '1') else self._get_spice_net_name(comp.pins[1].connected_net)
            anode = self._get_spice_net_name(comp.pins[1].connected_net) if comp.pins[1].name in ('A', 'ANODE', '2') else self._get_spice_net_name(comp.pins[0].connected_net)
            # Use MPN for diode model if available, otherwise default to 1N4148
            diode_model = comp.mpn if comp.mpn else "1N4148"
            lines.append(f"D{ref} {anode} {cathode} {diode_model}")

        elif comp.component_type == ComponentType.LED:
            # LED modeled as diode with forward voltage
            cathode = self._get_spice_net_name(comp.pins[0].connected_net) if comp.pins[0].name in ('K', 'CATHODE', '1') else self._get_spice_net_name(comp.pins[1].connected_net)
            anode = self._get_spice_net_name(comp.pins[1].connected_net) if comp.pins[1].name in ('A', 'ANODE', '2') else self._get_spice_net_name(comp.pins[0].connected_net)
            lines.append(f"D{ref} {anode} {cathode} DLED")
            lines.append(".model DLED D (IS=1e-15 N=1.5 RS=10 BV=5)")

        elif comp.component_type == ComponentType.REGULATOR_LDO:
            # Simplified LDO model: VIN, VOUT, GND
            vin = comp.get_pin("VI") or comp.get_pin("VIN") or comp.get_pin("3")
            vout = comp.get_pin("VO") or comp.get_pin("VOUT") or comp.get_pin("2")
            gnd = comp.get_pin("GND") or comp.get_pin("1")

            vin_net = self._get_spice_net_name(vin.connected_net) if vin else "VIN"
            vout_net = self._get_spice_net_name(vout.connected_net) if vout else "VOUT"
            gnd_net = self._get_spice_net_name(gnd.connected_net) if gnd else "GND"

            # Simple voltage source model for LDO output
            lines.append(f"V{ref}_OUT {vout_net} {gnd_net} DC {self._parse_voltage(comp.value)}")
            # Add input voltage source reference
            lines.append(f"V{ref}_IN {vin_net} {gnd_net} DC 5")

        elif comp.component_type == ComponentType.MICROCONTROLLER:
            # MCU as current load
            vdd = comp.get_pin("VDD") or comp.get_pin("VCC")
            vss = comp.get_pin("VSS") or comp.get_pin("GND")
            if vdd and vss:
                lines.append(f"I{ref}_LOAD {self._get_spice_net_name(vdd.connected_net)} {self._get_spice_net_name(vss.connected_net)} DC 0.05")  # 50mA load

        elif comp.component_type == ComponentType.VOLTAGE_SOURCE:
            # Explicit voltage source
            pos = comp.get_pin("POS") or comp.get_pin("P")
            neg = comp.get_pin("NEG") or comp.get_pin("N")
            if pos and neg:
                lines.append(f"V{ref} {self._get_spice_net_name(pos.connected_net)} {self._get_spice_net_name(neg.connected_net)} DC {comp.value}")

        # Passive components - use sanitized net names
        elif comp.component_type == ComponentType.RESISTOR:
            lines.append(f"R{ref} {get_net(comp.pins[0])} {get_net(comp.pins[1])} {comp.value}")

        elif comp.component_type == ComponentType.CAPACITOR:
            lines.append(f"C{ref} {get_net(comp.pins[0])} {get_net(comp.pins[1])} {comp.value}")

        elif comp.component_type == ComponentType.INDUCTOR:
            lines.append(f"L{ref} {get_net(comp.pins[0])} {get_net(comp.pins[1])} {comp.value}")

        elif comp.component_type == ComponentType.DIODE:
            # Assume pin 1 = cathode, pin 2 = anode
            cathode = self._get_spice_net_name(comp.pins[0].connected_net) if comp.pins[0].name in ('K', 'CATHODE', '1') else self._get_spice_net_name(comp.pins[1].connected_net)
            anode = self._get_spice_net_name(comp.pins[1].connected_net) if comp.pins[1].name in ('A', 'ANODE', '2') else self._get_spice_net_name(comp.pins[0].connected_net)
            # Use MPN for diode model if available, otherwise default to 1N4148
            diode_model = comp.mpn if comp.mpn else "1N4148"
            lines.append(f"D{ref} {anode} {cathode} {diode_model}")

        elif comp.component_type == ComponentType.LED:
            # LED modeled as diode with forward voltage
            cathode = self._get_spice_net_name(comp.pins[0].connected_net) if comp.pins[0].name in ('K', 'CATHODE', '1') else self._get_spice_net_name(comp.pins[1].connected_net)
            anode = self._get_spice_net_name(comp.pins[1].connected_net) if comp.pins[1].name in ('A', 'ANODE', '2') else self._get_spice_net_name(comp.pins[0].connected_net)
            lines.append(f"D{ref} {anode} {cathode} DLED")
            lines.append(".model DLED D (IS=1e-15 N=1.5 RS=10 BV=5)")

        else:
            # Generic component - create basic model
            lines.append(f"* Unknown component type: {comp.component_type} for {ref}")

        return lines

    def _parse_voltage(self, value: str) -> float:
        """Extract numeric voltage from value string like '3.3V'."""
        try:
            return float(value.replace('V', '').replace('v', ''))
        except ValueError:
            return 3.3


def parse_operating_point(stdout: str) -> Dict[str, Any]:
    """
    Extract DC node voltages from ngspice's operating-point table.

    ngspice prints one table per analysis, with a `device` header line followed
    by a row per node::

             device        vu1_in      vu1_out
              dc             5           3.3
              acmag          0            0

    The `dc` row holds the DC voltage of each node, which is what tells you
    whether a design actually regulates. Rows are kept only where the value
    parses as a number, so branch currents and `-` placeholders are ignored.
    """
    voltages: Dict[str, float] = {}
    header: Optional[List[str]] = None

    for line in stdout.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        parts = stripped.split()
        if not parts:
            continue

        if parts[0] == "device" and len(parts) > 1:
            header = parts[1:]
            continue

        # The DC row is the one we want; other rows (acmag, phase, ...) are not.
        if header and parts[0] == "dc" and len(parts) >= 2:
            for name, value in zip(header, parts[1:]):
                try:
                    voltages[name] = float(value)
                except ValueError:
                    continue
            header = None

    if not voltages:
        return {}
    return {
        "node_voltages": voltages,
        "min_voltage": min(voltages.values()),
        "max_voltage": max(voltages.values()),
    }


def simulate_circuit(circuit: CircuitIR, ngspice_path: str = "ngspice") -> SimulationResult:
    """
    High-level function to compile and simulate a circuit.
    """
    compiler = CircuitIRToSpice(circuit)
    netlist = compiler.compile()

    runner = NgSpiceRunner(ngspice_path)
    return runner.run_simulation(netlist)