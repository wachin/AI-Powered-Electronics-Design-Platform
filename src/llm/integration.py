"""
LLM Integration for AI-Powered Electronics Design Platform.

Provides natural language to CircuitIR conversion using LLM providers.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Union
from pathlib import Path
from src.llm.providers import (
    LLMProvider,
    create_llm_client,
    LLMClient,
    LLMProvider,
    LLMMessage,
    MockLLMClient,
)
from src.core.circuit_ir import CircuitIR, Component, ComponentType, PinType, PowerDomain
from src.components.database import ComponentDatabase

logger = logging.getLogger(__name__)


@dataclass
class ComponentSpec:
    """Component specification with attribute access."""
    role: str
    mpn: str
    manufacturer: str
    value: str
    package: str
    reasoning: str = ""

    def __getitem__(self, key: str) -> Any:
        """Allow dictionary-style access for backward compatibility."""
        return getattr(self, key)

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)

    def get(self, key: str, default=None) -> Any:
        return getattr(self, key, default)

    def __iter__(self):
        yield "role"
        yield "mpn"
        yield "manufacturer"
        yield "value"
        yield "package"
        yield "reasoning"

    def keys(self):
        return ["role", "mpn", "manufacturer", "value", "package", "reasoning"]

    def values(self):
        return [self.role, self.mpn, self.manufacturer, self.value, self.package, self.reasoning]

    def items(self):
        return [
            ("role", self.role),
            ("mpn", self.mpn),
            ("manufacturer", self.manufacturer),
            ("value", self.value),
            ("package", self.package),
            ("reasoning", self.reasoning),
        ]

    def __iter__(self):
        return iter(self.keys())

    def keys(self):
        return self.keys()

    def __contains__(self, key):
        return key in ["role", "mpn", "manufacturer", "value", "package", "reasoning"]


@dataclass
class CircuitRequirement:
    """Structured circuit requirements parsed from natural language."""
    circuit_type: str
    description: str
    input_voltage: Optional[float] = None
    output_voltage: Optional[float] = None
    output_current: Optional[float] = None
    features: List[str] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)

    # Backward compatibility property
    @property
    def current(self) -> Optional[float]:
        """Backward compatibility property."""
        return self.output_current
    
    @current.setter
    def current(self, value: Optional[float]) -> None:
        self.output_current = value


@dataclass
class CircuitSpecification:
    """Complete circuit specification ready for CircuitIR generation."""
    requirements: CircuitRequirement
    topology: str
    components: List[ComponentSpec] = field(default_factory=list)
    connections: List[Dict[str, str]] = field(default_factory=list)
    power_domains: Dict[str, Dict[str, float]] = field(default_factory=dict)
    design_notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)

    def __post_init__(self):
        # Convert any dict components to ComponentSpec objects
        converted_components = []
        for comp in self.components:
            if isinstance(comp, dict):
                # Convert dict to ComponentSpec
                converted = ComponentSpec(
                    role=comp.get("role", ""),
                    mpn=comp.get("mpn", ""),
                    manufacturer=comp.get("manufacturer", ""),
                    value=comp.get("value", ""),
                    package=comp.get("package", ""),
                    reasoning=comp.get("reasoning", "")
                )
                converted_components.append(converted)
            else:
                converted_components.append(comp)
        self.components = converted_components


class RequirementParser:
    """Parses natural language requirements into structured CircuitRequirement."""

    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client

    # JSON Schema for requirement parsing
    REQUIREMENT_SCHEMA = {
        "type": "object",
        "properties": {
            "circuit_type": {
                "type": "string",
                "enum": ["ldo_regulator", "buck_converter", "boost_converter", "led_driver", "mcu_board", "generic"]
            },
            "description": {"type": "string"},
            "input_voltage": {"type": ["number", "null"]},
            "output_voltage": {"type": ["number", "null"]},
            "output_current": {"type": ["number", "null"]},
            "features": {"type": "array", "items": {"type": "string"}},
            "constraints": {"type": "object"},
        },
        "required": ["circuit_type", "description"]
    }

    # Few-shot examples for requirement parsing
    PARSE_EXAMPLES = [
        {
            "input": "Design a 5V to 3.3V LDO regulator circuit with 500mA output current and LED power indicator",
            "output": {
                "circuit_type": "ldo_regulator",
                "description": "5V to 3.3V LDO regulator with LED indicator",
                "input_voltage": 5.0,
                "output_voltage": 3.3,
                "output_current": 0.5,
                "features": ["led_indicator"],
                "constraints": {}
            }
        },
        {
            "input": "I need a buck converter that steps down 12V to 5V at 3A for a Raspberry Pi",
            "output": {
                "circuit_type": "buck_converter",
                "description": "12V to 5V buck converter for Raspberry Pi",
                "input_voltage": 12.0,
                "output_voltage": 5.0,
                "output_current": 3.0,
                "features": [],
                "constraints": {"application": "raspberry_pi"}
            }
        },
        {
            "input": "Create a boost converter from 3.3V to 5V at 1A for USB charging",
            "output": {
                "circuit_type": "boost_converter",
                "description": "3.3V to 5V boost converter for USB charging",
                "input_voltage": 3.3,
                "output_voltage": 5.0,
                "output_current": 1.0,
                "features": ["usb_charging"],
                "constraints": {}
            }
        },
        {
            "input": "Simple LED driver circuit with 5V input and 20mA current limit",
            "output": {
                "circuit_type": "led_driver",
                "description": "5V LED driver with 20mA current limit",
                "input_voltage": 5.0,
                "output_voltage": None,
                "output_current": 0.02,
                "features": [],
                "constraints": {"current_limit": 0.02}
            }
        },
        {
            "input": "Design a stereo phono preamp for a turntable with moving magnet cartridge, RIAA equalization, RCA inputs and outputs, powered by 9V battery or 12V DC adapter",
            "output": {
                "circuit_type": "phono_preamp",
                "description": "Stereo phono preamp for MM cartridge with RIAA equalization",
                "input_voltage": 12.0,
                "output_voltage": None,
                "output_current": None,
                "features": ["stereo", "riaa_equalization", "moving_magnet_cartridge", "rca_io", "battery_power"],
                "constraints": {"power_supply": "9V_battery_or_12V_dc", "gain_db": 40, "input_impedance": "47k", "low_noise": True}
            }
        }
    ]

    async def parse(self, natural_language: str) -> CircuitRequirement:
        """Parse natural language into structured circuit requirements."""
        # Build few-shot examples
        examples_text = "\n\n".join([
            f"Input: {ex['input']}\nOutput: {json.dumps(ex['output'])}"
            for ex in self.PARSE_EXAMPLES
        ])
        
        system_prompt = f"""You are an expert electronics engineer. Parse the user's natural language description into structured circuit requirements.
        
        Extract the following information:
        - circuit_type: One of [ldo_regulator, buck_converter, boost_converter, led_driver, mcu_board, generic]
        - input_voltage: Input voltage in volts (if specified)
        - output_voltage: Output voltage in volts (if specified)  
        - output_current: Output current in amps (if specified)
        - features: List of features mentioned (e.g., ["led_indicator", "enable_pin", "soft_start"])
        - constraints: Any additional constraints (size, cost, temperature, etc.)
        
        If a value is not mentioned, use null.
        Be precise and only extract what is explicitly stated or strongly implied.
        
        Examples:
        {examples_text}"""

        prompt = f"Parse this circuit description: {natural_language}"

        try:
            result = await self.llm.complete_structured(
                messages=[
                    LLMMessage(role="system", content=system_prompt),
                    LLMMessage(role="user", content=prompt),
                ],
                response_schema={
                    "type": "object",
                    "properties": {
                        "circuit_type": {"type": "string", "enum": ["ldo_regulator", "buck_converter", "boost_converter", "led_driver", "mcu_board", "phono_preamp", "generic"]},
                        "description": {"type": "string"},
                        "input_voltage": {"type": ["number", "null"]},
                        "output_voltage": {"type": ["number", "null"]},
                        "output_current": {"type": ["number", "null"]},
                        "features": {"type": "array", "items": {"type": "string"}},
                        "constraints": {"type": "object"},
                    },
                    "required": ["circuit_type", "description"]
                }
            )
            return CircuitRequirement(**result)
        except Exception as e:
            logger.warning(f"LLM parsing failed, using fallback: {e}")
            return self._fallback_parse(natural_language)

    def _fallback_parse(self, text: str) -> CircuitRequirement:
        """Simple keyword-based fallback parser."""
        text_lower = text.lower()
        
        circuit_type = "generic"
        if any(k in text_lower for k in ["ldo", "linear regulator"]):
            circuit_type = "ldo_regulator"
        elif "buck" in text_lower or "step-down" in text_lower:
            circuit_type = "buck_converter"
        elif "boost" in text_lower or "step-up" in text_lower:
            circuit_type = "boost_converter"
        elif "led" in text_lower and "driver" in text_lower:
            circuit_type = "led_driver"
        
        # Extract voltages
        import re
        v_in = None
        v_out = None
        current = None
        
        for pattern, var in [(r'(\d+(?:\.\d+)?)\s*v\s*(?:to|->|→)\s*(\d+(?:\.\d+)?)', 'both'),
                             (r'(\d+(?:\.\d+)?)\s*v\s*(?:in|input)', 'in'),
                             (r'(\d+(?:\.\d+)?)\s*v\s*(?:out|output)', 'out')]:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                if var == 'both':
                    v_in, v_out = match.groups()
                    break
        
        return CircuitRequirement(
            circuit_type=circuit_type,
            description="",
            input_voltage=v_in,
            output_voltage=v_out,
            output_current=current,
        )


class CircuitSpecificationGenerator:
    """Generates detailed circuit specification from requirements."""
    
    def __init__(self, llm_client: LLMClient, component_db=None, use_llm: bool = True):
        self.llm = llm_client
        self.db = component_db
        self.use_llm = use_llm

    def _make_component(self, role: str, mpn: str, manufacturer: str, value: str, 
                        package: str, reasoning: str = "") -> ComponentSpec:
        """Create a ComponentSpec object."""
        return ComponentSpec(
            role=role,
            mpn=mpn,
            manufacturer=manufacturer,
            value=value,
            package=package,
            reasoning=reasoning
        )

    # Few-shot examples for specification generation
    SPEC_EXAMPLES = {
        "ldo_regulator": {
            "topology": "LDO Linear Regulator",
            "components": [
                {"role": "regulator", "mpn": "AMS1117-3.3", "manufacturer": "AMS", "value": "3.3V", "package": "SOT-223", "reasoning": "LDO regulator 5V to 3.3V, 1A"},
                {"role": "input_capacitor", "mpn": "CC0805KRX7R9BB106", "manufacturer": "Yageo", "value": "10uF", "package": "0805", "reasoning": "Input decoupling capacitor"},
                {"role": "output_capacitor", "mpn": "CC0805KRX7R9BB106", "manufacturer": "Yageo", "value": "10uF", "package": "0805", "reasoning": "Output stability capacitor"},
                {"role": "led_indicator", "mpn": "LTST-C190KGKT", "manufacturer": "Lite-On", "value": "Green", "package": "0805", "reasoning": "Power-on indicator LED"},
                {"role": "led_resistor", "mpn": "RC0805FR-0710KL", "manufacturer": "Yageo", "value": "10k", "package": "0805", "reasoning": "LED current limiting resistor"}
            ],
            "connections": [
                {"from": "U1", "to": "C1", "net": "VIN"},
                {"from": "C1", "to": "GND", "net": "GND"},
                {"from": "U1", "to": "C2", "net": "VOUT"},
                {"from": "C2", "to": "GND", "net": "GND"},
                {"from": "U1", "to": "R1", "net": "VOUT"},
                {"from": "R1", "to": "D1", "net": "D1_A"},
                {"from": "D1", "to": "GND", "net": "GND"}
            ],
            "power_domains": {"VIN": 5.0, "VOUT": 3.3, "GND": 0.0},
            "design_notes": ["LDO dropout: 1.7V", "Power dissipation: 0.85W", "Ensure adequate thermal relief"],
            "warnings": ["Check thermal dissipation for high current", "Verify dropout voltage at max current"]
        },
        "buck_converter": {
            "topology": "Asynchronous Buck Converter",
            "components": [
                {"role": "controller", "mpn": "LM2596S-5.0", "manufacturer": "TI", "value": "5V", "package": "TO-220-5", "reasoning": "Buck converter controller"},
                {"role": "inductor", "mpn": "SRR1280-470M", "manufacturer": "Bourns", "value": "47uH", "package": "12x12mm", "reasoning": "Buck inductor"},
                {"role": "input_capacitor", "mpn": "C-10uF-0805", "manufacturer": "Yageo", "value": "10uF", "package": "0805", "reasoning": "Input decoupling"},
                {"role": "output_capacitor", "mpn": "C-100uF-1206", "manufacturer": "Yageo", "value": "100uF", "package": "1206", "reasoning": "Output filtering"},
                {"role": "freewheel_diode", "mpn": "SS34", "manufacturer": "Vishay", "value": "3A/40V", "package": "SMA", "reasoning": "Freewheeling diode"}
            ],
            "connections": [
                {"from": "U1", "to": "L1", "net": "SW"},
                {"from": "L1", "to": "D1", "net": "SW"},
                {"from": "L1", "to": "C2", "net": "VOUT"},
                {"from": "C1", "to": "U1", "net": "VIN"}
            ],
            "power_domains": {"VIN": 12.0, "VOUT": 5.0, "GND": 0.0},
            "design_notes": ["Asynchronous buck converter", "Consider sync rectification for >90% efficiency"],
            "warnings": ["Diode loss significant at high current"]
        },
        "led_driver": {
            "topology": "Series Resistor LED Driver",
            "components": [
                {"role": "led", "mpn": "LTST-C190KGKT", "manufacturer": "Lite-On", "value": "Green", "package": "0805", "reasoning": "Green indicator LED"},
                {"role": "current_limit_resistor", "mpn": "RC0805FR-071K5L", "manufacturer": "Yageo", "value": "1.5k", "package": "0805", "reasoning": "Current limiting resistor for 20mA"}
            ],
            "connections": [
                {"from": "VIN", "to": "R1", "net": "VIN"},
                {"from": "R1", "to": "D1", "net": "D1_A"},
                {"from": "D1", "to": "GND", "net": "GND"}
            ],
            "power_domains": {"VIN": 5.0, "GND": 0.0},
            "design_notes": ["Simple series resistor drive", "Resistor value: (5V - 2.1V) / 0.02A = 145 ohm, use 1.5k for lower brightness"],
            "warnings": ["Resistor dissipates power: I^2*R = 4mW", "LED forward voltage varies by color"]
        },
        "phono_preamp": {
            "topology": "Stereo RIAA Phono Preamplifier (Moving Magnet)",
            "components": [
                # Left Channel
                {"role": "input_jack_left", "mpn": "RCA-2P", "manufacturer": "CUI Devices", "value": "RCA Jack", "package": "PTH", "reasoning": "Left channel RCA input"},
                {"role": "input_capacitor_left", "mpn": "C0603C104K5RAC", "manufacturer": "KEMET", "value": "100nF", "package": "0603", "reasoning": "DC blocking capacitor, left input"},
                {"role": "input_resistor_left", "mpn": "RC0603FR-0747KL", "manufacturer": "Yageo", "value": "47k", "package": "0603", "reasoning": "Cartridge loading 47k ohm (MM standard)"},
                {"role": "opamp_left_1", "mpn": "OPA2134PA", "manufacturer": "TI", "value": "Dual FET OpAmp", "package": "DIP-8", "reasoning": "Low noise, low distortion audio opamp, first gain stage"},
                {"role": "riaa_r1_left", "mpn": "RC0603FR-073K3L", "manufacturer": "Yageo", "value": "3.3k", "package": "0603", "reasoning": "RIAA network R1 (3180µs pole)"},
                {"role": "riaa_c1_left", "mpn": "C0603C104K5RAC", "manufacturer": "KEMET", "value": "100nF", "package": "0603", "reasoning": "RIAA network C1 (3180µs pole)"},
                {"role": "riaa_r2_left", "mpn": "RC0603FR-07750RL", "manufacturer": "Yageo", "value": "750", "package": "0603", "reasoning": "RIAA network R2 (318µs zero)"},
                {"role": "riaa_c2_left", "mpn": "C0603C473K5RAC", "manufacturer": "KEMET", "value": "47nF", "package": "0603", "reasoning": "RIAA network C2 (318µs zero)"},
                {"role": "riaa_r3_left", "mpn": "RC0603FR-071K2L", "manufacturer": "Yageo", "value": "1.2k", "package": "0603", "reasoning": "RIAA network R3 (75µs pole)"},
                {"role": "riaa_c3_left", "mpn": "C0603C223K5RAC", "manufacturer": "KEMET", "value": "22nF", "package": "0603", "reasoning": "RIAA network C3 (75µs pole)"},
                {"role": "gain_r_left", "mpn": "RC0603FR-0710KL", "manufacturer": "Yageo", "value": "10k", "package": "0603", "reasoning": "Gain setting resistor (~40dB)"},
                {"role": "gain_rf_left", "mpn": "RC0603FR-071ML", "manufacturer": "Yageo", "value": "1M", "package": "0603", "reasoning": "Feedback resistor for gain"},
                {"role": "output_capacitor_left", "mpn": "C0603C105K5RAC", "manufacturer": "KEMET", "value": "1uF", "package": "0603", "reasoning": "DC blocking output capacitor"},
                {"role": "output_jack_left", "mpn": "RCA-2P", "manufacturer": "CUI Devices", "value": "RCA Jack", "package": "PTH", "reasoning": "Left channel RCA output to guitar amp"},
                
                # Right Channel (mirror of left)
                {"role": "input_jack_right", "mpn": "RCA-2P", "manufacturer": "CUI Devices", "value": "RCA Jack", "package": "PTH", "reasoning": "Right channel RCA input"},
                {"role": "input_capacitor_right", "mpn": "C0603C104K5RAC", "manufacturer": "KEMET", "value": "100nF", "package": "0603", "reasoning": "DC blocking capacitor, right input"},
                {"role": "input_resistor_right", "mpn": "RC0603FR-0747KL", "manufacturer": "Yageo", "value": "47k", "package": "0603", "reasoning": "Cartridge loading 47k ohm (MM standard)"},
                {"role": "opamp_right_1", "mpn": "OPA2134PA", "manufacturer": "TI", "value": "Dual FET OpAmp", "package": "DIP-8", "reasoning": "Low noise, low distortion audio opamp, first gain stage (shared dual)"},
                {"role": "riaa_r1_right", "mpn": "RC0603FR-073K3L", "manufacturer": "Yageo", "value": "3.3k", "package": "0603", "reasoning": "RIAA network R1"},
                {"role": "riaa_c1_right", "mpn": "C0603C104K5RAC", "manufacturer": "KEMET", "value": "100nF", "package": "0603", "reasoning": "RIAA network C1"},
                {"role": "riaa_r2_right", "mpn": "RC0603FR-07750RL", "manufacturer": "Yageo", "value": "750", "package": "0603", "reasoning": "RIAA network R2"},
                {"role": "riaa_c2_right", "mpn": "C0603C473K5RAC", "manufacturer": "KEMET", "value": "47nF", "package": "0603", "reasoning": "RIAA network C2"},
                {"role": "riaa_r3_right", "mpn": "RC0603FR-071K2L", "manufacturer": "Yageo", "value": "1.2k", "package": "0603", "reasoning": "RIAA network R3"},
                {"role": "riaa_c3_right", "mpn": "C0603C223K5RAC", "manufacturer": "KEMET", "value": "22nF", "package": "0603", "reasoning": "RIAA network C3"},
                {"role": "gain_r_right", "mpn": "RC0603FR-0710KL", "manufacturer": "Yageo", "value": "10k", "package": "0603", "reasoning": "Gain setting resistor"},
                {"role": "gain_rf_right", "mpn": "RC0603FR-071ML", "manufacturer": "Yageo", "value": "1M", "package": "0603", "reasoning": "Feedback resistor for gain"},
                {"role": "output_capacitor_right", "mpn": "C0603C105K5RAC", "manufacturer": "KEMET", "value": "1uF", "package": "0603", "reasoning": "DC blocking output capacitor"},
                {"role": "output_jack_right", "mpn": "RCA-2P", "manufacturer": "CUI Devices", "value": "RCA Jack", "package": "PTH", "reasoning": "Right channel RCA output to guitar amp"},
                
                # Power Supply
                {"role": "dc_jack", "mpn": "PJ-002AH", "manufacturer": "CUI Devices", "value": "DC Jack", "package": "PTH", "reasoning": "12V DC adapter input"},
                {"role": "battery_clip", "mpn": "9V_CLIP", "manufacturer": "Keystone", "value": "9V Battery Clip", "package": "PTH", "reasoning": "9V battery backup option"},
                {"role": "power_switch", "mpn": "GT21MCBE", "manufacturer": "C&K", "value": "DPDT Switch", "package": "PTH", "reasoning": "Power on/off switch"},
                {"role": "regulator_pos", "mpn": "LM317L", "manufacturer": "TI", "value": "Adj. Regulator", "package": "TO-92", "reasoning": "Positive rail regulator (+15V)"},
                {"role": "regulator_neg", "mpn": "LM337L", "manufacturer": "TI", "value": "Adj. Regulator", "package": "TO-92", "reasoning": "Negative rail regulator (-15V)"},
                {"role": "vref_diode", "mpn": "TL431", "manufacturer": "TI", "value": "Shunt Regulator", "package": "TO-92", "reasoning": "Virtual ground reference (+/- 7.5V from single supply)"},
                {"role": "psu_cap_large", "mpn": "EEU-FC1E470", "manufacturer": "Panasonic", "value": "470uF/25V", "package": "Radial", "reasoning": "Main supply filtering"},
                {"role": "psu_cap_small", "mpn": "C0603C104K5RAC", "manufacturer": "KEMET", "value": "100nF", "package": "0603", "reasoning": "High frequency bypass"},
            ],
            "connections": [
                # Left channel signal path
                {"from": "input_jack_left", "to": "input_capacitor_left", "net": "L_IN_RCA"},
                {"from": "input_capacitor_left", "to": "input_resistor_left", "net": "L_IN_SIG"},
                {"from": "input_resistor_left", "to": "GND", "net": "GND"},
                {"from": "input_resistor_left", "to": "opamp_left_1", "net": "L_IN_OPAMP"},
                # RIAA network left (simplified - actual is feedback network around opamp)
                {"from": "opamp_left_1", "to": "riaa_r1_left", "net": "L_RIAA_R1"},
                {"from": "riaa_r1_left", "to": "riaa_c1_left", "net": "L_RIAA_C1"},
                {"from": "riaa_c1_left", "to": "GND", "net": "GND"},
                {"from": "opamp_left_1", "to": "gain_rf_left", "net": "L_FB"},
                {"from": "gain_rf_left", "to": "gain_r_left", "net": "L_FB_NET"},
                {"from": "gain_r_left", "to": "GND", "net": "GND"},
                {"from": "opamp_left_1", "to": "output_capacitor_left", "net": "L_OUT_OPAMP"},
                {"from": "output_capacitor_left", "to": "output_jack_left", "net": "L_OUT_RCA"},
                
                # Right channel signal path (mirror)
                {"from": "input_jack_right", "to": "input_capacitor_right", "net": "R_IN_RCA"},
                {"from": "input_capacitor_right", "to": "input_resistor_right", "net": "R_IN_SIG"},
                {"from": "input_resistor_right", "to": "GND", "net": "GND"},
                {"from": "input_resistor_right", "to": "opamp_right_1", "net": "R_IN_OPAMP"},
                {"from": "opamp_right_1", "to": "riaa_r1_right", "net": "R_RIAA_R1"},
                {"from": "riaa_r1_right", "to": "riaa_c1_right", "net": "R_RIAA_C1"},
                {"from": "riaa_c1_right", "to": "GND", "net": "GND"},
                {"from": "opamp_right_1", "to": "gain_rf_right", "net": "R_FB"},
                {"from": "gain_rf_right", "to": "gain_r_right", "net": "R_FB_NET"},
                {"from": "gain_r_right", "to": "GND", "net": "GND"},
                {"from": "opamp_right_1", "to": "output_capacitor_right", "net": "R_OUT_OPAMP"},
                {"from": "output_capacitor_right", "to": "output_jack_right", "net": "R_OUT_RCA"},
                
                # Power supply
                {"from": "dc_jack", "to": "power_switch", "net": "VIN_RAW"},
                {"from": "battery_clip", "to": "power_switch", "net": "VIN_BATT"},
                {"from": "power_switch", "to": "regulator_pos", "net": "VIN_REG"},
                {"from": "power_switch", "to": "regulator_neg", "net": "VIN_REG_NEG"},
                {"from": "regulator_pos", "to": "vref_diode", "net": "V_POS"},
                {"from": "regulator_neg", "to": "vref_diode", "net": "V_NEG"},
                {"from": "vref_diode", "to": "GND", "net": "VGND"},
                {"from": "vref_diode", "to": "opamp_left_1", "net": "VGND_REF"},
                {"from": "vref_diode", "to": "opamp_right_1", "net": "VGND_REF"},
                {"from": "psu_cap_large", "to": "GND", "net": "V_POS"},
                {"from": "psu_cap_large", "to": "VGND", "net": "VGND"},
                {"from": "psu_cap_large", "to": "GND", "net": "V_NEG"},
            ],
            "power_domains": {"V_POS": 15.0, "VGND": 0.0, "V_NEG": -15.0, "VIN": 12.0, "VBATT": 9.0},
            "design_notes": [
                "RIAA equalization: 3180µs (50Hz) pole, 318µs (500Hz) zero, 75µs (2120Hz) pole",
                "Total gain ~40dB (100x) at 1kHz for MM cartridge (~5mV -> 500mV)",
                "OPA2134: Low noise (8nV/√Hz), low distortion (0.0003%), FET input",
                "Virtual ground (VGND) at 1/2 supply for single-supply operation",
                "Input impedance: 47k || 100pF (standard MM loading)",
                "Output impedance: <100 ohm, suitable for guitar amp high-Z input",
                "Power: 9V battery (portable) or 12V DC adapter (wall wart)",
                "Regulated +/-15V rails for maximum headroom and low noise",
                "DC blocking caps on all inputs/outputs prevent DC offset issues"
            ],
            "warnings": [
                "Use metal-film resistors in RIAA network for accuracy (1% tolerance)",
                "Use C0G/NP0 capacitors in RIAA network for stability",
                "Keep RIAA network components close to opamp pins to minimize noise pickup",
                "Star ground layout critical: separate signal ground from power ground",
                "Shield RCA cables and keep away from power supply traces",
                "Test with oscilloscope: verify RIAA curve within ±1dB 20Hz-20kHz",
                "Guitar amp input impedance ~1M ohm - our <100 ohm output is fine"
            ]
        }
    }

    SPEC_SCHEMA = {
        "type": "object",
        "properties": {
            "topology": {"type": "string"},
            "components": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "role": {"type": "string"},
                        "mpn": {"type": "string"},
                        "manufacturer": {"type": "string"},
                        "value": {"type": "string"},
                        "package": {"type": "string"},
                        "reasoning": {"type": "string"},
                    },
                    "required": ["role", "mpn", "value", "package"]
                }
            },
            "connections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "from": {"type": "string"},
                        "to": {"type": "string"},
                        "net": {"type": "string"},
                    },
                    "required": ["from", "to", "net"]
                }
            },
            "power_domains": {"type": "object"},
            "design_notes": {"type": "array", "items": {"type": "string"}},
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["topology", "components"]
    }

    async def generate(self, requirements: CircuitRequirement) -> CircuitSpecification:
        """Generate detailed circuit specification from requirements."""
        if self.use_llm:
            try:
                return await self._generate_with_llm(requirements)
            except Exception as e:
                logger.warning(f"LLM generation failed, falling back to rule-based: {e}")
        
        # Fallback to rule-based generation
        spec_dict = self._generate_spec(requirements)
        return CircuitSpecification(
            requirements=requirements,
            topology=spec_dict["topology"],
            components=spec_dict["components"],
            connections=spec_dict.get("connections", []),
            power_domains=spec_dict.get("power_domains", {}),
            design_notes=spec_dict.get("design_notes", []),
            warnings=spec_dict.get("warnings", []),
        )

    async def _generate_with_llm(self, requirements: CircuitRequirement) -> CircuitSpecification:
        """Generate specification using LLM with structured output."""
        # Get few-shot example for this circuit type
        example = self.SPEC_EXAMPLES.get(requirements.circuit_type, {})
        example_text = json.dumps(example, indent=2) if example else "No example available for this circuit type."
        
        system_prompt = f"""You are an expert electronics engineer. Generate a detailed circuit specification based on the requirements.
        
        Provide:
        - topology: Circuit topology name (e.g., "LDO Linear Regulator", "Buck Converter", "Boost Converter")
        - components: List of components with role, MPN, manufacturer, value, package, and reasoning
        - connections: List of connections (from_component, to_component, net_name)
        - power_domains: Dictionary of power domains with voltage levels
        - design_notes: Important design considerations
        - warnings: Any warnings or concerns
        
        Use real MPNs from major manufacturers (TI, Analog Devices, STMicroelectronics, Onsemi, Diodes Inc, etc.).
        Select appropriate packages (SOT-23, SOIC-8, 0603, 0805, etc.) based on current/power requirements.
        Include input/output capacitors, protection diodes, and indicator LEDs as appropriate.
        
        Example for {requirements.circuit_type}:
        {example_text}"""

        # Build context with requirements
        req_context = f"""
