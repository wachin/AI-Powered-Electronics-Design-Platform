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
                        "circuit_type": {"type": "string", "enum": ["ldo_regulator", "buck_converter", "boost_converter", "led_driver", "mcu_board", "generic"]},
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
            if not result.get("topology") or not result.get("components"):
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
            
            circuit.connect("D1", "A", "R1_1")
            circuit.connect("R1", "1", "R1_1")
            circuit.connect("R1", "2", "VIN")
            circuit.connect("D1", "K", "GND")
        
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