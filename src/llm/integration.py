"""
LLM Integration for AI-Powered Electronics Design Platform.

Provides structured natural language understanding for circuit requirements.
Uses JSON schema for reliable structured output.
"""

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Literal
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class LLMProvider(Enum):
    OLLAMA = "ollama"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    MOCK = "mock"


@dataclass
class CircuitRequirement:
    """Structured circuit requirements extracted from natural language."""
    circuit_type: str  # "ldo_regulator", "buck_converter", "led_driver", "mcu_board", etc.
    description: str
    
    # Power requirements
    input_voltage: Optional[float] = None
    input_voltage_range: Optional[tuple] = None
    output_voltage: Optional[float] = None
    output_current: Optional[float] = None
    output_power: Optional[float] = None
    
    # Features
    features: List[str] = field(default_factory=list)  # ["led_indicator", "enable_pin", "soft_start"]
    
    # Constraints
    package_preference: Optional[str] = None  # "SOT-23", "QFN", "TO-220"
    budget_target: Optional[float] = None
    size_constraint: Optional[str] = None  # "compact", "standard"
    efficiency_target: Optional[float] = None
    
    # Environment
    operating_temp_range: Optional[tuple] = None
    automotive_grade: bool = False
    
    # Special requirements
    special_requirements: List[str] = field(default_factory=list)


@dataclass
class ComponentSelection:
    """Selected component with reasoning."""
    role: str  # "regulator", "input_cap", "output_cap", "inductor", "feedback_resistor"
    mpn: str
    manufacturer: str
    value: str
    package: str
    reasoning: str
    alternatives: List[str] = field(default_factory=list)
    estimated_cost: float = 0.0


@dataclass
class CircuitSpecification:
    """Complete circuit specification ready for Circuit IR generation."""
    requirements: CircuitRequirement
    topology: str  # "linear_ldo", "buck_sync", "buck_async", "boost", "charge_pump"
    components: List[ComponentSelection] = field(default_factory=list)
    netlist_hints: Dict[str, Any] = field(default_factory=dict)
    design_notes: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)


class LLMClient(ABC):
    """Abstract base for LLM providers."""
    
    @abstractmethod
    def complete(self, prompt: str, schema: Dict[str, Any], system_prompt: str = "") -> Dict[str, Any]:
        """Generate structured output conforming to schema."""
        pass
    
    @abstractmethod
    def is_available(self) -> bool:
        """Check if provider is available."""
        pass


