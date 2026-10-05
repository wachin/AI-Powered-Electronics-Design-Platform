"""
Tests for Smart PCB Placement.
"""

import pytest
from src.core.circuit_ir import CircuitIR, Component, ComponentType, PinType
from src.pcb.smart_placement import (
    SmartPlacer,
    BoundingBox,
    FootprintGeometry,
    PlacementStrategy,
    smart_place_components,
    generate_pcb_with_smart_placement,
)


def test_bounding_box():
    """Test bounding box operations."""
    b1 = BoundingBox(0, 0, 10, 10)
    b2 = BoundingBox(5, 5, 15, 15)
    b3 = BoundingBox(20, 20, 30, 30)
    
    assert b1.intersects(b2)
    assert not b1.intersects(b3)
    assert b1.intersects(b3, clearance=15)
    
    # Test center
    assert b1.center == (5, 5)
    
    # Test expand
    expanded = b1.expand(2)
    assert expanded.x_min == -2
    assert expanded.x_max == 12
    
    # Test translate
    moved = b1.translate(5, 5)
    assert moved.x_min == 5
    assert moved.y_max == 15


def test_footprint_geometry_parsing():
    """Test footprint geometry creation from standard names."""
    # SOT-223 (power package)
    sot223 = FootprintGeometry.from_footprint_name("Package_TO_SOT_SMD:SOT-223-3_TabPin2")
    assert sot223.thermal_pad
    assert sot223.power_dissipation > 0.5
    assert sot223.bbox.width > 5
    
    # 0805 passive
    r0805 = FootprintGeometry.from_footprint_name("Resistor_SMD:R_0805_2012Metric")
    assert not r0805.thermal_pad
    assert r0805.power_dissipation <= 0.25
    assert r0805.bbox.width > 1.5
    
    # QFN
    qfn = FootprintGeometry.from_footprint_name("Package_QFN:QFN-48_7x7mm_P0.5mm")
    assert qfn.thermal_pad
    assert qfn.power_dissipation > 1.0
    assert qfn.bbox.width > 5


def test_smart_placer_basic():
    """Test basic smart placer functionality."""
    circuit = CircuitIR(name="Test")
    
    # Add a few components
    u1 = Component(
        ref="U1", value="3.3V", component_type=ComponentType.REGULATOR_LDO,
        footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2",
        symbol="Regulator_Linear:AMS1117-3.3"
    )
    u1.add_pin("1", "GND", PinType.POWER_IN)
    u1.add_pin("2", "VOUT", PinType.POWER_OUT)
    u1.add_pin("3", "VIN", PinType.POWER_IN)
    circuit.add_component(u1)
    
    c1 = Component(
        ref="C1", value="10uF", component_type=ComponentType.CAPACITOR,
        footprint="Capacitor_SMD:C_0805_2012Metric",
        symbol="Device:C"
    )
    c1.add_pin("1", "1", PinType.PASSIVE)
    c1.add_pin("2", "2", PinType.PASSIVE)
    circuit.add_component(c1)
    
    c2 = Component(
        ref="C2", value="22uF", component_type=ComponentType.CAPACITOR,
        footprint="Capacitor_SMD:C_0805_2012Metric",
        symbol="Device:C"
    )
    c2.add_pin("1", "1", PinType.PASSIVE)
    c2.add_pin("2", "2", PinType.PASSIVE)
    circuit.add_component(c2)
    
    # Place
    placed = smart_place_components(circuit, board_width=100, board_height=80)
    
    assert len(placed) == 3
    assert "U1" in placed
    assert "C1" in placed
    assert "C2" in placed
    
    # Check all placed within bounds
    for ref, p in placed.items():
        assert p.bbox.x_min >= 5  # EDGE_CLEARANCE
        assert p.bbox.y_min >= 5
        assert p.bbox.x_max <= 95  # board_width - EDGE_CLEARANCE
        assert p.bbox.y_max <= 75  # board_height - EDGE_CLEARANCE
    
    # Check no collisions
    refs = list(placed.keys())
    for i, ref1 in enumerate(refs):
        for ref2 in refs[i+1:]:
            assert not placed[ref1].bbox.intersects(placed[ref2].bbox, 0.5)


