#!/usr/bin/env python3
"""
Acceptance check: does the generated KiCad schematic actually contain a netlist?

This is the test the project was missing. It builds a small circuit, writes the
schematic, and asks kicad-cli to extract the netlist. A schematic that opens but
has no connectivity reports `(nets)` empty, which this script treats as failure.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from src.core.circuit_ir import CircuitIR, Component, ComponentType, PinType
from src.generators.kicad_generator import KiCadGenerator

SPEC = [
    ("U1", "AMS1117-3.3", "Regulator_Linear:AMS1117-3.3",
     "Package_TO_SOT_SMD:SOT-223-3_TabPin2",
     [("1", "GND", PinType.POWER_IN), ("2", "VO", PinType.POWER_OUT), ("3", "VI", PinType.POWER_IN)]),
    ("C1", "CC0805KRX7R9BB106", "Device:C", "Capacitor_SMD:C_0805_2012Metric",
     [("1", "1", PinType.PASSIVE), ("2", "2", PinType.PASSIVE)]),
    ("C2", "CC0805KRX5R7BB226", "Device:C", "Capacitor_SMD:C_0805_2012Metric",
     [("1", "1", PinType.PASSIVE), ("2", "2", PinType.PASSIVE)]),
    ("D1", "LTST-C190KGKT", "Device:LED", "LED_SMD:LED_0805_2012Metric",
     [("1", "K", PinType.PASSIVE), ("2", "A", PinType.PASSIVE)]),
    ("R1", "RC0805FR-07330RL", "Device:R", "Resistor_SMD:R_0805_2012Metric",
     [("1", "1", PinType.PASSIVE), ("2", "2", PinType.PASSIVE)]),
]

CONNECTIONS = [
    ("U1", "3", "VIN"), ("U1", "2", "VOUT"), ("U1", "1", "GND"),
    ("C1", "1", "VIN"), ("C1", "2", "GND"),
    ("C2", "1", "VOUT"), ("C2", "2", "GND"),
    ("R1", "1", "VOUT"), ("R1", "2", "LED_A"),
    ("D1", "2", "LED_A"), ("D1", "1", "GND"),
]


def build_circuit() -> CircuitIR:
    circuit = CircuitIR(name="probe_circuit")
    for ref, mpn, symbol, footprint, pins in SPEC:
        component = Component(
            ref=ref, value=mpn, component_type=ComponentType.CUSTOM,
            footprint=footprint, symbol=symbol, mpn=mpn,
        )
        for number, name, pin_type in pins:
            component.add_pin(number, name, pin_type)
        circuit.add_component(component)
    for ref, pin, net in CONNECTIONS:
        circuit.connect(ref, pin, net)
    return circuit


def main() -> int:
    out = Path("output_design/netlist_check")
    out.mkdir(parents=True, exist_ok=True)
    files = KiCadGenerator(build_circuit()).export_project(out, "probe")
    sch = files["sch"]
    net = out / "probe.net"

    result = subprocess.run(
        ["kicad-cli", "sch", "export", "netlist", "--output", str(net), str(sch)],
        capture_output=True, text=True,
    )
    print("kicad-cli returncode:", result.returncode)
    for stream in (result.stdout, result.stderr):
        if stream.strip():
            print(stream.strip()[:1500])
    if not net.exists():
        print("FAIL: no netlist produced")
        return 1

    content = net.read_text()
    nets_section = content[content.index("(nets"):] if "(nets" in content else ""
    print(nets_section[:1500])

    expected = {"VIN", "VOUT", "GND", "LED_A"}
    found = {n for n in expected if f'name "/{n}"' in content}
    missing = expected - found
    if missing:
        print(f"FAIL: missing nets {sorted(missing)}")
        return 1
    if "(nets))" in content.replace(" ", "") or nets_section.strip() in ("(nets))", "(nets)"):
        print("FAIL: netlist is empty")
        return 1
    print(f"PASS: netlist contains {sorted(found)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