class MockLLMClient(LLMClient):
    """Mock client for testing without API keys."""
    
    def is_available(self) -> bool:
        return True
    
    def complete(self, prompt: str, schema: Dict[str, Any], system_prompt: str = "") -> Dict[str, Any]:
        """Return mock structured response based on prompt keywords."""
        prompt_lower = prompt.lower()
        
        # Detect circuit type
        if "ldo" in prompt_lower or "linear regulator" in prompt_lower:
            return self._mock_ldo_response(prompt)
        elif "buck" in prompt_lower or "step.down" in prompt_lower:
            return self._mock_buck_response(prompt)
        elif "boost" in prompt_lower or "step.up" in prompt_lower:
            return self._mock_boost_response(prompt)
        elif "led" in prompt_lower:
            return self._mock_led_response(prompt)
        else:
            return self._mock_generic_response(prompt)
    
    def _mock_ldo_response(self, prompt: str) -> Dict[str, Any]:
        import re
        prompt_lower = prompt.lower()
        v_in = 5.0
        v_out = 3.3
        i_out = 0.5
        
        # Try to extract voltages
        v_in_match = re.search(r'(\d+(?:\.\d+)?)\s*v\s*(?:to|->|→)\s*', prompt_lower)
        if v_in_match:
            v_in = float(v_in_match.group(1))
        v_out_match = re.search(r'(?:to|->|→)\s*(\d+(?:\.\d+)?)\s*v', prompt_lower)
        if v_out_match:
            v_out = float(v_out_match.group(1))
        i_match = re.search(r'(\d+(?:\.\d+)?)\s*[ma]', prompt_lower)
        if i_match:
            i_out = float(i_match.group(1)) / (1000 if 'ma' in prompt_lower else 1)
        
        has_led = "led" in prompt_lower
        
        components = [
            {
                "role": "regulator",
                "mpn": "AMS1117-3.3" if v_out == 3.3 else "LM7805",
                "manufacturer": "AMS" if v_out == 3.3 else "TI",
                "value": f"{v_out}V",
                "package": "SOT-223",
                "reasoning": f"LDO regulator {v_in}V to {v_out}V, {i_out}A",
                "alternatives": ["LM2940", "MIC5219"],
                "estimated_cost": 0.15
            },
            {
                "role": "input_capacitor",
                "mpn": "CC0805KRX7R9BB106",
                "manufacturer": "Yageo",
                "value": "10uF",
                "package": "0805",
                "reasoning": "Input decoupling capacitor",
                "alternatives": [],
                "estimated_cost": 0.02
            },
            {
                "role": "output_capacitor",
                "mpn": "CC0805KRX7R9BB106",
                "manufacturer": "Yageo",
                "value": "10uF",
                "package": "0805",
                "reasoning": "Output stability capacitor",
                "alternatives": [],
                "estimated_cost": 0.02
            },
        ]
        
        if has_led:
            components.extend([
                {
                    "role": "led_indicator",
                    "mpn": "LTST-C190KGKT",
                    "manufacturer": "Lite-On",
                    "value": "Green",
                    "package": "0805",
                    "reasoning": "Power-on indicator LED",
                    "alternatives": [],
                    "estimated_cost": 0.04
                },
                {
                    "role": "led_resistor",
                    "mpn": "RC0805FR-0710KL",
                    "manufacturer": "Yageo",
                    "value": "10k",
                    "package": "0805",
                    "reasoning": "LED current limiting resistor",
                    "alternatives": [],
                    "estimated_cost": 0.01
                },
            ])
        
        return {
            "circuit_type": "ldo_regulator",
            "description": prompt,
            "input_voltage": v_in,
            "output_voltage": v_out,
            "output_current": i_out,
            "features": ["led_indicator"] if has_led else [],
            "components": components,
            "topology": "linear_ldo",
            "design_notes": [
                f"LDO dropout: {v_in - v_out}V",
                f"Power dissipation: {(v_in - v_out) * i_out:.2f}W",
                "Ensure adequate thermal relief"
            ],
            "warnings": [
                "Check thermal dissipation for high current",
                "Verify dropout voltage at max current"
            ] if (v_in - v_out) * i_out > 0.5 else []
        }
    
    def _mock_buck_response(self, prompt: str) -> Dict[str, Any]:
        return {
            "circuit_type": "buck_converter",
            "description": prompt,
            "input_voltage": 12.0,
            "output_voltage": 5.0,
            "output_current": 3.0,
            "components": [
                {
                    "role": "controller",
                    "mpn": "LM2596S-5.0",
                    "manufacturer": "TI",
                    "value": "5V",
                    "package": "TO-220-5",
                    "reasoning": "Buck converter controller",
                    "alternatives": ["LM2675", "TPS5430"],
                    "estimated_cost": 0.85
                },
                {
                    "role": "inductor",
                    "mpn": "SRR1280-470M",
                    "manufacturer": "Bourns",
                    "value": "47uH",
                    "package": "12x12mm",
                    "reasoning": "Buck converter inductor",
                    "alternatives": [],
                    "estimated_cost": 0.45
                },
                {
                    "role": "input_capacitor",
                    "mpn": "CC0805KRX7R9BB106",
                    "manufacturer": "Yageo",
                    "value": "10uF",
                    "package": "0805",
                    "reasoning": "Input decoupling",
                    "alternatives": [],
                    "estimated_cost": 0.02
                },
                {
                    "role": "output_capacitor",
                    "mpn": "CC0805KRX7R9BB106",
                    "manufacturer": "Yageo",
                    "value": "100uF",
                    "package": "1206",
                    "reasoning": "Output filtering",
                    "alternatives": [],
                    "estimated_cost": 0.05
                },
                {
                    "role": "freewheel_diode",
                    "mpn": "SS34",
                    "manufacturer": "Vishay",
                    "value": "3A/40V",
                    "package": "SMA",
                    "reasoning": "Freewheeling diode",
                    "alternatives": [],
                    "estimated_cost": 0.08
                },
            ],
            "topology": "buck_async",
            "design_notes": ["Asynchronous buck converter", "Consider sync rectification for >90% efficiency"],
            "warnings": ["Diode loss significant at high current"]
        }
    
    def _mock_boost_response(self, prompt: str) -> Dict[str, Any]:
        return {
            "circuit_type": "boost_converter",
            "description": prompt,
            "input_voltage": 3.3,
            "output_voltage": 5.0,
            "output_current": 1.0,
            "components": [
                {
                    "role": "controller",
                    "mpn": "MT3608",
                    "manufacturer": "Aerosemi",
                    "value": "Adjustable",
                    "package": "SOT-23-6",
                    "reasoning": "Boost converter IC",
                    "alternatives": ["LM2731", "TPS61070"],
                    "estimated_cost": 0.35
                },
                {
                    "role": "inductor",
                    "mpn": "SRR0604-100M",
                    "manufacturer": "Bourns",
                    "value": "10uH",
                    "package": "6x6mm",
                    "reasoning": "Boost inductor",
                    "alternatives": [],
                    "estimated_cost": 0.25
                },
            ],
            "topology": "boost",
            "design_notes": ["Boost converter for voltage step-up"],
            "warnings": ["Output current limited by inductor saturation"]
        }
    
    def _mock_led_response(self, prompt: str) -> Dict[str, Any]:
        return {
            "circuit_type": "led_driver",
            "description": prompt,
            "input_voltage": 5.0,
            "output_current": 0.02,
            "components": [
                {
                    "role": "led",
                    "mpn": "LTST-C190KGKT",
                    "manufacturer": "Lite-On",
                    "value": "Green",
                    "package": "0805",
                    "reasoning": "Indicator LED",
                    "alternatives": [],
                    "estimated_cost": 0.04
                },
                {
                    "role": "current_limit_resistor",
                    "mpn": "RC0805FR-0710KL",
                    "manufacturer": "Yageo",
                    "value": "10k",
                    "package": "0805",
                    "reasoning": "Current limiting resistor",
                    "alternatives": [],
                    "estimated_cost": 0.01
                },
            ],
            "topology": "series_resistor",
            "design_notes": ["Simple series resistor LED driver"],
            "warnings": ["Not suitable for high-power LEDs"]
        }
    
    def _mock_generic_response(self, prompt: str) -> Dict[str, Any]:
        return {
            "circuit_type": "generic",
            "description": prompt,
            "components": [],
            "topology": "unknown",
            "design_notes": ["Unable to determine circuit type"],
            "warnings": ["Please specify circuit type more clearly"]
        }