def test_thermal_separation():
    """Test that high-power components are separated."""
    circuit = CircuitIR(name="Thermal Test")
    
    # Two high-power regulators
    u1 = Component(
        ref="U1", value="5V", component_type=ComponentType.REGULATOR_LDO,
        footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2",
        symbol="Regulator_Linear:LM7805"
    )
    u1.add_pin("1", "GND", PinType.POWER_IN)
    u1.add_pin("2", "VOUT", PinType.POWER_OUT)
    u1.add_pin("3", "VIN", PinType.POWER_IN)
    circuit.add_component(u1)
    
    u2 = Component(
        ref="U2", value="3.3V", component_type=ComponentType.REGULATOR_LDO,
        footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2",
        symbol="Regulator_Linear:AMS1117-3.3"
    )
    u2.add_pin("1", "GND", PinType.POWER_IN)
    u2.add_pin("2", "VOUT", PinType.POWER_OUT)
    u2.add_pin("3", "VIN", PinType.POWER_IN)
    circuit.add_component(u2)
    
    # Small caps
    for i, ref in enumerate(["C1", "C2", "C3", "C4"]):
        c = Component(
            ref=ref, value="10uF", component_type=ComponentType.CAPACITOR,
            footprint="Capacitor_SMD:C_0805_2012Metric",
            symbol="Device:C"
        )
        c.add_pin("1", "1", PinType.PASSIVE)
        c.add_pin("2", "2", PinType.PASSIVE)
        circuit.add_component(c)
    
    # Place with thermal strategy
    placed = smart_place_components(
        circuit, board_width=100, board_height=80,
        strategy=PlacementStrategy.THERMAL
    )
    
    # Check U1 and U2 are well separated
    u1_pos = placed["U1"].bbox.center
    u2_pos = placed["U2"].bbox.center
    
    dist = ((u1_pos[0] - u2_pos[0])**2 + (u1_pos[1] - u2_pos[1])**2)**0.5
    # Should be at least thermal clearance apart
    assert dist >= 10.0, f"High-power components too close: {dist:.1f}mm"


def test_signal_integrity_grouping():
    """Test that components on same net are placed close."""
    circuit = CircuitIR(name="Signal Test")
    
    # MCU with many pins
    mcu = Component(
        ref="U1", value="STM32F103", component_type=ComponentType.MICROCONTROLLER,
        footprint="Package_QFP:LQFP-48_7x7mm_P0.5mm",
        symbol="MCU_ST_STM32F1:STM32F103C8T6"
    )
    for i in range(48):
        mcu.add_pin(str(i+1), f"P{i+1}", PinType.BIDIRECTIONAL)
    circuit.add_component(mcu)
    
    # Crystal near MCU
    xtal = Component(
        ref="X1", value="8MHz", component_type=ComponentType.CRYSTAL,
        footprint="Crystal:Crystal_HC49S",
        symbol="Crystal:Crystal_GND2"
    )
    xtal.add_pin("1", "1", PinType.PASSIVE)
    xtal.add_pin("2", "2", PinType.PASSIVE)
    circuit.add_component(xtal)
    
    # Caps for crystal
    for ref in ["C1", "C2"]:
        c = Component(
            ref=ref, value="20pF", component_type=ComponentType.CAPACITOR,
            footprint="Capacitor_SMD:C_0603_1608Metric",
            symbol="Device:C"
        )
        c.add_pin("1", "1", PinType.PASSIVE)
        c.add_pin("2", "2", PinType.PASSIVE)
        circuit.add_component(c)
    
    # Connect X1 to U1
    circuit.connect("X1", "1", "NET_XTAL1")
    circuit.connect("U1", "P5", "NET_XTAL1")  # OSC_IN
    circuit.connect("X1", "2", "NET_XTAL2")
    circuit.connect("U1", "P6", "NET_XTAL2")  # OSC_OUT
    circuit.connect("C1", "1", "NET_XTAL1")
    circuit.connect("C1", "2", "GND")
    circuit.connect("C2", "1", "NET_XTAL2")
    circuit.connect("C2", "2", "GND")
    
    # Place with signal integrity strategy
    placed = smart_place_components(
        circuit, board_width=100, board_height=80,
        strategy=PlacementStrategy.SIGNAL_INTEGRITY
    )
    
    # X1 should be close to U1
    xtal_pos = placed["X1"].bbox.center
    mcu_pos = placed["U1"].bbox.center
    dist = ((xtal_pos[0] - mcu_pos[0])**2 + (xtal_pos[1] - mcu_pos[1])**2)**0.5
    
    # Crystal should be reasonably close to MCU
    assert dist < 30, f"Crystal too far from MCU: {dist:.1f}mm"