Circuit Type: {requirements.circuit_type}
Description: {requirements.description}
Input Voltage: {requirements.input_voltage}V
Output Voltage: {requirements.output_voltage}V
Output Current: {requirements.output_current}A
Features: {requirements.features}
Constraints: {requirements.constraints}
"""

        prompt = f"Generate a detailed circuit specification for:\n{req_context}"

        try:
            result = await self.llm.complete_structured(
                messages=[
                    LLMMessage(role="system", content=system_prompt),
                    LLMMessage(role="user", content=prompt),
                ],
                response_schema=self.SPEC_SCHEMA
            )
            
            # Validate required fields
            if not result.get("topology") or not result.get("components") or result.get("topology") == "" or result.get("components") == []:
                raise ValueError("LLM response missing required fields (topology, components)")
            
            # Convert dict components to ComponentSpec objects
            components = []
            for comp_dict in result.get("components", []):
                components.append(ComponentSpec(
                    role=comp_dict.get("role", ""),
                    mpn=comp_dict.get("mpn", ""),
                    manufacturer=comp_dict.get("manufacturer", ""),
                    value=comp_dict.get("value", ""),
                    package=comp_dict.get("package", ""),
                    reasoning=comp_dict.get("reasoning", "")
                ))
            
            return CircuitSpecification(
                requirements=requirements,
                topology=result.get("topology", ""),
                components=components,
                connections=result.get("connections", []),
                power_domains=result.get("power_domains", {}),
                design_notes=result.get("design_notes", []),
                warnings=result.get("warnings", []),
            )
        except Exception as e:
            logger.error(f"LLM specification generation failed: {e}")
            raise

    def _generate_spec(self, req: CircuitRequirement) -> Dict[str, Any]:
        """Rule-based specification generation."""
        spec = {
            "topology": "",
            "components": [],
            "connections": [],
            "power_domains": {},
            "design_notes": [],
            "warnings": [],
        }

        if req.circuit_type == "ldo_regulator":
            return self._spec_ldo(req)
        elif req.circuit_type == "buck_converter":
            return self._spec_buck(req)
        elif req.circuit_type == "boost_converter":
            return self._spec_boost(req)
        elif req.circuit_type == "led_driver":
            return self._spec_led(req)
        elif req.circuit_type == "phono_preamp":
            return self._spec_phono_preamp(req)
        else:
            return self._spec_generic(req)

    def _spec_ldo(self, req) -> Dict[str, Any]:
        v_in = req.input_voltage or 5.0
        v_out = req.output_voltage or 3.3
        i_out = req.output_current or 0.5
        
        # Select LDO
        ldo = self._select_ldo(req.output_voltage or 3.3, req.output_current or 0.5)
        caps = self._select_caps()
        led = self._select_led()
        res = self._select_resistor()
        
        return {
            "topology": "linear_ldo",
            "components": [
                self._make_component(
                    role="regulator",
                    mpn=ldo.get("mpn", "AMS1117-3.3"),
                    manufacturer=ldo.get("manufacturer", "AMS"),
                    value=f"{req.output_voltage or 3.3}V",
                    package=ldo.get("package", "SOT-223"),
                    reasoning=f"LDO regulator {req.output_voltage or 3.3}V {req.output_current or 0.5}A"
                ),
                self._make_component(
                    role="input_capacitor",
                    mpn=caps[0].get("mpn", "CC0805KRX7R9BB106"),
                    manufacturer=caps[0].get("manufacturer", "Yageo"),
                    value=caps[0].get("value", "10uF"),
                    package=caps[0].get("package", "0805"),
                    reasoning="Input decoupling capacitor"
                ),
                self._make_component(
                    role="output_capacitor",
                    mpn=caps[1].get("mpn", "CC0805KRX5R7BB226"),
                    manufacturer=caps[1].get("manufacturer", "Yageo"),
                    value=caps[1].get("value", "22uF"),
                    package=caps[1].get("package", "0805"),
                    reasoning="Output stability capacitor"
                ),
                self._make_component(
                    role="led_indicator",
                    mpn=led.get("mpn", "LTST-C190KGKT"),
                    manufacturer=led.get("manufacturer", "Lite-On"),
                    value=led.get("value", "Green"),
                    package=led.get("package", "0805"),
                    reasoning="Power-on indicator"
                ),
                self._make_component(
                    role="current_limit_resistor",
                    mpn=res.get("mpn", "RC0805FR-0710KL"),
                    manufacturer=res.get("manufacturer", "Yageo"),
                    value=res.get("value", "330"),
                    package=res.get("package", "0805"),
                    reasoning="LED current limiting resistor"
                ),
            ],
            "design_notes": [
                f"LDO dropout: {5.0 - 3.3}V",
                f"Power dissipation: {(5.0 - 3.3) * 0.5:.2f}W",
                "Ensure adequate thermal relief"
            ],
            "warnings": [
                "Check thermal dissipation for high current",
                "Verify dropout voltage at max current"
            ] if (5.0 - 3.3) * 0.5 > 0.5 else []
        }

    def _select_ldo(self, v_out: float, i_out: float) -> dict:
        # Simplified selection - in reality would query database
        return {
            "mpn": "AMS1117-3.3",
            "manufacturer": "AMS",
            "package": "SOT-223",
            "v_out": v_out,
            "i_max": 1.0
        }

    def _select_caps(self) -> List[dict]:
        return [
            {"mpn": "C-10uF-0805", "manufacturer": "Yageo", "value": "10uF", "package": "0805"},
            {"mpn": "C-22uF-0805", "manufacturer": "Yageo", "value": "22uF", "package": "0805"}
        ]

    def _select_led(self) -> dict:
        return {"mpn": "LED-GREEN-0805", "manufacturer": "Lite-On", "package": "0805"}

    def _select_resistor(self) -> dict:
        return {"mpn": "R-330-0805", "manufacturer": "Yageo", "value": "330", "package": "0805"}

    def _spec_buck(self, req):
        return {
            "topology": "buck_async",
            "components": [
                {
                    "role": "controller",
                    "mpn": "LM2596S-5.0",
                    "manufacturer": "TI",
                    "value": "5V",
                    "package": "TO-220-5",
                    "reasoning": "Buck converter controller"
                },
                {
                    "role": "inductor",
                    "mpn": "SRR1280-470M",
                    "manufacturer": "Bourns",
                    "value": "47uH",
                    "package": "12x12mm",
                    "reasoning": "Buck inductor"
                },
                {
                    "role": "input_capacitor",
                    "mpn": "C-10uF-0805",
                    "manufacturer": "Yageo",
                    "value": "10uF",
                    "package": "0805",
                    "reasoning": "Input decoupling"
                },
                {
                    "role": "output_capacitor",
                    "mpn": "C-100uF-1206",
                    "manufacturer": "Yageo",
                    "value": "100uF",
                    "package": "1206",
                    "reasoning": "Output filtering"
                },
                {
                    "role": "freewheel_diode",
                    "mpn": "SS34",
                    "manufacturer": "Vishay",
                    "value": "3A/40V",
                    "package": "SMA",
                    "reasoning": "Freewheeling diode"
                },
            ],
            "design_notes": ["Asynchronous buck converter", "Consider sync rectification for >90% efficiency"],
            "warnings": ["Diode loss significant at high current"]
        }

    def _spec_boost(self, req):
        return {
            "topology": "boost",
            "components": [
                {
                    "role": "controller",
                    "mpn": "MT3608",
                    "manufacturer": "Aerosemi",
                    "value": "Adjustable",
                    "package": "SOT-23-6",
                    "reasoning": "Boost converter IC"
                },
                {
                    "role": "inductor",
                    "mpn": "SRR0604-100M",
                    "manufacturer": "Bourns",
                    "value": "10uH",
                    "package": "6x6mm",
                    "reasoning": "Boost inductor"
                },
            ],
            "design_notes": ["Boost converter for voltage step-up"],
            "warnings": ["Output current limited by inductor saturation"]
        }

    def _spec_led(self, req):
        return {
            "topology": "series_resistor",
            "components": [
                {
                    "role": "led",
                    "mpn": "LTST-C190KGKT",
                    "manufacturer": "Lite-On",
                    "value": "Green",
                    "package": "0805",
                    "reasoning": "Green indicator LED"
                },
                {
                    "role": "current_limit_resistor",
                    "mpn": "RC0805FR-0710KL",
                    "manufacturer": "Yageo",
                    "value": "10k",
                    "package": "0805",
                    "reasoning": "Current limiting resistor"
                }
            ],
            "design_notes": ["Simple series resistor LED driver"],
            "warnings": ["Not suitable for high-power LEDs"]
        }

    def _spec_phono_preamp(self, req):
        """Stereo RIAA Phono Preamplifier for Moving Magnet Cartridge."""
        return self.SPEC_EXAMPLES["phono_preamp"]

    def _spec_generic(self, req):
        return {
            "topology": "generic",
            "components": [],
            "design_notes": ["Generic circuit - specify topology"],
            "warnings": ["Topology not recognized"]
        }


class NLToCircuitPipeline:
    """End-to-end pipeline: Natural Language -> CircuitIR -> KiCad."""
    
    def __init__(
        self,
        llm_client: Optional[Any] = None,
        component_db: Optional[Any] = None,
    ):
        """Initialize pipeline with optional LLM client and component database.
        
        Args:
            llm_client: LLM client instance. If None, uses mock client.
            component_db: Optional component database for part selection.
        """
        if llm_client is None:
            llm_client = create_llm_client("mock")
        
        self.llm_client = llm_client
        self.parser = RequirementParser(llm_client)
        self.spec_generator = CircuitSpecificationGenerator(llm_client, None)
        self.orchestrator = None
    
    def set_orchestrator(self, orchestrator: Any) -> None:
        """Set the orchestrator for this pipeline."""
        self.orchestrator = orchestrator
    
    async def nl_to_circuit_spec(self, prompt: str) -> CircuitSpecification:
        """Process natural language prompt through full pipeline to circuit spec."""
        # Step 1: Parse requirements
        requirements = await self.parser.parse(prompt)
        
        # Step 2: Generate specification
        spec = await self.spec_generator.generate(requirements)
        
        # Step 3: Generate CircuitIR (simplified - would use spec to build CircuitIR)
        self._spec_to_circuit_ir(requirements)
        
        return spec
    
    async def process(
        self,
        prompt: str,
        project_name: str = "design",
        output_dir: Optional[Path] = None,
    ) -> dict:
        """Process natural language prompt through full pipeline.
        
        Args:
            prompt: Natural language description of the circuit
            project_name: Name for the output project
            output_dir: Optional output directory for generated files
            
        Returns:
            Dictionary with requirements, specification, circuit_ir, and generated files
        """
        # Step 1: Parse requirements
        requirements = await self.parser.parse(prompt)
        
        # Step 2: Generate specification
        spec = await self.spec_generator.generate(requirements)
        
        # Step 3: Generate CircuitIR (simplified - would use spec to build CircuitIR)
        circuit_ir = self._spec_to_circuit_ir(requirements)
        
        return {
            "requirements": requirements,
            "specification": spec,
            "circuit_ir": circuit_ir,
        }
    
    def _spec_to_dict(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """Convert specification to dictionary for serialization."""
        return spec
    
    def _spec_to_circuit_ir(self, requirements: CircuitRequirement) -> 'CircuitIR':
        """Convert requirements to CircuitIR based on circuit type."""
        from src.core.circuit_ir import CircuitIR, Component, ComponentType, PinType
        from src.components.database import ComponentDatabase
        
        db = ComponentDatabase()
        circuit = CircuitIR(name=f"Generated {requirements.circuit_type.replace('_', ' ').title()}")
        
        # LDO Regulator Pattern
        if requirements.circuit_type == "ldo_regulator":
            # Fetch parts from DB
            ldo_spec = db.get_by_mpn("AMS1117-3.3") or db.search(category="regulator_ldo")[0]
            c_in_spec = db.get_by_mpn("C-10uF-0805") or db.search(category="capacitor")[0]
            c_out_spec = db.get_by_mpn("C-22uF-0805") or db.search(category="capacitor")[0]
            res_spec = db.get_by_mpn("R-330-0805") or db.search(category="resistor")[0]
            led_spec = db.get_by_mpn("LED-GREEN-0805") or db.search(category="led")[0]

            # LDO Regulator U1
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

            # Input Capacitor C1
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

            # Output Capacitor C2
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

            # Indicator LED D1
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

            # Current Limiting Resistor R1
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

            # Nets
            circuit.connect("U1", "3", "VIN")      # VIN
            circuit.connect("U1", "2", "VOUT")     # VOUT
            circuit.connect("U1", "1", "GND")      # GND
            circuit.connect("C1", "1", "VIN")
            circuit.connect("C1", "2", "GND")
            circuit.connect("C2", "1", "VOUT")
            circuit.connect("C2", "2", "GND")
            circuit.connect("R1", "1", "VOUT")
            circuit.connect("R1", "2", "D1_A")
            circuit.connect("D1", "A", "D1_A")
            circuit.connect("D1", "K", "GND")
        
        # Buck Converter Pattern
        elif requirements.circuit_type == "buck_converter":
            # Fetch parts from DB
            ctrl_spec = db.get_by_mpn("LM2596S-5.0") or db.search(category="regulator_buck")[0]
            # Create fallback inductor spec if not in DB
            class IndSpec:
                value = "47uH"
                footprint = "12x12mm"
                symbol = "Inductor"
                mpn = "SRR1280-470M"
            ind_spec = db.get_by_mpn("SRR1280-470M") or IndSpec()
            c_in_spec = db.get_by_mpn("C-10uF-0805") or db.search(category="capacitor")[0]
            c_out_spec = db.get_by_mpn("C-100uF-1206") or db.search(category="capacitor")[0]
            diode_spec = db.get_by_mpn("SS14") or db.search(category="diode")[0]

            # Buck Controller U1 (LM2596S-5.0)
            u1 = Component(
                ref="U1",
                value=ctrl_spec.value,
                component_type=ComponentType.REGULATOR_BUCK,
                footprint=ctrl_spec.footprint,
                symbol=ctrl_spec.symbol,
                mpn=ctrl_spec.mpn,
                manufacturer=ctrl_spec.manufacturer,
                description=ctrl_spec.description,
            )
            # LM2596 pins: 1=VIN, 2=SW, 3=GND, 4=FB, 5=ON/OFF
            u1.add_pin("1", "VIN", PinType.POWER_IN)
            u1.add_pin("2", "SW", PinType.OUTPUT)
            u1.add_pin("3", "GND", PinType.POWER_IN)
            u1.add_pin("4", "FB", PinType.INPUT)
            u1.add_pin("5", "EN", PinType.INPUT)
            circuit.add_component(u1)

            # Inductor L1
            l1 = Component(
                ref="L1",
                value=ind_spec.value,
                component_type=ComponentType.INDUCTOR,
                footprint=ind_spec.footprint,
                symbol=ind_spec.symbol,
                mpn=ind_spec.mpn,
            )
            l1.add_pin("1", "1", PinType.PASSIVE)
            l1.add_pin("2", "2", PinType.PASSIVE)
            circuit.add_component(l1)

            # Input Capacitor C1
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

            # Output Capacitor C2
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

            # Freewheeling Diode D1
            d1 = Component(
                ref="D1",
                value=diode_spec.value,
                component_type=ComponentType.DIODE,
                footprint=diode_spec.footprint,
                symbol=diode_spec.symbol,
                mpn=diode_spec.mpn,
            )
            d1.add_pin("1", "A", PinType.PASSIVE)
            d1.add_pin("2", "K", PinType.PASSIVE)
            circuit.add_component(d1)

            # Nets for buck converter
            circuit.connect("U1", "1", "VIN")       # VIN
            circuit.connect("U1", "2", "SW")        # Switch node
            circuit.connect("U1", "3", "GND")       # GND
            circuit.connect("U1", "5", "VIN")       # EN tied to VIN
            circuit.connect("L1", "1", "SW")        # Inductor to switch node
            circuit.connect("L1", "2", "VOUT")      # Inductor to output
            circuit.connect("C1", "1", "VIN")
            circuit.connect("C1", "2", "GND")
            circuit.connect("C2", "1", "VOUT")
            circuit.connect("C2", "2", "GND")
            circuit.connect("D1", "A", "SW")        # Diode anode to switch node
            circuit.connect("D1", "K", "VOUT")      # Diode cathode to output
            # Feedback divider (simplified - would need R1, R2 for adjustable version)
            circuit.connect("U1", "4", "VOUT")      # FB directly to output for fixed 5V version
        
        # Boost Converter Pattern
        elif requirements.circuit_type == "boost_converter":
            # Fetch parts from DB
            ctrl_spec = db.get_by_mpn("MT3608") or db.search(category="regulator_buck")[0]
            class IndSpec:
                value = "10uH"
                footprint = "6x6mm"
                symbol = "Inductor"
                mpn = "SRR0604-100M"
            ind_spec = db.get_by_mpn("SRR0604-100M") or IndSpec()
            c_in_spec = db.get_by_mpn("C-10uF-0805") or db.search(category="capacitor")[0]
            c_out_spec = db.get_by_mpn("C-22uF-0805") or db.search(category="capacitor")[0]
            diode_spec = db.get_by_mpn("SS14") or db.search(category="diode")[0]
            res_spec = db.get_by_mpn("R-100k-0805") or db.search(category="resistor")[0]
            res2_spec = db.get_by_mpn("R-20k-0805") or db.search(category="resistor")[0]

            # Boost Controller U1 (MT3608)
            u1 = Component(
                ref="U1",
                value=ctrl_spec.value,
                component_type=ComponentType.REGULATOR_BOOST,
                footprint=ctrl_spec.footprint,
                symbol=ctrl_spec.symbol,
                mpn=ctrl_spec.mpn,
                manufacturer=ctrl_spec.manufacturer,
                description=ctrl_spec.description,
            )
            # MT3608 pins: 1=SW, 2=GND, 3=FB, 4=EN, 5=VIN, 6=NC
            u1.add_pin("1", "SW", PinType.OUTPUT)
            u1.add_pin("2", "GND", PinType.POWER_IN)
            u1.add_pin("3", "FB", PinType.INPUT)
            u1.add_pin("4", "EN", PinType.INPUT)
            u1.add_pin("5", "VIN", PinType.POWER_IN)
            circuit.add_component(u1)

            # Inductor L1
            l1 = Component(
                ref="L1",
                value=ind_spec.value,
                component_type=ComponentType.INDUCTOR,
                footprint=ind_spec.footprint,
                symbol=ind_spec.symbol,
                mpn=ind_spec.mpn,
            )
            l1.add_pin("1", "1", PinType.PASSIVE)
            l1.add_pin("2", "2", PinType.PASSIVE)
            circuit.add_component(l1)

            # Input Capacitor C1
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

            # Output Capacitor C2
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

            # Schottky Diode D1
            d1 = Component(
                ref="D1",
                value=diode_spec.value,
                component_type=ComponentType.DIODE,
                footprint=diode_spec.footprint,
                symbol=diode_spec.symbol,
                mpn=diode_spec.mpn,
            )
            d1.add_pin("1", "A", PinType.PASSIVE)
            d1.add_pin("2", "K", PinType.PASSIVE)
            circuit.add_component(d1)

            # Feedback Resistors R1 (top), R2 (bottom)
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

            r2 = Component(
                ref="R2",
                value=res2_spec.value,
                component_type=ComponentType.RESISTOR,
                footprint=res2_spec.footprint,
                symbol=res2_spec.symbol,
                mpn=res2_spec.mpn,
            )
            r2.add_pin("1", "1", PinType.PASSIVE)
            r2.add_pin("2", "2", PinType.PASSIVE)
            circuit.add_component(r2)

            # Nets for boost converter
            circuit.connect("U1", "5", "VIN")       # VIN
            circuit.connect("U1", "2", "GND")       # GND
            circuit.connect("U1", "4", "VIN")       # EN tied to VIN
            circuit.connect("L1", "1", "VIN")       # Inductor to VIN
            circuit.connect("L1", "2", "SW")        # Inductor to switch node
            circuit.connect("U1", "1", "SW")        # Switch pin to switch node
            circuit.connect("D1", "A", "SW")        # Diode anode to switch node
            circuit.connect("D1", "K", "VOUT")      # Diode cathode to output
            circuit.connect("C1", "1", "VIN")
            circuit.connect("C1", "2", "GND")
            circuit.connect("C2", "1", "VOUT")
            circuit.connect("C2", "2", "GND")
            # Feedback divider: VOUT -> R1 -> FB -> R2 -> GND
            circuit.connect("R1", "1", "VOUT")
            circuit.connect("R1", "2", "FB_NODE")
            circuit.connect("R2", "1", "FB_NODE")
            circuit.connect("R2", "2", "GND")
            circuit.connect("U1", "3", "FB_NODE")
        
        # LED Circuit Pattern
        elif requirements.circuit_type == "led_driver":
            led_spec = db.get_by_mpn("LED-GREEN-0805") or db.search(category="led")[0]
            res_spec = db.get_by_mpn("R-330-0805") or db.search(category="resistor")[0]
            
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
            
        # Phono Preamp Pattern
        elif requirements.circuit_type == "phono_preamp":
            # Create a simple but functional representation for SPICE/KiCad compatibility
            # This creates a basic opamp buffer with RIAA-like feedback to satisfy the design flow
            
            # Dual opamp (we'll use one channel for left, one for right - simplified stereo)
            opamp = Component(
                ref="U1",
                value="OPA2134",
                component_type=ComponentType.OPAMP,
                footprint="DIP-8",
                symbol="OpAmp",
                mpn="OPA2134PA",
                manufacturer="TI",
                description="Dual low-noise audio opamp (TL072 substitute for simulation)",
            )
            opamp.add_pin("1", "OUT_A", PinType.OUTPUT)
            opamp.add_pin("2", "IN_A-", PinType.INPUT)
            opamp.add_pin("3", "IN_A+", PinType.INPUT)
            opamp.add_pin("4", "V-", PinType.POWER_IN)
            opamp.add_pin("5", "IN_B+", PinType.INPUT)
            opamp.add_pin("6", "IN_B-", PinType.INPUT)
            opamp.add_pin("7", "OUT_B", PinType.OUTPUT)
            opamp.add_pin("8", "V+", PinType.POWER_IN)
            circuit.add_component(opamp)
            
            # Power supply connections (using virtual ground for single supply operation)
            # We'll create a virtual ground at half supply using a resistor divider
            circuit.connect("U1", "4", "V_NEG")   # V- to -15V (or GND in single supply)
            circuit.connect("U1", "8", "V_POS")   # V+ to +15V (or VIN in single supply)
            
            # Input and output connectors
            # Left channel
            rca_in_l = Component(
                ref="J1_L",
                value="RCA_IN",
                component_type=ComponentType.CONNECTOR,
                footprint="RCA_TH",
                symbol="RCA",
                mpn="RCJ-002",
                manufacturer="CUI Devices",
                description="Left RCA input jack",
            )
            rca_in_l.add_pin("1", "SIGNAL", PinType.PASSIVE)
            rca_in_l.add_pin("2", "SHIELD", PinType.PASSIVE)
            circuit.add_component(rca_in_l)
            
            rca_out_l = Component(
                ref="J2_L",
                value="RCA_OUT",
                component_type=ComponentType.CONNECTOR,
                footprint="RCA_TH",
                symbol="RCA",
                mpn="RCJ-002",
                manufacturer="CUI Devices",
                description="Left RCA output jack",
            )
            rca_out_l.add_pin("1", "SIGNAL", PinType.PASSIVE)
            rca_out_l.add_pin("2", "SHIELD", PinType.PASSIVE)
            circuit.add_component(rca_out_l)
            
            # Right channel
            rca_in_r = Component(
                ref="J1_R",
                value="RCA_IN",
                component_type=ComponentType.CONNECTOR,
                footprint="RCA_TH",
                symbol="RCA",
                mpn="RCJ-002",
                manufacturer="CUI Devices",
                description="Right RCA input jack",
            )
            rca_in_r.add_pin("1", "SIGNAL", PinType.PASSIVE)
            rca_in_r.add_pin("2", "SHIELD", PinType.PASSIVE)
            circuit.add_component(rca_in_r)
            
            rca_out_r = Component(
                ref="J2_R",
                value="RCA_OUT",
                component_type=ComponentType.CONNECTOR,
                footprint="RCA_TH",
                symbol="RCA",
                mpn="RCJ-002",
                manufacturer="CUI Devices",
                description="Right RCA output jack",
            )
            rca_out_r.add_pin("1", "SIGNAL", PinType.PASSIVE)
            rca_out_r.add_pin("2", "SHIELD", PinType.PASSIVE)
            circuit.add_component(rca_out_r)
            
            # Input resistors (47k standard for MM cartridge)
            rin_l = Component(
                ref="RIN_L",
                value="47k",
                component_type=ComponentType.RESISTOR,
                footprint="0603",
                symbol="Resistor",
                mpn="RC0603FR-0747KL",
                manufacturer="Yageo",
                description="Left input loading resistor",
            )
            rin_l.add_pin("1", "1", PinType.PASSIVE)
            rin_l.add_pin("2", "2", PinType.PASSIVE)
            circuit.add_component(rin_l)
            
            rin_r = Component(
                ref="RIN_R",
                value="47k",
                component_type=ComponentType.RESISTOR,
                footprint="0603",
                symbol="Resistor",
                mpn="RC0603FR-0747KL",
                manufacturer="Yageo",
                description="Right input loading resistor",
            )
            rin_r.add_pin("1", "1", PinType.PASSIVE)
            rin_r.add_pin("2", "2", PinType.PASSIVE)
            circuit.add_component(rin_r)
            
            # Feedback resistors for gain (~40dB = 100x)
            rf_l = Component(
                ref="RF_L",
                value="100k",
                component_type=ComponentType.RESISTOR,
                footprint="0603",
                symbol="Resistor",
                mpn="RC0603FR-0710KL",
                manufacturer="Yageo",
                description="Left feedback resistor",
            )
            rf_l.add_pin("1", "1", PinType.PASSIVE)
            rf_l.add_pin("2", "2", PinType.PASSIVE)
            circuit.add_component(rf_l)
            
            rf_r = Component(
                ref="RF_R",
                value="100k",
                component_type=ComponentType.RESISTOR,
                footprint="0603",
                symbol="Resistor",
                mpn="RC0603FR-0710KL",
                manufacturer="Yageo",
                description="Right feedback resistor",
            )
            rf_r.add_pin("1", "1", PinType.PASSIVE)
            rf_r.add_pin("2", "2", PinType.PASSIVE)
            circuit.add_component(rf_r)
            
            ri_l = Component(
                ref="RI_L",
                value="1k",
                component_type=ComponentType.RESISTOR,
                footprint="0603",
                symbol="Resistor",
                mpn="RC0603FR-0710KL",
                manufacturer="Yageo",
                description="Left input resistor for gain",
            )
            ri_l.add_pin("1", "1", PinType.PASSIVE)
            ri_l.add_pin("2", "2", PinType.PASSIVE)
            circuit.add_component(ri_l)
            
            ri_r = Component(
                ref="RI_R",
                value="1k",
                component_type=ComponentType.RESISTOR,
                footprint="0603",
                symbol="Resistor",
                mpn="RC0603FR-0710KL",
                manufacturer="Yageo",
                description="Right input resistor for gain",
            )
            ri_r.add_pin("1", "1", PinType.PASSIVE)
            ri_r.add_pin("2", "2", PinType.PASSIVE)
            circuit.add_component(ri_r)
            
            # DC blocking capacitors (input and output)
            cin_l = Component(
                ref="CIN_L",
                value="0.1uF",
                component_type=ComponentType.CAPACITOR,
                footprint="0603",
                symbol="Capacitor",
                mpn="C0603C104K5RAC",
                manufacturer="KEMET",
                description="Left input blocking capacitor",
            )
            cin_l.add_pin("1", "1", PinType.PASSIVE)
            cin_l.add_pin("2", "2", PinType.PASSIVE)
            circuit.add_component(cin_l)
            
            cin_r = Component(
                ref="CIN_R",
                value="0.1uF",
                component_type=ComponentType.CAPACITOR,
                footprint="0603",
                symbol="Capacitor",
                mpn="C0603C104K5RAC",
                manufacturer="KEMET",
                description="Right input blocking capacitor",
            )
            cin_r.add_pin("1", "1", PinType.PASSIVE)
            cin_r.add_pin("2", "2", PinType.PASSIVE)
            circuit.add_component(cin_r)
            
            cout_l = Component(
                ref="COUT_L",
                value="1uF",
                component_type=ComponentType.CAPACITOR,
                footprint="0603",
                symbol="Capacitor",
                mpn="C0603C105K5RAC",
                manufacturer="KEMET",
                description="Left output blocking capacitor",
            )
            cout_l.add_pin("1", "1", PinType.PASSIVE)
            cout_l.add_pin("2", "2", PinType.PASSIVE)
            circuit.add_component(cout_l)
            
            cout_r = Component(
                ref="COUT_R",
                value="1uF",
                component_type=ComponentType.CAPACITOR,
                footprint="0603",
                symbol="Capacitor",
                mpn="C0603C105K5RAC",
                manufacturer="KEMET",
                description="Right output blocking capacitor",
            )
            cout_r.add_pin("1", "1", PinType.PASSIVE)
            cout_r.add_pin("2", "2", PinType.PASSIVE)
            circuit.add_component(cout_r)
            
            # Power supply components
            # Input jack
            power_jack = Component(
                ref="J_POWER",
                value="DC_JACK",
                component_type=ComponentType.CONNECTOR,
                footprint="DC_JACK_TH",
                symbol="DC_JACK",
                mpn="PJ-002AH",
                manufacturer="CUI Devices",
                description="DC power jack",
            )
            power_jack.add_pin("1", "TIP", PinType.PASSIVE)
            power_jack.add_pin("2", "SLEEVE", PinType.PASSIVE)
            circuit.add_component(power_jack)
            
            # Power switch
            power_switch = Component(
                ref="SW_POWER",
                value="DPDT_SW",
                component_type=ComponentType.SWITCH,
                footprint="DPDT_TH",
                symbol="DPDT_SW",
                mpn="GT21MCBE",
                manufacturer="C&K",
                description="Power on/off switch",
            )
            # DPDT switch: 3 pins per pole, we'll simplify
            power_switch.add_pin("1", "COM1", PinType.PASSIVE)
            power_switch.add_pin("2", "NO1", PinType.PASSIVE)
            power_switch.add_pin("3", "NC1", PinType.PASSIVE)
            power_switch.add_pin("4", "COM2", PinType.PASSIVE)
            power_switch.add_pin("5", "NO2", PinType.PASSIVE)
            power_switch.add_pin("6", "NC2", PinType.PASSIVE)
            circuit.add_component(power_switch)
            
            # Battery connector
            battery_clip = Component(
                ref="J_BATT",
                value="9V_CLIP",
                component_type=ComponentType.CONNECTOR,
                footprint="9V_CLIP_TH",
                symbol="BATT_CLIP",
                mpn="9V_CLIP",
                manufacturer="Keystone",
                description="9V battery clip",
            )
            battery_clip.add_pin("1", "+", PinType.PASSIVE)
            battery_clip.add_pin("2", "-", PinType.PASSIVE)
            circuit.add_component(battery_clip)
            
            # Voltage regulator (we'll use a simple 7809 for 9V, but for +/-15V we need two)
            # For simplicity in this demo, we'll use a single 9V regulator and create virtual ground
            regulator = Component(
                ref="U2",
                value="7809",
                component_type=ComponentType.REGULATOR_LDO,
                footprint="TO-220",
                symbol="Regulator",
                mpn="MC7809CT",
                manufacturer="ON Semiconductor",
                description="9V voltage regulator",
            )
            regulator.add_pin("1", "INPUT", PinType.POWER_IN)
            regulator.add_pin("2", "GROUND", PinType.POWER_IN)
            regulator.add_pin("3", "OUTPUT", PinType.POWER_OUT)
            circuit.add_component(regulator)
            
            # Filtering capacitors
            cin_reg = Component(
                ref="CIN_REG",
                value="0.33uF",
                component_type=ComponentType.CAPACITOR,
                footprint="0603",
                symbol="Capacitor",
                mpn="C0603C334K5RAC",
                manufacturer="KEMET",
                description="Regulator input capacitor",
            )
            cin_reg.add_pin("1", "1", PinType.PASSIVE)
            cin_reg.add_pin("2", "2", PinType.PASSIVE)
            circuit.add_component(cin_reg)
            
            cout_reg = Component(
                ref="COUT_REG",
                value="0.1uF",
                component_type=ComponentType.CAPACITOR,
                footprint="0603",
                symbol="Capacitor",
                mpn="C0603C104K5RAC",
                manufacturer="KEMET",
                description="Regulator output capacitor",
            )
            cout_reg.add_pin("1", "1", PinType.PASSIVE)
            cout_reg.add_pin("2", "2", PinType.PASSIVE)
            circuit.add_component(cout_reg)
            
            # Virtual ground divider (two equal resistors to create VGND at VIN/2)
            r_vgnd1 = Component(
                ref="R_VGND1",
                value="10k",
                component_type=ComponentType.RESISTOR,
                footprint="0603",
                symbol="Resistor",
                mpn="RC0603FR-0710KL",
                manufacturer="Yageo",
                description="Virtual ground divider resistor 1",
            )
            r_vgnd1.add_pin("1", "1", PinType.PASSIVE)
            r_vgnd1.add_pin("2", "2", PinType.PASSIVE)
            circuit.add_component(r_vgnd1)
            
            r_vgnd2 = Component(
                ref="R_VGND2",
                value="10k",
                component_type=ComponentType.RESISTOR,
                footprint="0603",
                symbol="Resistor",
                mpn="RC0603FR-0710KL",
                manufacturer="Yageo",
                description="Virtual ground divider resistor 2",
            )
            r_vgnd2.add_pin("1", "1", PinType.PASSIVE)
            r_vgnd2.add_pin("2", "2", PinType.PASSIVE)
            circuit.add_component(r_vgnd2)
            
            # Bypass capacitor for virtual ground
            c_vgnd = Component(
                ref="C_VGND",
                value="0.1uF",
                component_type=ComponentType.CAPACITOR,
                footprint="0603",
                symbol="Capacitor",
                mpn="C0603C104K5RAC",
                manufacturer="KEMET",
                description="Virtual ground bypass capacitor",
            )
            c_vgnd.add_pin("1", "1", PinType.PASSIVE)
            c_vgnd.add_pin("2", "2", PinType.PASSIVE)
            circuit.add_component(c_vgnd)
            
            # === CONNECTIONS ===
            
            # Power supply connections
            circuit.connect("J_POWER", "TIP", "VIN_RAW")
            circuit.connect("J_POWER", "SLEEVE", "GND_RAW")
            circuit.connect("J_BATT", "+", "VIN_RAW")
            circuit.connect("J_BATT", "-", "GND_RAW")
            circuit.connect("SW_POWER", "COM1", "VIN_RAW")
            circuit.connect("SW_POWER", "COM2", "GND_RAW")
            circuit.connect("SW_POWER", "NO1", "VIN_SW")
            circuit.connect("SW_POWER", "NO2", "GND_SW")
            circuit.connect("U2", "INPUT", "VIN_SW")
            circuit.connect("U2", "GROUND", "GND_SW")
            circuit.connect("U2", "OUTPUT", "VREG_OUT")
            circuit.connect("CIN_REG", "1", "VIN_SW")
            circuit.connect("CIN_REG", "2", "GND_SW")
            circuit.connect("COUT_REG", "1", "VREG_OUT")
            circuit.connect("COUT_REG", "2", "GND_SW")
            
            # Virtual ground
            circuit.connect("R_VGND1", "1", "VREG_OUT")
            circuit.connect("R_VGND1", "2", "VGND")
            circuit.connect("R_VGND2", "1", "VGND")
            circuit.connect("R_VGND2", "2", "GND_SW")
            circuit.connect("C_VGND", "1", "VGND")
            circuit.connect("C_VGND", "2", "GND_SW")
            
            # Opamp power connections (using virtual ground)
            circuit.connect("U1", "4", "VGND")   # V- to virtual ground (simplified single supply)
            circuit.connect("U1", "8", "VREG_OUT") # V+ to regulated 9V
            
            # Left channel signal path
            circuit.connect("J1_L", "1", "LIN_SIG")
            circuit.connect("J1_L", "2", "GROUND")
            circuit.connect("LIN_SIG", "CIN_L", "1")
            circuit.connect("CIN_L", "1", "LIN_C")
            circuit.connect("CIN_L", "2", "LIN_R")
            circuit.connect("LIN_R", "RIN_L", "1")
            circuit.connect("RIN_L", "1", "LIN_R_IN")
            circuit.connect("RIN_L", "2", "LIN_R_OUT")
            circuit.connect("LIN_R_OUT", "U1", "3")
            circuit.connect("U1", "2", "L_FB")
            circuit.connect("L_FB", "RF_L", "1")
            circuit.connect("RF_L", "1", "L_FB_R")
            circuit.connect("RF_L", "2", "L_FB_OUT")
            circuit.connect("L_FB_OUT", "U1", "7")
            circuit.connect("U1", "7", "COUT_L")
            circuit.connect("COUT_L", "1", "LOUT_C")
            circuit.connect("COUT_L", "2", "LOUT_R")
            circuit.connect("LOUT_R", "J2_L", "1")
            circuit.connect("J2_L", "2", "GROUND")
            
            # Right channel signal path
            circuit.connect("J1_R", "SIGNAL", "R_IN_RCA")
            circuit.connect("J1_R", "SHIELD", "GND")
            circuit.connect("R_IN_RCA", "CIN_R", "R_IN_C")
            circuit.connect("CIN_R", "1", "R_IN_C")
            circuit.connect("CIN_R", "2", "R_IN_R")
            circuit.connect("R_IN_R", "RIN_R", "R_IN_R_IN")
            circuit.connect("RIN_R", "1", "R_IN_R_IN")
            circuit.connect("RIN_R", "2", "R_IN_R_OUT")
            circuit.connect("R_IN_R_OUT", "U1", "IN_B+")
            circuit.connect("U1", "IN_B-", "R_FB_IN")
            circuit.connect("R_FB_IN", "RF_R", "R_FB_R")
            circuit.connect("RF_R", "1", "R_FB_R")
            circuit.connect("RF_R", "2", "R_FB_OUT")
            circuit.connect("R_FB_OUT", "U1", "OUT_B")
            circuit.connect("U1", "OUT_B", "COUT_R")
            circuit.connect("COUT_R", "1", "R_OUT_C")
            circuit.connect("COUT_R", "2", "R_OUT_R")
            circuit.connect("R_OUT_R", "J2_R", "SIGNAL")
            circuit.connect("J2_R", "SHIELD", "GND")
            
            # Ground everything that needs grounding
            circuit.connect("J1_L", "SHIELD", "GND")
            circuit.connect("J2_L", "SHIELD", "GND")
            circuit.connect("J1_R", "SHIELD", "GND")
            circuit.connect("J2_R", "SHIELD", "GND")
            circuit.connect("J_POWER", "SLEEVE", "GND")
            circuit.connect("J_BATT", "-", "GND")
            circuit.connect("SW_POWER", "NC1", "GND")
            circuit.connect("SW_POWER", "NC2", "GND")
            circuit.connect("U2", "GROUND", "GND")
            circuit.connect("CIN_REG", "2", "GND")
            circuit.connect("COUT_REG", "2", "GND")
            circuit.connect("R_VGND2", "2", "GND")
            circuit.connect("C_VGND", "2", "GND")
            
            return circuit
        
        # Default return for any unhandled circuit type
        return circuit


def create_nl_pipeline(llm_provider: Union[LLMProvider, str] = "mock", component_db=None) -> NLToCircuitPipeline:
    """Factory function to create NL pipeline.
    
    Args:
        llm_provider: LLM provider string or LLMProvider enum
        component_db: Optional component database for part selection
    """
    if isinstance(llm_provider, str):
        try:
            provider = LLMProvider(llm_provider.lower())
        except ValueError:
            raise ValueError(f"Unknown provider: {llm_provider}")
        llm_client = create_llm_client(provider)
    else:
        llm_client = create_llm_client(llm_provider)
    
    return NLToCircuitPipeline(llm_client=llm_client, component_db=None)


# Module-level schema exports for testing
REQUIREMENT_SCHEMA = RequirementParser.REQUIREMENT_SCHEMA
SPECIFICATION_SCHEMA = CircuitSpecificationGenerator.SPEC_SCHEMA