class OllamaLLMClient(LLMClient):
    """Ollama local LLM client."""
    
    def __init__(self, model: str = "llama3.1", base_url: str = "http://localhost:11434"):
        self.model = model
        self.base_url = base_url
        self._available = None
    
    def is_available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import requests
            resp = requests.get(f"{self.base_url}/api/tags", timeout=2)
            self._available = resp.status_code == 200
            return self._available
        except Exception:
            self._available = False
            return False
    
    def complete(self, prompt: str, schema: Dict[str, Any], system_prompt: str = "") -> Dict[str, Any]:
        import requests
        
        # Build prompt with schema instruction
        schema_str = json.dumps(schema, indent=2)
        full_prompt = f"""{system_prompt}

User: {prompt}

Respond with valid JSON matching this schema:
{schema_str}

Output only the JSON object, no additional text."""
        
        resp = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.model,
                "prompt": full_prompt,
                "format": "json",
                "stream": False,
                "options": {"temperature": 0.1}
            },
            timeout=60
        )
        resp.raise_for_status()
        result = resp.json()
        
        try:
            return json.loads(result["response"])
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response: {e}")
            logger.error(f"Raw response: {result['response'][:500]}")
            raise


def get_llm_client(provider: LLMProvider = LLMProvider.MOCK, **kwargs) -> LLMClient:
    """Factory function to get LLM client."""
    if provider == LLMProvider.MOCK:
        return MockLLMClient()
    elif provider == LLMProvider.OLLAMA:
        return OllamaLLMClient(**kwargs)
    else:
        raise ValueError(f"Provider {provider} not implemented")


# JSON Schemas for structured output

