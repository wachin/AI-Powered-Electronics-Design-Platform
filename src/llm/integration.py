"""
LLM Integration for AI-Powered Electronics Design Platform.

Provides natural language to CircuitIR conversion using LLM providers.
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
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
class CircuitRequirement:
    """Structured circuit requirements parsed from natural language."""
    circuit_type: str
    description: str
    input_voltage: Optional[float] = None
    output_voltage: Optional[float] = None
    current: Optional[float] = None
    features: List[str] = field(default_factory=list)
    constraints: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CircuitSpecification:
    """Complete circuit specification ready for CircuitIR generation."""
    requirements: CircuitRequirement
    topology: str
    components: List[Dict[str, Any]] = field(default_factory=list)
    connections: List[Dict[str, str]] = field(default_factory=list)
    power_domains: Dict[str, Dict[str, float]] = field(default_factory=dict)
    design_notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


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
            "current": {"type": ["number", "null"]},
            "features": {"type": "array", "items": {"type": "string"}},
            "constraints": {"type": "object"},
        },
        "required": ["circuit_type", "description"]
    }

    async def parse(self, natural_language: str) -> CircuitRequirement:
        """Parse natural language into structured circuit requirements."""
        system_prompt = """You are an expert electronics engineer. Parse the user's natural language description into structured circuit requirements.
        
        Extract the following information:
        - circuit_type: One of [ldo_regulator, buck_converter, boost_converter, led_driver, mcu_board, generic]
        - input_voltage: Input voltage in volts (if specified)
        - output_voltage: Output voltage in volts (if specified)  
        - current: Output current in amps (if specified)
        - features: List of features mentioned (e.g., ["led_indicator", "enable_pin", "soft_start"])
        - constraints: Any additional constraints (size, cost, temperature, etc.)
        
        If a value is not mentioned, use null.
        Be precise and only extract what is explicitly stated or strongly implied."""

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
                        "current": {"type": ["number", "null"]},
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
            current=current,
        )


class CircuitSpecificationGenerator:
    """Generates detailed circuit specification from requirements."""
    
    def __init__(self, llm_client: LLMClient, component_db):
        self.llm = llm_client
        self.db = component_db

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
            "design_notes": {"type": "array", "items": {"type": "string"}},
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
        "required": ["topology", "components"]
    }

    async def generate(self, requirements: CircuitRequirement) -> Dict[str, Any]:
        """Generate detailed circuit specification from requirements."""
        # For now, use rule-based generation (LLM can be added later)
        return self._generate_spec(requirements)

    def _generate_spec(self, req: CircuitRequirement) -> Dict[str, Any]:
        """Rule-based specification generation."""
        spec = {
            "topology": "",
            "components": [],
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
        i_out = req.current or 0.5
        
        # Select LDO
        ldo = self._select_ldo(v_out, i_out)
        caps = self._select_caps()
        led = self._select_led()
        res = self._select_resistor()
        
        return {
            "topology": "linear_ldo",
            "components": [
                {
                    "role": "regulator",
                    "mpn": ldo.get("mpn", "AMS1117-3.3"),
                    "manufacturer": ldo.get("manufacturer", "AMS"),
                    "value": f"{v_out}V",
                    "package": ldo.get("package", "SOT-223"),
                    "reasoning": f"LDO regulator {v_out}V {i_out}A"
                },
                {
                    "role": "input_capacitor",
                    "mpn": caps[0].get("mpn", "C-10uF-0805"),
                    "manufacturer": caps[0].get("manufacturer", "Yageo"),
                    "value": caps[0].get("value", "10uF"),
                    "package": caps[0].get("package", "0805"),
                    "reasoning": "Input decoupling capacitor"
                },
                {
                    "role": "output_capacitor",
                    "mpn": caps[1].get("mpn", "C-22uF-0805"),
                    "manufacturer": caps[1].get("manufacturer", "Yageo"),
                    "value": caps[1].get("value", "22uF"),
                    "package": caps[1].get("package", "0805"),
                    "reasoning": "Output stability capacitor"
                },
                {
                    "role": "led_indicator",
                    "mpn": led.get("mpn", "LED-GREEN-0805"),
                    "manufacturer": led.get("manufacturer", "Lite-On"),
                    "value": "Green",
                    "package": "0805",
                    "reasoning": "Power-on indicator"
                },
                {
                    "role": "current_limit_resistor",
                    "mpn": res.get("mpn", "R-330-0805"),
                    "manufacturer": res.get("manufacturer", "Yageo"),
                    "value": "330",
                    "package": "0805",
                    "reasoning": "LED current limiting resistor"
                }
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
    
    def __init__(self, llm_provider: str = "mock", component_db=None):
        self.llm_client = create_llm_client("mock")  # Use mock for now
        self.parser = RequirementParser(self.llm_client)
        self.spec_generator = CircuitSpecificationGenerator(self.llm_client, None)
        self.orchestrator = None  # Will be set externally
        
    async def nl_to_circuit_spec(self, prompt: str) -> dict:
        """Process natural language prompt through full pipeline to circuit spec."""
        # Step 1: Parse requirements
        requirements = await self.parser.parse(prompt)
        
        # Step 2: Generate specification
        spec = await self.spec_generator.generate(requirements)
        
        # Step 3: Generate CircuitIR (simplified - would use spec to build CircuitIR)
        circuit_ir = self._spec_to_circuit_ir({})
        
        return {
            "requirements": requirements,
            "specification": self._spec_to_dict({}),
            "circuit_ir": {}
        }
        
    async def process(self, prompt: str, project_name: str = "design") -> dict:
        """Process natural language prompt through full pipeline."""
        # Step 1: Parse requirements
        requirements = await self.parser.parse(prompt)
        
        # Step 2: Generate specification
        spec = await self.spec_generator.generate(requirements)
        
        # Step 3: Generate CircuitIR (simplified - would use spec to build CircuitIR)
        circuit_ir = self._spec_to_circuit_ir({})
        
        # Step 4: Generate KiCad files (via orchestrator)
        if self.orchestrator:
            from src.agents.orchestrator import DesignRequest
            request = DesignRequest(prompt="", project_name="generated")
            request.prompt = "Generated from NL"
            summary = self.orchestrator.process_request(request, output_dir)
            
            return {
                "requirements": requirements,
                "specification": spec,
                "output_files": summary.generated_files,
                "bom": summary.bom
            }
        
        return {
            "requirements": requirements,
            "specification": spec,
        }

    def _spec_to_circuit_ir(self, spec) -> 'CircuitIR':
        """Convert specification to CircuitIR (simplified)."""
        from src.core.circuit_ir import CircuitIR, Component, ComponentType, PinType
        circuit = CircuitIR(name="Generated Circuit")
        # Would build full CircuitIR from spec - simplified for now
        return circuit

    def set_orchestrator(self, orchestrator):
        self.orchestrator = orchestrator


def create_nl_pipeline(llm_provider: str = "mock") -> NLToCircuitPipeline:
    """Factory function to create NL pipeline."""
    return NLToCircuitPipeline(llm_provider=llm_provider)


# Module-level schema exports for testing
REQUIREMENT_SCHEMA = RequirementParser.REQUIREMENT_SCHEMA
SPECIFICATION_SCHEMA = CircuitSpecificationGenerator.SPEC_SCHEMA