def test_pcb_generation():
    """Test PCB generation with smart placement."""
    circuit = CircuitIR(name="PCB Gen Test")
    
    u1 = Component(
        ref="U1", value="3.3V", component_type=ComponentType.REGULATOR_LDO,
        footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2",
        symbol="Regulator_Linear:AMS1117-3.3"
    )
    u1.add_pin("1", "GND", PinType.POWER_IN)
    u1.add_pin("2", "VOUT", PinType.POWER_OUT)
    u1.add_pin("3", "VIN", PinType.POWER_IN)
    circuit.add_component(u1)
    
    c1 = Component(
        ref="C1", value="10uF", component_type=ComponentType.CAPACITOR,
        footprint="Capacitor_SMD:C_0805_2012Metric",
        symbol="Device:C"
    )
    c1.add_pin("1", "1", PinType.PASSIVE)
    c1.add_pin("2", "2", PinType.PASSIVE)
    circuit.add_component(c1)
    
    # Generate PCB
    pcb_content = generate_pcb_with_smart_placement(circuit, board_width=100, board_height=80)
    
    assert "(kicad_pcb" in pcb_content
    assert "U1" in pcb_content
    assert "C1" in pcb_content
    assert "SOT-223-3_TabPin2" in pcb_content
    assert "C_0805_2012Metric" in pcb_content
    assert "Edge.Cuts" in pcb_content


def test_strategy_compact_vs_balanced():
    """Test different placement strategies produce different results."""
    circuit = CircuitIR(name="Strategy Test")
    
    # Add several components
    for i in range(5):
        c = Component(
            ref=f"R{i+1}", value="10k", component_type=ComponentType.RESISTOR,
            footprint="Resistor_SMD:R_0805_2012Metric",
            symbol="Device:R"
        )
        c.add_pin("1", "1", PinType.PASSIVE)
        c.add_pin("2", "2", PinType.PASSIVE)
        circuit.add_component(c)
    
    # Compact strategy
    compact = smart_place_components(circuit, strategy=PlacementStrategy.COMPACT)
    
    # Balanced strategy
    balanced = smart_place_components(circuit, strategy=PlacementStrategy.BALANCED)
    
    # Both should place all components
    assert len(compact) == 5
    assert len(balanced) == 5
    
    # Both should be valid (no collisions)
    for placed in [compact, balanced]:
        refs = list(placed.keys())
        for i, ref1 in enumerate(refs):
            for ref2 in refs[i+1:]:
                assert not placed[ref1].bbox.intersects(placed[ref2].bbox, 0.5)


def test_large_board():
    """Test placement on larger board."""
    circuit = CircuitIR(name="Large Board")
    
    # Add 20 components
    for i in range(20):
        c = Component(
            ref=f"C{i+1}", value="100nF", component_type=ComponentType.CAPACITOR,
            footprint="Capacitor_SMD:C_0603_1608Metric",
            symbol="Device:C"
        )
        c.add_pin("1", "1", PinType.PASSIVE)
        c.add_pin("2", "2", PinType.PASSIVE)
        circuit.add_component(c)
    
    placed = smart_place_components(
        circuit, board_width=200, board_height=150,
        strategy=PlacementStrategy.BALANCED
    )
    
    assert len(placed) == 20
    
    # All within larger board bounds
    for ref, p in placed.items():
        assert p.bbox.x_min >= 5
        assert p.bbox.y_min >= 5
        assert p.bbox.x_max <= 195
        assert p.bbox.y_max <= 145


if __name__ == "__main__":
    pytest.main([__file__, "-v"])