REQUIREMENT_SCHEMA = {
    "type": "object",
    "properties": {
        "circuit_type": {"type": "string", "enum": ["ldo_regulator", "buck_converter", "boost_converter", "led_driver", "mcu_board", "generic"]},
        "description": {"type": "string"},
        "input_voltage": {"type": ["number", "null"]},
        "input_voltage_range": {"type": ["array", "null"], "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
        "output_voltage": {"type": ["number", "null"]},
        "output_current": {"type": ["number", "null"]},
        "output_power": {"type": ["number", "null"]},
        "features": {"type": "array", "items": {"type": "string"}},
        "package_preference": {"type": ["string", "null"]},
        "budget_target": {"type": ["number", "null"]},
        "size_constraint": {"type": ["string", "null"]},
        "efficiency_target": {"type": ["number", "null"]},
        "operating_temp_range": {"type": ["array", "null"], "items": {"type": "number"}, "minItems": 2, "maxItems": 2},
        "automotive_grade": {"type": "boolean"},
        "special_requirements": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["circuit_type", "description"]
}

SPECIFICATION_SCHEMA = {
    "type": "object",
    "properties": {
        "circuit_type": {"type": "string"},
        "description": {"type": "string"},
        "input_voltage": {"type": ["number", "null"]},
        "output_voltage": {"type": ["number", "null"]},
        "output_current": {"type": ["number", "null"]},
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
                    "alternatives": {"type": "array", "items": {"type": "string"}},
                    "estimated_cost": {"type": "number"}
                },
                "required": ["role", "mpn", "manufacturer", "value", "package", "reasoning"]
            }
        },
        "design_notes": {"type": "array", "items": {"type": "string"}},
        "warnings": {"type": "array", "items": {"type": "string"}}
    },
    "required": ["circuit_type", "description", "topology", "components"]
}


def parse_requirements(prompt: str, provider: LLMProvider = LLMProvider.MOCK, **kwargs) -> CircuitRequirement:
    """Parse natural language into structured CircuitRequirement."""
    client = get_llm_client(provider, **kwargs)
    
    system = """You are an expert electronics engineer. Parse the user's natural language description into structured circuit requirements. Be precise with voltages, currents, and component types."""
    
    result = client.complete(prompt, REQUIREMENT_SCHEMA, system)
    
    return CircuitRequirement(
        circuit_type=result["circuit_type"],
        description=result["description"],
        input_voltage=result.get("input_voltage"),
        input_voltage_range=tuple(result["input_voltage_range"]) if result.get("input_voltage_range") else None,
        output_voltage=result.get("output_voltage"),
        output_current=result.get("output_current"),
        output_power=result.get("output_power"),
        features=result.get("features", []),
        package_preference=result.get("package_preference"),
        budget_target=result.get("budget_target"),
        size_constraint=result.get("size_constraint"),
        efficiency_target=result.get("efficiency_target"),
        operating_temp_range=tuple(result["operating_temp_range"]) if result.get("operating_temp_range") else None,
        automotive_grade=result.get("automotive_grade", False),
        special_requirements=result.get("special_requirements", [])
    )


def generate_specification(requirements: CircuitRequirement, provider: LLMProvider = LLMProvider.MOCK, **kwargs) -> CircuitSpecification:
    """Generate detailed circuit specification from requirements."""
    client = get_llm_client(provider, **kwargs)
    
    system = """You are an expert power electronics engineer. Generate a complete circuit specification including topology selection, component selection with MPNs, and design rationale. Consider efficiency, thermal, cost, and manufacturability."""
    
    # Build detailed prompt with requirements
    req_dict = {
        "circuit_type": requirements.circuit_type,
        "description": requirements.description,
        "input_voltage": requirements.input_voltage,
        "output_voltage": requirements.output_voltage,
        "output_current": requirements.output_current,
        "features": requirements.features,
        "package_preference": requirements.package_preference,
    }
    
    prompt = f"Design a circuit with these requirements:\n{json.dumps(req_dict, indent=2)}"
    
    result = client.complete(prompt, SPECIFICATION_SCHEMA, system)
    
    # Convert to dataclasses
    components = [
        ComponentSelection(
            role=c["role"],
            mpn=c["mpn"],
            manufacturer=c["manufacturer"],
            value=c["value"],
            package=c["package"],
            reasoning=c["reasoning"],
            alternatives=c.get("alternatives", []),
            estimated_cost=c.get("estimated_cost", 0.0)
        )
        for c in result["components"]
    ]
    
    return CircuitSpecification(
        requirements=requirements,
        topology=result["topology"],
        components=components,
        design_notes=result.get("design_notes", []),
        warnings=result.get("warnings", [])
    )


def nl_to_circuit_spec(prompt: str, provider: LLMProvider = LLMProvider.MOCK, **kwargs) -> CircuitSpecification:
    """End-to-end: natural language → CircuitSpecification."""
    requirements = parse_requirements(prompt, provider, **kwargs)
    return generate_specification(requirements, provider, **kwargs)