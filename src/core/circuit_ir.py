"""
Core data structures for the Circuit Intermediate Representation (Circuit IR).

This layer acts as the single source of truth for all electronic designs.
It maps between natural language specifications, Circuit JSON, and KiCad models.
"""

from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Union
from enum import Enum
import uuid


class PinType(Enum):
    POWER_IN = "power_in"
    POWER_OUT = "power_out"
    PASSIVE = "passive"
    INPUT = "input"
    OUTPUT = "output"
    BIDIRECTIONAL = "bidirectional"
    UNSPECIFIED = "unspecified"


class ComponentType(Enum):
    RESISTOR = "resistor"
    CAPACITOR = "capacitor"
    INDUCTOR = "inductor"
    DIODE = "diode"
    LED = "led"
    TRANSISTOR = "transistor"
    MOSFET = "mosfet"
    OPAMP = "opamp"
    REGULATOR_LDO = "regulator_ldo"
    REGULATOR_BUCK = "regulator_buck"
    REGULATOR_BOOST = "regulator_boost"
    MICROCONTROLLER = "microcontroller"
    CONNECTOR = "connector"
    CHIP = "chip"
    SWITCH = "switch"
    CRYSTAL = "crystal"
    TESTPOINT = "testpoint"
    CUSTOM = "custom"


@dataclass
class Point2D:
    x: float
    y: float

    def to_dict(self) -> Dict[str, float]:
        return {"x": self.x, "y": self.y}


@dataclass
class Pin:
    """Represents a component pin/port."""
    number: str
    name: str
    pin_type: PinType = PinType.UNSPECIFIED
    connected_net: Optional[str] = None
    position: Optional[Point2D] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "number": self.number,
            "name": self.name,
            "pin_type": self.pin_type.value,
            "connected_net": self.connected_net,
            "position": self.position.to_dict() if self.position else None
        }


@dataclass
class Component:
    """Represents an electronic component in the Circuit IR."""
    ref: str
    value: str
    component_type: ComponentType
    footprint: str
    symbol: str
    mpn: Optional[str] = None
    manufacturer: Optional[str] = None
    description: Optional[str] = None
    pins: List[Pin] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)
    position: Optional[Point2D] = None
    rotation: float = 0.0

    def add_pin(self, number: str, name: str, pin_type: PinType = PinType.UNSPECIFIED) -> Pin:
        pin = Pin(number=number, name=name, pin_type=pin_type)
        self.pins.append(pin)
        return pin

    def get_pin(self, name_or_num: str) -> Optional[Pin]:
        for p in self.pins:
            if p.name == name_or_num or p.number == name_or_num:
                return p
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ref": self.ref,
            "value": self.value,
            "component_type": self.component_type.value,
            "footprint": self.footprint,
            "symbol": self.symbol,
            "mpn": self.mpn,
            "manufacturer": self.manufacturer,
            "description": self.description,
            "pins": [p.to_dict() for p in self.pins],
            "attributes": self.attributes,
            "position": self.position.to_dict() if self.position else None,
            "rotation": self.rotation
        }


@dataclass
class Net:
    """Represents a net (electrical connection) in the circuit."""
    name: str
    is_power: bool = False
    voltage: Optional[float] = None
    connected_pins: List[Dict[str, str]] = field(default_factory=list)  # [{"ref": "U1", "pin": "1"}]

    def connect(self, component_ref: str, pin_name_or_num: str):
        self.connected_pins.append({"ref": component_ref, "pin": pin_name_or_num})

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "is_power": self.is_power,
            "voltage": self.voltage,
            "connected_pins": self.connected_pins
        }


@dataclass
class PowerDomain:
    name: str
    voltage: float
    max_current_ma: float
    ground_net: str = "GND"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "voltage": self.voltage,
            "max_current_ma": self.max_current_ma,
            "ground_net": self.ground_net
        }


@dataclass
class Constraint:
    target_ref: str
    rule_type: str  # "max_voltage", "decoupling_required", "pullup_required", "diff_pair"
    parameters: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "target_ref": self.target_ref,
            "rule_type": self.rule_type,
            "parameters": self.parameters
        }


@dataclass
class CircuitIR:
    """
    The Canonical Circuit Intermediate Representation.
    
    Acts as the single source of truth for:
    1. AI natural language understanding
    2. Circuit JSON emission
    3. KiCad direct compiler
    4. Deterministic ERC/DRC validation
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Untitled Circuit"
    description: str = ""
    components: Dict[str, Component] = field(default_factory=dict)
    nets: Dict[str, Net] = field(default_factory=dict)
    power_domains: Dict[str, PowerDomain] = field(default_factory=dict)
    constraints: List[Constraint] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_component(self, component: Component) -> Component:
        self.components[component.ref] = component
        return component

    def get_or_create_net(self, name: str, is_power: bool = False, voltage: Optional[float] = None) -> Net:
        if name not in self.nets:
            self.nets[name] = Net(name=name, is_power=is_power, voltage=voltage)
        return self.nets[name]

    def connect(self, comp_ref: str, pin: str, net_name: str):
        if comp_ref not in self.components:
            raise ValueError(f"Component {comp_ref} not found in circuit")
        
        net = self.get_or_create_net(net_name)
        net.connect(comp_ref, pin)
        
        c = self.components[comp_ref]
        p = c.get_pin(pin)
        if p:
            p.connected_net = net_name

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "components": {k: v.to_dict() for k, v in self.components.items()},
            "nets": {k: v.to_dict() for k, v in self.nets.items()},
            "power_domains": {k: v.to_dict() for k, v in self.power_domains.items()},
            "constraints": [c.to_dict() for c in self.constraints],
            "metadata": self.metadata
        }

    def to_circuit_json_compatible(self) -> List[Dict[str, Any]]:
        """
        Converts the canonical Circuit IR into standard Circuit JSON elements.
        """
        elements: List[Dict[str, Any]] = []

        # Project metadata
        elements.append({
            "type": "source_project_metadata",
            "name": self.name,
            "description": self.description
        })

        # Convert Components
        for ref, comp in self.components.items():
            elem: Dict[str, Any] = {
                "type": "source_component",
                "source_component_id": ref,
                "name": ref,
                "ftype": "simple_chip",
                "supplier_part_numbers": {}
            }
            if comp.mpn:
                elem["supplier_part_numbers"]["jlcpcb"] = [comp.mpn]
            elements.append(elem)

        # Convert Nets
        for net_name, net in self.nets.items():
            elements.append({
                "type": "source_net",
                "source_net_id": net_name,
                "name": net_name,
                "is_power": net.is_power
            })

        return elements
