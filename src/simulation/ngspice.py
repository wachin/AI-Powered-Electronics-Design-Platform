"""
SPICE Simulation Integration for AI-Powered Electronics Design Platform.

Compiles CircuitIR to SPICE netlists and runs ngspice for circuit verification.
"""

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

            return SimulationResult(
                success=(result.returncode == 0),
                stdout=result.stdout,
                stderr=result.stderr,
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

        # Standard simulation commands
        lines.extend([
            "",
            "* DC Operating Point Analysis",
            ".op",
            "",
            "* Transient Analysis (1ms)",
            ".tran 1u 1m",
            "",
            "* DC Sweep for regulators",
            ".dc VIN 0 10 0.1",
            "",
            ".end",
        ])

        return "\n".join(lines)

    def _component_to_spice(self, ref: str, comp: Component) -> List[str]:
        lines = []

        if comp.component_type == ComponentType.RESISTOR:
            lines.append(f"R{ref} {comp.pins[0].connected_net or 'N001'} {comp.pins[1].connected_net or 'N002'} {comp.value}")

        elif comp.component_type == ComponentType.CAPACITOR:
            lines.append(f"C{ref} {comp.pins[0].connected_net or 'N001'} {comp.pins[1].connected_net or 'N002'} {comp.value}")

        elif comp.component_type == ComponentType.INDUCTOR:
            lines.append(f"L{ref} {comp.pins[0].connected_net or 'N001'} {comp.pins[1].connected_net or 'N002'} {comp.value}")

        elif comp.component_type == ComponentType.DIODE:
            # Assume pin 1 = cathode, pin 2 = anode
            cathode = comp.pins[0].connected_net if comp.pins[0].name in ('K', 'CATHODE', '1') else comp.pins[1].connected_net
            anode = comp.pins[1].connected_net if comp.pins[1].name in ('A', 'ANODE', '2') else comp.pins[0].connected_net
            lines.append(f"D{ref} {anode} {cathode} 1N4148")

        elif comp.component_type == ComponentType.LED:
            # LED modeled as diode with forward voltage
            cathode = comp.pins[0].connected_net if comp.pins[0].name in ('K', 'CATHODE', '1') else comp.pins[1].connected_net
            anode = comp.pins[1].connected_net if comp.pins[1].name in ('A', 'ANODE', '2') else comp.pins[0].connected_net
            lines.append(f"D{ref} {anode} {cathode} DLED")
            lines.append(".model DLED D (IS=1e-15 N=1.5 RS=10 VBR=5)")

        elif comp.component_type == ComponentType.REGULATOR_LDO:
            # Simplified LDO model: VIN, VOUT, GND
            vin = comp.get_pin("VI") or comp.get_pin("VIN") or comp.get_pin("3")
            vout = comp.get_pin("VO") or comp.get_pin("VOUT") or comp.get_pin("2")
            gnd = comp.get_pin("GND") or comp.get_pin("1")

            vin_net = vin.connected_net if vin else "VIN"
            vout_net = vout.connected_net if vout else "VOUT"
            gnd_net = gnd.connected_net if gnd else "GND"

            # Simple voltage source model for LDO output
            lines.append(f"V{ref}_OUT {vout_net} {gnd_net} DC {self._parse_voltage(comp.value)}")
            # Add input voltage source reference
            lines.append(f"V{ref}_IN {vin_net} {gnd_net} DC 5")

        elif comp.component_type == ComponentType.MICROCONTROLLER:
            # MCU as current load
            vdd = comp.get_pin("VDD") or comp.get_pin("VCC")
            vss = comp.get_pin("VSS") or comp.get_pin("GND")
            if vdd and vss:
                lines.append(f"I{ref}_LOAD {vdd.connected_net} {vss.connected_net} DC 0.05")  # 50mA load

        elif comp.component_type == ComponentType.VOLTAGE_SOURCE:
            # Explicit voltage source
            pos = comp.get_pin("POS") or comp.get_pin("P")
            neg = comp.get_pin("NEG") or comp.get_pin("N")
            if pos and neg:
                lines.append(f"V{ref} {pos.connected_net} {neg.connected_net} DC {comp.value}")

        return lines

    def _parse_voltage(self, value: str) -> float:
        """Extract numeric voltage from value string like '3.3V'."""
        try:
            return float(value.replace('V', '').replace('v', ''))
        except ValueError:
            return 3.3


def simulate_circuit(circuit: CircuitIR, ngspice_path: str = "ngspice") -> SimulationResult:
    """
    High-level function to compile and simulate a circuit.
    """
    compiler = CircuitIRToSpice(circuit)
    netlist = compiler.compile()

    runner = NgSpiceRunner(ngspice_path)
    return runner.run_simulation(netlist)