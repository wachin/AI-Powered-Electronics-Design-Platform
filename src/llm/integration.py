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
    LLMResponseError,
)
from src.core.circuit_ir import CircuitIR, Component, ComponentType, PinType, PowerDomain
from src.core.circuit_builder import CircuitIRBuilder, BuildReport
from src.llm.validation import DesignValidator, DesignValidationReport
from src.components.database import ComponentDatabase

logger = logging.getLogger(__name__)


def _report_score(report: DesignValidationReport) -> int:
    """
    Rank validation reports so repair keeps the best attempt, never a worse one.

    Fewest errors always wins: a larger circuit that violates the electrical
    rules is worse than a smaller circuit that does not. Component count is
    only a tie-breaker between attempts with the same error count, so a more
    complete design is preferred when both are equally correct.
    """
    error_count = len(report.errors)
    component_count = (
        len(report.circuit.components) if report.circuit is not None else 0
    )
    return -error_count * 1000 + min(component_count, 999)


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

    def __contains__(self, key: str) -> bool:
        return hasattr(self, key)

    def get(self, key: str, default=None) -> Any:
        return getattr(self, key, default)

    def keys(self):
        return ["role", "mpn", "manufacturer", "value", "package", "reasoning"]

    def __iter__(self):
        """Iterate keys so dict(spec) and mapping consumers work."""
        return iter(self.keys())

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
    # Populated by the validated generation path: build report, ERC results and
    # the list of problems that were found (and either repaired or reported).
    validation: Optional[Dict[str, Any]] = None
    repair_attempts: int = 0
    used_llm: bool = True

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

    def __init__(self, llm_client: LLMClient, deterministic: bool = False):
        """
        Args:
            llm_client: The model to ask when ``deterministic`` is False.
            deterministic: Parse the prompt with rules instead of asking a model.

                This exists because the mock client returns *canned* requirements
                (5 V in, 3.3 V out, 0.5 A) rather than reading the prompt — so
                running the CLI with its default ``--provider mock`` discarded
                whatever the user typed. "Design a 12V to 3.3V LDO" produced a
                5 V design, and every later stage — the electrical review, the
                trace widths, the purchase list — validated that wrong design
                without saying so.

                The rule-based parser reads the prompt for real, so the default
                path now honours it.
        """
        self.llm = llm_client
        self.deterministic = deterministic

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
        if self.deterministic:
            return self._fallback_parse(natural_language)

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
        """
        Keyword-based requirement parser used when the LLM is unavailable.

        This deliberately errs toward recognising a topology rather than
        defaulting to "generic", because a mis-classified request produces a
        confidently wrong circuit.
        """
        import re

        text_lower = text.lower()

        circuit_type = "generic"
        # Switching topologies are checked before the linear ones, because
        # "regulador conmutado" and "regulador lineal" both contain "regulador".
        # Spanish terms are listed alongside the English ones: this project is
        # used in both, and "un regulador de 12V a 3.3V" was being classified as
        # "generic" while the voltages were read correctly — a design that
        # silently ignores the topology the user asked for.
        switching_down = (
            "buck", "step-down", "step down", "reductor",
            # A switching regulator with no direction named is taken as a buck:
            # step-down is what the overwhelming majority of them are, and
            # "generic" would silently ignore the topology.
            "conmutado", "switching", "conmutada",
        )
        switching_up = ("boost", "step-up", "step up", "elevador")

        if any(k in text_lower for k in switching_down):
            circuit_type = "buck_converter"
        elif any(k in text_lower for k in switching_up):
            circuit_type = "boost_converter"
        elif any(k in text_lower for k in ["ldo", "linear regulator", "regulador lineal", "lineal"]):
            circuit_type = "ldo_regulator"
        elif any(k in text_lower for k in ["regulador", "regulator"]):
            # A regulator with no topology named is usually a linear one; the
            # switching branches above have already taken the exceptions.
            circuit_type = "ldo_regulator"
        elif "phono" in text_lower or "riaa" in text_lower:
            circuit_type = "phono_preamp"
        elif "led" in text_lower:
            # Any mention of an LED (with a resistor, "driver", "indicator")
            # is an LED circuit; the regulator branches above win when the
            # prompt also asks for a regulator.
            circuit_type = "led_driver"

        def _number(pattern: str) -> Optional[float]:
            match = re.search(pattern, text, re.IGNORECASE)
            if not match:
                return None
            try:
                return float(match.group(1))
            except (TypeError, ValueError):
                return None

        # "5V to 3.3V", "5v->3.3v", "5 V → 3.3 V", "12V a 3.3V", "de 12V a 3.3V".
        # The separator list includes the Spanish "a" because this project is used
        # in Spanish as much as in English, and "12V a 3.3V" is unambiguous.
        # `\ba\b` cannot match the "a" inside "at" or "and", because neither has a
        # word boundary after it.
        span = re.search(
            r"(\d+(?:\.\d+)?)\s*v\s*(?:to|->|→|hasta|\ba\b|-)\s*"
            r"(\d+(?:\.\d+)?)\s*v?",
            text,
            re.IGNORECASE,
        )
        v_in: Optional[float] = None
        v_out: Optional[float] = None
        assumptions: List[str] = []
        if span:
            v_in = float(span.group(1))
            v_out = float(span.group(2))
        else:
            v_in = _number(r"(\d+(?:\.\d+)?)\s*v\s*(?:in|input)")
            v_out = _number(r"(\d+(?:\.\d+)?)\s*v\s*(?:out|output)")

            # A single voltage with no range: for a regulator it is the output,
            # for an LED circuit it is the supply. Said out loud, because a
            # guessed rail is the difference between a design that works and one
            # that does not.
            if v_out is None and v_in is None:
                single = _number(r"(\d+(?:\.\d+)?)\s*v\b")
                if single is not None:
                    if circuit_type in ("ldo_regulator", "buck_converter", "boost_converter"):
                        v_out = single
                        assumptions.append(
                            f"only one voltage was stated ({single:g} V); treated as "
                            f"the output, with the input left to the default"
                        )
                    elif circuit_type == "led_driver":
                        v_in = single
                        assumptions.append(
                            f"only one voltage was stated ({single:g} V); treated as "
                            f"the supply for the LED circuit"
                        )

        # "500mA", "3A", "1.5 A"
        current = _number(r"(\d+(?:\.\d+)?)\s*(?:a|amp|amps|ampere|amperes)\b")
        milliamps = _number(r"(\d+(?:\.\d+)?)\s*ma\b")
        if milliamps is not None:
            current = milliamps / 1000.0

        features: List[str] = []
        if "led" in text_lower:
            features.append("led_indicator")
        if any(k in text_lower for k in ["decoupling", "bypass", "filter"]):
            features.append("decoupling")

        # The defaults the specification generator applies. Filling them here
        # means the caller is told what was assumed instead of discovering it in
        # the finished design.
        if circuit_type in ("ldo_regulator", "buck_converter", "boost_converter"):
            if v_in is None:
                v_in = 5.0
                assumptions.append("no input voltage was stated; assumed 5 V")
            if v_out is None:
                default_out = 3.3 if circuit_type == "ldo_regulator" else 5.0
                v_out = default_out
                assumptions.append(
                    f"no output voltage was stated; assumed {default_out:g} V"
                )
            if current is None:
                current = 0.5
                assumptions.append("no current was stated; assumed 0.5 A")

        return CircuitRequirement(
            circuit_type=circuit_type,
            description=text.strip(),
            input_voltage=v_in,
            output_voltage=v_out,
            output_current=current,
            features=features,
            constraints={"assumptions": assumptions} if assumptions else {},
        )


class CircuitSpecificationGenerator:
    """Generates detailed circuit specification from requirements."""
    
    def __init__(
        self,
        llm_client: LLMClient,
        component_db=None,
        use_llm: bool = True,
        allow_fallback: bool = True,
    ):
        self.llm = llm_client
        self.db = component_db
        # `use_llm=False` selects the rule-based generator outright. It is what
        # the deterministic path sets, so that a run with no model never asks a
        # mock one for a canned answer.
        self.use_llm = use_llm
        # When False, an LLM failure raises instead of silently producing a
        # canned template. Callers that must not fake a design set this False.
        self.allow_fallback = allow_fallback
        # Bounds generation so a slow local model cannot run for many minutes
        # on a single request.
        self.default_max_tokens = 2048

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
                {"role": "regulator", "mpn": "", "lcsc": "", "value": "3.3V", "package": "SOT-223", "reasoning": "LDO regulator 5V to 3.3V, 1A"},
                {"role": "input_capacitor", "mpn": "", "lcsc": "", "value": "10uF", "package": "0805", "reasoning": "Input decoupling capacitor"},
                {"role": "output_capacitor", "mpn": "", "lcsc": "", "value": "10uF", "package": "0805", "reasoning": "Output stability capacitor"},
                {"role": "led_indicator", "mpn": "", "lcsc": "", "value": "Green", "package": "0805", "reasoning": "Power-on indicator LED"},
                {"role": "led_resistor", "mpn": "", "lcsc": "", "value": "10k", "package": "0805", "reasoning": "LED current limiting resistor"}
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
            "warnings": []
        },
        "buck_converter": {
            "topology": "Asynchronous Buck Converter",
            "components": [
                {"role": "controller", "mpn": "", "lcsc": "", "value": "5V", "package": "TO-220-5", "reasoning": "Buck converter controller"},
                {"role": "inductor", "mpn": "", "lcsc": "", "value": "47uH", "package": "12x12mm", "reasoning": "Buck inductor"},
                {"role": "input_capacitor", "mpn": "", "lcsc": "", "value": "10uF", "package": "0805", "reasoning": "Input decoupling"},
                {"role": "output_capacitor", "mpn": "", "lcsc": "", "value": "100uF", "package": "1206", "reasoning": "Output filtering"},
                {"role": "freewheel_diode", "mpn": "", "lcsc": "", "value": "3A/40V", "package": "SMA", "reasoning": "Freewheeling diode"}
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
                {"role": "led", "mpn": "", "lcsc": "", "value": "Green", "package": "0805", "reasoning": "Green indicator LED"},
                {"role": "current_limit_resistor", "mpn": "", "lcsc": "", "value": "1.5k", "package": "0805", "reasoning": "Current limiting resistor for 20mA"}
            ],
            "connections": [
                {"from": "VIN", "to": "R1", "net": "VIN"},
                {"from": "R1", "to": "D1", "net": "D1_A"},
                {"from": "D1", "to": "GND", "net": "GND"}
            ],
            "power_domains": {"VIN": 5.0, "GND": 0.0},
            "design_notes": ["Simple series resistor drive", "Resistor value: (5V - 2.1V) / 0.02A = 145 ohm, use 1.5k for lower brightness"],
            "warnings": []
        },
        "phono_preamp": {
            "topology": "Stereo RIAA Phono Preamplifier (Moving Magnet)",
            "components": [
                {"role": "input_jack_left", "mpn": "", "lcsc": "", "value": "RCA Jack", "package": "PTH", "reasoning": "Left channel RCA input"},
                {"role": "input_capacitor_left", "mpn": "", "lcsc": "", "value": "100nF", "package": "0603", "reasoning": "Left input DC blocking capacitor"},
                {"role": "input_resistor_left", "mpn": "", "lcsc": "", "value": "47k", "package": "0603", "reasoning": "Moving-magnet cartridge load resistor"},
                {"role": "riaa_r1_left", "mpn": "", "lcsc": "", "value": "3.3k", "package": "0603", "reasoning": "RIAA 3180us network resistor"},
                {"role": "riaa_c1_left", "mpn": "", "lcsc": "", "value": "47nF", "package": "0603", "reasoning": "RIAA 3180us network capacitor"},
                {"role": "riaa_r2_left", "mpn": "", "lcsc": "", "value": "750", "package": "0603", "reasoning": "RIAA 318us network resistor"},
                {"role": "riaa_c2_left", "mpn": "", "lcsc": "", "value": "100nF", "package": "0603", "reasoning": "RIAA 318us network capacitor"},
                {"role": "riaa_r3_left", "mpn": "", "lcsc": "", "value": "1.2k", "package": "0603", "reasoning": "RIAA 75us network resistor"},
                {"role": "riaa_c3_left", "mpn": "", "lcsc": "", "value": "22nF", "package": "0603", "reasoning": "RIAA 75us network capacitor"},
                {"role": "gain_rf_left", "mpn": "", "lcsc": "", "value": "1M", "package": "0603", "reasoning": "Feedback resistor, approximately 40dB gain"},
                {"role": "output_capacitor_left", "mpn": "", "lcsc": "", "value": "1uF", "package": "0603", "reasoning": "Left output DC blocking capacitor"},
                {"role": "output_jack_left", "mpn": "", "lcsc": "", "value": "RCA Jack", "package": "PTH", "reasoning": "Left channel RCA output"},
                {"role": "input_jack_right", "mpn": "", "lcsc": "", "value": "RCA Jack", "package": "PTH", "reasoning": "Right channel RCA input"},
                {"role": "input_capacitor_right", "mpn": "", "lcsc": "", "value": "100nF", "package": "0603", "reasoning": "Right input DC blocking capacitor"},
                {"role": "input_resistor_right", "mpn": "", "lcsc": "", "value": "47k", "package": "0603", "reasoning": "Moving-magnet cartridge load resistor"},
                {"role": "riaa_r1_right", "mpn": "", "lcsc": "", "value": "3.3k", "package": "0603", "reasoning": "RIAA 3180us network resistor"},
                {"role": "riaa_c1_right", "mpn": "", "lcsc": "", "value": "47nF", "package": "0603", "reasoning": "RIAA 3180us network capacitor"},
                {"role": "riaa_r2_right", "mpn": "", "lcsc": "", "value": "750", "package": "0603", "reasoning": "RIAA 318us network resistor"},
                {"role": "riaa_c2_right", "mpn": "", "lcsc": "", "value": "100nF", "package": "0603", "reasoning": "RIAA 318us network capacitor"},
                {"role": "riaa_r3_right", "mpn": "", "lcsc": "", "value": "1.2k", "package": "0603", "reasoning": "RIAA 75us network resistor"},
                {"role": "riaa_c3_right", "mpn": "", "lcsc": "", "value": "22nF", "package": "0603", "reasoning": "RIAA 75us network capacitor"},
                {"role": "gain_rf_right", "mpn": "", "lcsc": "", "value": "1M", "package": "0603", "reasoning": "Feedback resistor, approximately 40dB gain"},
                {"role": "output_capacitor_right", "mpn": "", "lcsc": "", "value": "1uF", "package": "0603", "reasoning": "Right output DC blocking capacitor"},
                {"role": "output_jack_right", "mpn": "", "lcsc": "", "value": "RCA Jack", "package": "PTH", "reasoning": "Right channel RCA output"},
                {"role": "opamp", "mpn": "", "lcsc": "", "value": "OPA2134", "package": "DIP-8", "reasoning": "Dual low-noise audio op-amp, one unit per channel"},
                {"role": "psu_cap_large", "mpn": "", "lcsc": "", "value": "470uF/25V", "package": "Radial", "reasoning": "Supply bulk filtering capacitor"},
                {"role": "psu_cap_small", "mpn": "", "lcsc": "", "value": "100nF", "package": "0603", "reasoning": "Op-amp supply bypass capacitor"},
                {"role": "regulator_adj_resistor", "mpn": "", "lcsc": "", "value": "240", "package": "0603", "reasoning": "LM317 adjustment resistor"},
                {"role": "regulator_pos", "mpn": "", "lcsc": "", "value": "Adjustable", "package": "TO-92", "reasoning": "Positive 15V rail regulator"},
                {"role": "regulator_neg_adj", "mpn": "", "lcsc": "", "value": "240", "package": "0603", "reasoning": "LM337 adjustment resistor"},
                {"role": "dc_jack", "mpn": "", "lcsc": "", "value": "DC Jack", "package": "PTH", "reasoning": "12V DC input jack"},
                {"role": "power_switch", "mpn": "", "lcsc": "", "value": "DPDT", "package": "PTH", "reasoning": "Power on/off switch"},
                {"role": "battery_clip", "mpn": "", "lcsc": "", "value": "9V Battery Clip", "package": "PTH", "reasoning": "Optional 9V battery input"},
            ],
            "connections": [
                {"from": "input_jack_left.1", "to": "input_capacitor_left.1", "net": "L_IN"},
                {"from": "input_capacitor_left.2", "to": "input_resistor_left.1", "net": "L_SIG"},
                {"from": "input_resistor_left.2", "to": "psu_cap_large.2", "net": "GND"},
                {"from": "input_capacitor_left.2", "to": "opamp.3", "net": "L_SIG"},
                {"from": "opamp.1", "to": "output_capacitor_left.1", "net": "L_OUT_AMP"},
                {"from": "output_capacitor_left.2", "to": "output_jack_left.1", "net": "L_OUT"},
                {"from": "output_jack_left.2", "to": "psu_cap_large.2", "net": "GND"},
                {"from": "opamp.2", "to": "riaa_r1_left.2", "net": "L_FB"},
                {"from": "riaa_r1_left.1", "to": "riaa_c1_left.1", "net": "L_RIAA_A"},
                {"from": "riaa_c1_left.2", "to": "riaa_r2_left.1", "net": "L_RIAA_B"},
                {"from": "riaa_r2_left.2", "to": "riaa_c2_left.1", "net": "L_RIAA_C"},
                {"from": "riaa_c2_left.2", "to": "riaa_r3_left.1", "net": "L_RIAA_D"},
                {"from": "riaa_r3_left.2", "to": "riaa_c3_left.1", "net": "L_RIAA_E"},
                {"from": "riaa_c3_left.2", "to": "gain_rf_left.1", "net": "L_RIAA_F"},
                {"from": "gain_rf_left.2", "to": "opamp.1", "net": "L_OUT_AMP"},
                {"from": "input_jack_right.1", "to": "input_capacitor_right.1", "net": "R_IN"},
                {"from": "input_capacitor_right.2", "to": "input_resistor_right.1", "net": "R_SIG"},
                {"from": "input_resistor_right.2", "to": "psu_cap_large.2", "net": "GND"},
                {"from": "input_capacitor_right.2", "to": "opamp.5", "net": "R_SIG"},
                {"from": "opamp.7", "to": "output_capacitor_right.1", "net": "R_OUT_AMP"},
                {"from": "output_capacitor_right.2", "to": "output_jack_right.1", "net": "R_OUT"},
                {"from": "output_jack_right.2", "to": "psu_cap_large.2", "net": "GND"},
                {"from": "opamp.6", "to": "riaa_r1_right.2", "net": "R_FB"},
                {"from": "riaa_r1_right.1", "to": "riaa_c1_right.1", "net": "R_RIAA_A"},
                {"from": "riaa_c1_right.2", "to": "riaa_r2_right.1", "net": "R_RIAA_B"},
                {"from": "riaa_r2_right.2", "to": "riaa_c2_right.1", "net": "R_RIAA_C"},
                {"from": "riaa_c2_right.2", "to": "riaa_r3_right.1", "net": "R_RIAA_D"},
                {"from": "riaa_r3_right.2", "to": "riaa_c3_right.1", "net": "R_RIAA_E"},
                {"from": "riaa_c3_right.2", "to": "gain_rf_right.1", "net": "R_RIAA_F"},
                {"from": "gain_rf_right.2", "to": "opamp.7", "net": "R_OUT_AMP"},
                {"from": "dc_jack.1", "to": "power_switch.1", "net": "VRAW"},
                {"from": "battery_clip.1", "to": "power_switch.1", "net": "VRAW"},
                {"from": "power_switch.2", "to": "regulator_pos.VI", "net": "VRAW"},
                {"from": "psu_cap_large.1", "to": "regulator_pos.VI", "net": "VRAW"},
                {"from": "regulator_pos.ADJ", "to": "regulator_adj_resistor.1", "net": "VCC_ADJ"},
                {"from": "regulator_adj_resistor.2", "to": "psu_cap_large.2", "net": "GND"},
                {"from": "regulator_pos.VO", "to": "regulator_pos.ADJ", "net": "VCC"},
                {"from": "opamp.8", "to": "regulator_pos.VO", "net": "VCC"},
                {"from": "psu_cap_small.1", "to": "regulator_pos.VO", "net": "VCC"},
                {"from": "psu_cap_small.2", "to": "psu_cap_large.2", "net": "GND"},
                {"from": "opamp.4", "to": "psu_cap_large.2", "net": "GND"},
                {"from": "dc_jack.2", "to": "psu_cap_large.2", "net": "GND"},
                {"from": "battery_clip.2", "to": "psu_cap_large.2", "net": "GND"},
            ],
            "power_domains": {"VCC": 15.0, "VRAW": 12.0, "GND": 0.0},
            "design_notes": [
                "Passive RIAA equalisation around a single non-inverting gain stage per channel",
                "Use 1% metal-film resistors and C0G/NP0 capacitors in the RIAA network",
                "Keep the RIAA network close to the op-amp pins to minimise noise pickup",
                "Star ground: separate signal ground from power ground",
                "Verify the RIAA curve within +/-1dB from 20Hz to 20kHz"
            ],
            "warnings": [
                "Replace the DC jack and battery clip with the supply the user actually has"
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
                        "lcsc": {"type": "string"},
                        "manufacturer": {"type": "string"},
                        "value": {"type": "string"},
                        "package": {"type": "string"},
                        "reasoning": {"type": "string"},
                    },
                    # `mpn` is deliberately not required. Requiring it forced the
                    # model to produce a part number whether or not it knew a
                    # real one, and the invented numbers then looked exactly like
                    # orderable parts. An empty mpn is the honest answer: the
                    # platform resolves a real part from the value and package.
                    "required": ["role", "value", "package"]
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
        """
        Generate a circuit specification, preferring the LLM.

        When the LLM fails, the rule-based generator is used only if
        ``allow_fallback`` is enabled, and the substitution is recorded on the
        returned specification so callers never mistake a canned template for
        an AI-generated design.
        """
        if self.use_llm:
            try:
                return await self._generate_with_llm(requirements)
            except Exception as e:
                if not self.allow_fallback:
                    raise
                logger.warning(
                    "LLM generation failed (%s: %s); falling back to the rule-based "
                    "template generator",
                    type(e).__name__,
                    e,
                )

        # Rule-based template generation.
        spec_dict = self._generate_spec(requirements)
        return CircuitSpecification(
            requirements=requirements,
            topology=spec_dict["topology"],
            components=spec_dict["components"],
            connections=spec_dict.get("connections", []),
            power_domains=spec_dict.get("power_domains", {}),
            design_notes=spec_dict.get("design_notes", []),
            warnings=spec_dict.get("warnings", []),
            used_llm=False,
        )

    async def generate_validated(
        self,
        requirements: CircuitRequirement,
        max_repairs: int = 2,
        description: str = "",
        max_tokens: Optional[int] = None,
    ) -> tuple[CircuitSpecification, Optional[CircuitIR], DesignValidationReport]:
        """
        Generate, physically build, validate, and repair a circuit.

        This is the path that actually guarantees a usable design:

        1. ask the LLM for a specification
        2. build a Circuit IR (real MPNs, real pins, real footprints)
        3. run ERC and structural validation
        4. if there are errors, hand the model the exact problems and retry

        Returns the best specification, its Circuit IR, and the final report.
        """
        if max_tokens is None:
            max_tokens = self.default_max_tokens

        validator = DesignValidator(self.db)
        best: Optional[DesignValidationReport] = None
        attempts = 0
        used_llm = False

        spec_dict, used_llm = await self._generate_spec_dict(requirements, max_tokens)

        for attempt in range(max_repairs + 1):
            attempts = attempt + 1
            report = validator.validate(
                spec_dict, requirements=requirements, description=description
            )
            if best is None or _report_score(report) > _report_score(best):
                best = report

            if report.valid:
                break

            if attempt >= max_repairs:
                logger.warning(
                    "Circuit still has %d error(s) after %d attempt(s)",
                    len(report.errors),
                    attempts,
                )
                break

            logger.info(
                "Repairing circuit (attempt %d/%d): %d error(s)",
                attempt + 1,
                max_repairs + 1,
                len(report.errors),
            )
            spec_dict = await self._repair_spec(
                requirements, spec_dict, report.feedback(), max_tokens
            )

        assert best is not None  # loop always runs at least once

        spec = self._spec_from_dict(requirements, spec_dict)
        spec.used_llm = used_llm
        spec.repair_attempts = attempts - 1
        spec.validation = best.to_dict()
        if best.build_report is not None:
            # Surface substitution / inference notes to the caller.
            spec.warnings = list(spec.warnings) + list(best.build_report.notes)
        return spec, best.circuit, best

    async def _generate_spec_dict(
        self, requirements: CircuitRequirement, max_tokens: int = 2048
    ) -> tuple[Dict[str, Any], bool]:
        """Ask the LLM for a raw specification dict.

        Returns the specification and whether it actually came from the LLM.
        """
        if self.use_llm:
            try:
                spec_dict = await self._request_spec_dict(
                    requirements, max_tokens=max_tokens
                )
                if not spec_dict.get("components"):
                    raise LLMResponseError(
                        "LLM returned a specification with no components; "
                        f"keys received: {sorted(spec_dict.keys())}"
                    )
                return spec_dict, True
            except Exception as e:
                if not self.allow_fallback:
                    raise
                logger.warning(
                    "LLM specification generation failed (%s: %s); using the "
                    "rule-based template generator",
                    type(e).__name__,
                    e,
                )
        return self._generate_spec(requirements), False

    def _spec_from_dict(
        self, requirements: CircuitRequirement, spec_dict: Dict[str, Any]
    ) -> CircuitSpecification:
        """Convert a raw specification dict into a CircuitSpecification."""
        components = []
        for comp in spec_dict.get("components", []) or []:
            if isinstance(comp, ComponentSpec):
                components.append(comp)
            elif isinstance(comp, dict):
                components.append(
                    ComponentSpec(
                        role=comp.get("role", ""),
                        mpn=comp.get("mpn", ""),
                        manufacturer=comp.get("manufacturer", ""),
                        value=comp.get("value", ""),
                        package=comp.get("package", ""),
                        reasoning=comp.get("reasoning", ""),
                    )
                )
        return CircuitSpecification(
            requirements=requirements,
            topology=spec_dict.get("topology", ""),
            components=components,
            connections=spec_dict.get("connections", []) or [],
            power_domains=spec_dict.get("power_domains", {}) or {},
            design_notes=spec_dict.get("design_notes", []) or [],
            warnings=spec_dict.get("warnings", []) or [],
        )

    async def _request_spec_dict(
        self,
        requirements: CircuitRequirement,
        feedback: str = "",
        previous_spec: Optional[Dict[str, Any]] = None,
        max_tokens: int = 2048,
    ) -> Dict[str, Any]:
        """Make one specification request to the LLM.

        ``max_tokens`` bounds generation so a chatty local model cannot run for
        many minutes on a single request.
        """
        result = await self.llm.complete_structured(
            messages=self._build_spec_messages(
                requirements, feedback=feedback, previous_spec=previous_spec
            ),
            response_schema=self.SPEC_SCHEMA,
            max_tokens=max_tokens,
        )
        if not isinstance(result, dict):
            raise LLMResponseError(
                f"Expected a JSON object from the LLM, got {type(result).__name__}"
            )
        return result

    async def _repair_spec(
        self,
        requirements: CircuitRequirement,
        spec_dict: Dict[str, Any],
        feedback: str,
        max_tokens: int = 2048,
    ) -> Dict[str, Any]:
        """Ask the LLM to fix specific, machine-detected problems."""
        try:
            repaired = await self._request_spec_dict(
                requirements,
                feedback=feedback,
                previous_spec=spec_dict,
                max_tokens=max_tokens,
            )
        except Exception as e:
            logger.warning(
                "Repair attempt failed (%s: %s); keeping previous spec",
                type(e).__name__,
                e,
            )
            return spec_dict

        if not repaired.get("components"):
            logger.warning("Repair returned no components; keeping previous spec")
            return spec_dict
        return repaired

    def _build_spec_messages(
        self,
        requirements: CircuitRequirement,
        feedback: str = "",
        previous_spec: Optional[Dict[str, Any]] = None,
    ) -> List[LLMMessage]:
        """Build the system+user messages for specification generation."""
        example_text = self._few_shot_example(requirements.circuit_type)

        catalog_hint = self._catalog_hint(requirements)

        system_prompt = (
            "You are an expert electronics engineer. Produce a circuit "
            "specification as JSON.\n\n"
            "Requirements for your answer:\n"
            "- topology: a short topology name, e.g. \"LDO Linear Regulator\".\n"
            "- components: every part needed, each with role, value, package and "
            "reasoning.\n"
            "  * value and package are what identify a part. Give them as "
            "concretely as you can (\"10k\" with \"0603\", not \"resistor\").\n"
            "  * mpn and lcsc are optional. Fill them in ONLY by copying a part "
            "verbatim from the catalog list below. If you do not have a catalog "
            "part that fits, set both to an empty string: the platform will find "
            "a real, in-stock part for the value and package you asked for.\n"
            "  * Never write a part number from memory. A number that looks real "
            "but is not in a distributor's catalogue cannot be ordered, and the "
            "mistake is only discovered after the boards are designed.\n"
            "  * The examples below have empty mpn for exactly this reason: they "
            "show the shape of the answer, not part numbers to copy.\n"
            "- connections: every electrical connection, each as "
            "{\"from\": \"<ref>.<pin>\", \"to\": \"<ref>.<pin>\", \"net\": \"<NET>\"}. "
            "Use the reference designators you assigned (U1, C1, R1, D1, ...). "
            "Every pin you name must exist on that part.\n"
            "- power_domains: each rail with its voltage.\n"
            "- design_notes and warnings: free text.\n\n"
            "Electrical rules you must follow:\n"
            "- Every power input pin must be connected to a power or ground net.\n"
            "- Every regulator or IC needs input and output decoupling capacitors.\n"
            "- Every LED needs a series current-limiting resistor.\n"
            "- Every net must have at least two pin connections.\n"
            "- Do not invent pin numbers.\n"
            "- Do not invent part numbers: an empty mpn is always better than a "
            "guessed one.\n"
            f"{catalog_hint}\n"
            f"Example for {requirements.circuit_type}:\n{example_text}"
        )

        req_context = (
            f"Circuit Type: {requirements.circuit_type}\n"
            f"Description: {requirements.description}\n"
            f"Input Voltage: {requirements.input_voltage}V\n"
            f"Output Voltage: {requirements.output_voltage}V\n"
            f"Output Current: {requirements.output_current}A\n"
            f"Features: {requirements.features}\n"
            f"Constraints: {requirements.constraints}"
        )

        user_prompt = f"Generate a detailed circuit specification for:\n{req_context}"

        if feedback:
            previous = self._compact_render(previous_spec)
            user_prompt += (
                "\n\nThe previous attempt was invalid. Fix exactly these problems "
                "and return the complete corrected specification:\n"
                f"{feedback}\n"
            )
            if previous:
                user_prompt += f"Previous components were: {previous}\n"
            user_prompt += (
                "Return every component and every connection again, not just the "
                "changed ones."
            )

        return [
            LLMMessage(role="system", content=system_prompt),
            LLMMessage(role="user", content=user_prompt),
        ]

    # Local models on CPU spend real time reading the prompt, so a huge
    # few-shot example is a latency cost with little accuracy benefit.
    _MAX_EXAMPLE_CHARS = 2600

    def _few_shot_example(self, circuit_type: str) -> str:
        """Render the few-shot example, trimmed for prompt economy."""
        example = self.SPEC_EXAMPLES.get(circuit_type)
        if not example:
            return "No example available for this circuit type."

        text = json.dumps(example, separators=(",", ":"))
        if len(text) <= self._MAX_EXAMPLE_CHARS:
            return text

        # Keep the first components and the connections, which carry the shape.
        trimmed = {
            key: value
            for key, value in example.items()
            if key in ("topology", "connections", "power_domains")
        }
        components = example.get("components") or []
        trimmed["components"] = components[:6]
        trimmed["design_notes"] = (example.get("design_notes") or [])[:2]
        return json.dumps(trimmed, separators=(",", ":"))

    def _catalog_hint(self, requirements: CircuitRequirement) -> str:
        """
        Render a short list of real catalog parts that actually fit the request.

        Only parts relevant to the requirement are listed. An earlier version
        listed the four highest-stock parts of each category, which for a 3.3 V
        regulator request offered five-volt regulators — a hint that invites the
        wrong answer is worse than no hint. Passives are deliberately not listed:
        their value and package are enough for the platform to find a real part,
        and a list of unrelated 0402 capacitors is only noise.
        """
        if self.db is None:
            return ""

        category = {
            "ldo_regulator": "regulator_ldo",
            "buck_converter": "regulator_buck",
            "boost_converter": "regulator_boost",
        }.get(requirements.circuit_type)

        lines: List[str] = []
        if category:
            wanted_voltage = requirements.output_voltage
            query = f"{wanted_voltage}v" if wanted_voltage else ""
            try:
                parts = self.db.search(
                    query=query, category=category, min_stock=1000, limit=6
                )
            except Exception:
                parts = []
            for part in parts:
                if not part.lcsc_part:
                    # No LCSC number means a component template, not something
                    # that can be ordered. Offering it here is how invented part
                    # numbers spread into designs.
                    continue
                lines.append(
                    f"- mpn={part.mpn} lcsc={part.lcsc_part} "
                    f"({part.manufacturer}) value={part.value} "
                    f"package={part.package} stock={part.stock}"
                )

        if not lines:
            return (
                "\nNo component catalogue is available, so no part numbers can be "
                "verified. Leave mpn and lcsc empty for every component: give "
                "value and package, and the platform will find a real part."
            )

        return (
            "\nThese parts are real, in stock and match what was asked for. Copy "
            "mpn and lcsc together, exactly as written, if one of them fits; "
            "otherwise leave both empty. For resistors, capacitors and "
            "inductors, leave mpn and lcsc empty and just give value and "
            "package:\n" + "\n".join(lines)
        )

    def _compact_render(self, spec_dict: Optional[Dict[str, Any]]) -> str:
        """Render a spec compactly (used when giving repair context)."""
        if not spec_dict:
            return ""
        parts = []
        for comp in spec_dict.get("components", []) or []:
            if isinstance(comp, dict):
                identifier = comp.get("lcsc") or comp.get("mpn") or "?"
                parts.append(f"{comp.get('role', '?')}={identifier}")
        return ", ".join(parts)

    async def _generate_with_llm(self, requirements: CircuitRequirement) -> CircuitSpecification:
        """Generate specification using LLM with structured output."""
        result = await self._request_spec_dict(requirements)

        # Validate required fields
        if (
            not result.get("topology")
            or not result.get("components")
            or result.get("topology") == ""
            or result.get("components") == []
        ):
            raise LLMResponseError(
                "LLM response missing required fields (topology, components); "
                f"received keys: {sorted(result.keys())}"
            )

        return self._spec_from_dict(requirements, result)

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
        ldo = self._select_ldo(v_out, i_out)
        caps = self._select_caps()
        led = self._select_led()
        res = self._select_resistor()

        return {
            "topology": "linear_ldo",
            "components": [
                self._make_component(
                    role="regulator",
                    mpn=ldo["mpn"],
                    manufacturer=ldo.get("manufacturer", ""),
                    value=f"{v_out}V",
                    package=ldo.get("package", "SOT-223"),
                    reasoning=f"LDO regulator {v_in}V to {v_out}V at {i_out}A",
                ),
                self._make_component(
                    role="input_capacitor",
                    mpn=caps[0]["mpn"],
                    manufacturer=caps[0].get("manufacturer", ""),
                    value=caps[0].get("value", "10uF"),
                    package=caps[0].get("package", "0805"),
                    reasoning="Input decoupling capacitor",
                ),
                self._make_component(
                    role="output_capacitor",
                    mpn=caps[1]["mpn"],
                    manufacturer=caps[1].get("manufacturer", ""),
                    value=caps[1].get("value", "22uF"),
                    package=caps[1].get("package", "0805"),
                    reasoning="Output stability capacitor",
                ),
                self._make_component(
                    role="led_indicator",
                    mpn=led["mpn"],
                    manufacturer=led.get("manufacturer", ""),
                    value=led.get("value", "Green"),
                    package=led.get("package", "0805"),
                    reasoning="Power-on indicator",
                ),
                self._make_component(
                    role="current_limit_resistor",
                    mpn=res["mpn"],
                    manufacturer=res.get("manufacturer", ""),
                    value=res.get("value", "330"),
                    package=res.get("package", "0805"),
                    reasoning="LED current limiting resistor",
                ),
            ],
            "connections": [
                {"from": "U1.VIN", "to": "C1.1", "net": "VIN"},
                {"from": "U1.VOUT", "to": "C2.1", "net": "VOUT"},
                {"from": "U1.VOUT", "to": "R1.1", "net": "VOUT"},
                {"from": "R1.2", "to": "D1.A", "net": "LED_A"},
                {"from": "D1.K", "to": "C1.2", "net": "GND"},
                {"from": "U1.GND", "to": "C2.2", "net": "GND"},
            ],
            # The dissipation and dropout are no longer asserted as notes: the
            # electrical review computes them from the finished circuit and says
            # whether they pass. A note that says "check this" when the platform
            # already knows the answer is how a real problem gets ignored.
            "design_notes": [
                f"Linear regulator drops {v_in - v_out:.1f}V at up to {i_out:g}A",
            ],
            "warnings": [],
        }

    def _select_ldo(self, v_out: float, i_out: float) -> dict:
        # Simplified selection - in reality would query database
        return {
            "mpn": "",
            "package": "SOT-223",
            "v_out": v_out,
            "i_max": 1.0
        }

    def _select_caps(self) -> List[dict]:
        return [
            {"mpn": "", "value": "10uF", "package": "0805"},
            {"mpn": "", "value": "22uF", "package": "0805"}
        ]

    def _select_led(self) -> dict:
        return {"mpn": "", "value": "Green", "package": "0805"}

    def _select_resistor(self) -> dict:
        return {"mpn": "", "value": "330", "package": "0805"}

    def _spec_buck(self, req):
        return {
            "topology": "buck_async",
            "components": [
                {
                    "role": "controller",
                    "mpn": "",
                    "value": "5V",
                    "package": "TO-220-5",
                    "reasoning": "Buck converter controller",
                },
                {
                    "role": "inductor",
                    "mpn": "",
                    "value": "47uH",
                    "package": "1210",
                    "reasoning": "Buck inductor",
                },
                {
                    "role": "input_capacitor",
                    "mpn": "",
                    "value": "10uF",
                    "package": "0805",
                    "reasoning": "Input decoupling",
                },
                {
                    "role": "output_capacitor",
                    "mpn": "",
                    "value": "22uF",
                    "package": "0805",
                    "reasoning": "Output filtering",
                },
                {
                    "role": "freewheel_diode",
                    "mpn": "",
                    "value": "1A/40V",
                    "package": "SMA",
                    "reasoning": "Freewheeling diode",
                },
            ],
            "connections": [
                {"from": "U1.VIN", "to": "C1.1", "net": "VIN"},
                {"from": "U1.OUT", "to": "L1.1", "net": "SW"},
                {"from": "L1.2", "to": "C2.1", "net": "VOUT"},
                {"from": "D1.K", "to": "U1.OUT", "net": "SW"},
                {"from": "D1.A", "to": "C1.2", "net": "GND"},
                {"from": "U1.GND", "to": "C2.2", "net": "GND"},
                {"from": "U1.FB", "to": "C2.1", "net": "VOUT"},
                {"from": "U1.ON", "to": "C1.2", "net": "GND"},
            ],
            "design_notes": [
                "Asynchronous buck converter",
                "Consider synchronous rectification for >90% efficiency",
            ],
            "warnings": ["Diode loss is significant at high current"],
        }

    def _spec_boost(self, req):
        return {
            "topology": "boost",
            "components": [
                {
                    "role": "controller",
                    "mpn": "",
                    "value": "Adjustable",
                    "package": "SOT-23-6",
                    "reasoning": "Boost converter IC",
                },
                {
                    "role": "inductor",
                    "mpn": "",
                    "value": "10uH",
                    "package": "0805",
                    "reasoning": "Boost inductor",
                },
                {
                    "role": "input_capacitor",
                    "mpn": "",
                    "value": "10uF",
                    "package": "0805",
                    "reasoning": "Input decoupling",
                },
                {
                    "role": "output_capacitor",
                    "mpn": "",
                    "value": "22uF",
                    "package": "0805",
                    "reasoning": "Output filtering",
                },
                {
                    "role": "freewheel_diode",
                    "mpn": "",
                    "value": "1A/40V",
                    "package": "SMA",
                    "reasoning": "Boost rectifier",
                },
            ],
            "connections": [
                {"from": "U1.VIN", "to": "C1.1", "net": "VIN"},
                {"from": "U1.SW", "to": "L1.1", "net": "SW"},
                {"from": "D1.A", "to": "L1.2", "net": "SW"},
                {"from": "D1.K", "to": "C2.1", "net": "VOUT"},
                {"from": "U1.GND", "to": "C1.2", "net": "GND"},
                {"from": "C2.2", "to": "C1.2", "net": "GND"},
                {"from": "U1.FB", "to": "C2.1", "net": "VOUT"},
                {"from": "U1.EN", "to": "C1.1", "net": "VIN"},
            ],
            "design_notes": ["Boost converter for voltage step-up"],
            "warnings": ["Output current is limited by inductor saturation"],
        }

    def _spec_led(self, req):
        return {
            "topology": "series_resistor",
            "components": [
                {
                    "role": "led",
                    "mpn": "",
                    "value": "Green",
                    "package": "0805",
                    "reasoning": "Green indicator LED",
                },
                {
                    "role": "current_limit_resistor",
                    "mpn": "",
                    "value": "330",
                    "package": "0805",
                    "reasoning": "Current limiting resistor",
                },
            ],
            "connections": [
                {"from": "R1.1", "to": "D1.A", "net": "LED_A"},
                {"from": "R1.2", "to": "D1.K", "net": "LED_K"},
            ],
            "design_notes": ["Simple series resistor LED driver"],
            "warnings": ["Not suitable for high-power LEDs"],
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
        allow_fallback: bool = True,
        max_repairs: int = 2,
        deterministic: bool = False,
    ):
        """Initialize pipeline with optional LLM client and component database.

        Args:
            llm_client: LLM client instance. If None, uses mock client.
            component_db: Component database for part resolution. Defaults to
                the standard database so MPNs resolve to real catalog parts.
            allow_fallback: When False, an LLM failure raises instead of
                silently substituting the rule-based template generator.
            max_repairs: How many times a physically invalid design is sent back
                to the model with specific error feedback.
            deterministic: Parse and generate with rules instead of asking the
                model. The mock client returns canned requirements rather than
                reading the prompt, so without this a default run discards what
                the user typed; see :class:`RequirementParser`.
        """
        if llm_client is None:
            llm_client = create_llm_client("mock")

        self.llm_client = llm_client
        self.max_repairs = max_repairs
        self.allow_fallback = allow_fallback
        self.deterministic = deterministic
        self.db = component_db if component_db is not None else ComponentDatabase()

        self.parser = RequirementParser(llm_client, deterministic=deterministic)
        self.spec_generator = CircuitSpecificationGenerator(
            llm_client, self.db,
            use_llm=not deterministic,
            allow_fallback=allow_fallback,
        )
        self.builder = CircuitIRBuilder(self.db)
        self.validator = DesignValidator(self.db)
        self.orchestrator = None
        # Populated by the most recent pipeline run, for callers that want the
        # full validation detail alongside the Circuit IR.
        self.last_validation: Optional[DesignValidationReport] = None

    def set_orchestrator(self, orchestrator: Any) -> None:
        """Set the orchestrator for this pipeline."""
        self.orchestrator = orchestrator

    @staticmethod
    def _require_valid_design(
        circuit: Optional[CircuitIR], report: DesignValidationReport
    ) -> None:
        """
        Fail loudly when a design is missing or violates the electrical rules.

        Returning a design that does not pass ERC would hand the user a board
        that cannot work, so an unusable result is an error, not a warning.
        """
        if circuit is None:
            raise RuntimeError(
                "Design could not be built from the generated specification: "
                + "; ".join(i.message for i in report.errors[:3])
            )

        if not report.valid:
            details = "; ".join(i.message for i in report.errors[:3])
            raise RuntimeError(
                f"Generated design failed validation with "
                f"{len(report.errors)} error(s): {details}"
            )

    async def nl_to_circuit_spec(self, prompt: str) -> CircuitSpecification:
        """
        Process a natural language prompt into a validated circuit specification.

        The returned specification carries a ``validation`` payload and its
        ``requirements``; the built Circuit IR is available on the pipeline as
        ``last_validation.circuit`` and via :meth:`nl_to_circuit_ir`.
        """
        requirements = await self.parser.parse(prompt)
        spec, circuit, report = await self.spec_generator.generate_validated(
            requirements,
            max_repairs=self.max_repairs,
            description=requirements.description or prompt,
        )
        self.last_validation = report

        self._require_valid_design(circuit, report)

        return spec

    async def nl_to_circuit_ir(self, prompt: str) -> CircuitIR:
        """Process a natural language prompt into a built, validated Circuit IR."""
        requirements = await self.parser.parse(prompt)
        spec, circuit, report = await self.spec_generator.generate_validated(
            requirements,
            max_repairs=self.max_repairs,
            description=requirements.description or prompt,
        )
        self.last_validation = report

        self._require_valid_design(circuit, report)
        return circuit
    
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
            Dictionary with requirements, specification, circuit_ir, validation,
            and generated files
        """
        # Step 1: Parse requirements
        requirements = await self.parser.parse(prompt)

        # Step 2+3: Generate the specification, build the Circuit IR, validate it,
        # and repair it if the electrical rules fail.
        spec, circuit_ir, report = await self.spec_generator.generate_validated(
            requirements,
            max_repairs=self.max_repairs,
            description=requirements.description or prompt,
        )
        self.last_validation = report

        if circuit_ir is None:
            raise RuntimeError(
                "Design could not be built from the generated specification: "
                + "; ".join(i.message for i in report.errors[:3])
            )

        result: Dict[str, Any] = {
            "requirements": requirements,
            "specification": spec,
            "circuit_ir": circuit_ir,
            "validation": report,
            "valid": report.valid,
        }

        # Step 4: optionally emit KiCad project files.
        if output_dir is not None:
            result["files"] = self._export(circuit_ir, Path(output_dir), project_name)

        return result

    def _export(
        self, circuit_ir: CircuitIR, output_dir: Path, project_name: str
    ) -> Dict[str, Path]:
        """Write the Circuit IR out as a KiCad project."""
        from src.generators.kicad_generator import KiCadGenerator

        output_dir.mkdir(parents=True, exist_ok=True)
        return KiCadGenerator(circuit_ir).export_project(output_dir, project_name)
    
    def _spec_to_dict(self, spec: Dict[str, Any]) -> Dict[str, Any]:
        """Convert specification to dictionary for serialization."""
        return spec
    
    def _spec_to_circuit_ir(self, requirements: CircuitRequirement) -> CircuitIR:
        """
        Build a Circuit IR from a requirement using the validated builder path.

        This previously contained per-topology hardcoded circuits that ignored
        the generated specification entirely. It now generates a specification
        synchronously via the rule-based templates and builds it through the
        same resolver/validator used for LLM output, so there is exactly one
        code path that turns a specification into hardware.
        """
        spec_dict = self.spec_generator._generate_spec(requirements)
        circuit, report = self.builder.build(
            spec_dict,
            requirements=requirements,
            description=requirements.description,
        )
        circuit.metadata["build_report"] = report.to_dict()
        return circuit

def create_nl_pipeline(
    llm_provider: Union[LLMProvider, str] = "mock",
    component_db=None,
    allow_fallback: bool = True,
    max_repairs: int = 2,
) -> NLToCircuitPipeline:
    """Factory function to create NL pipeline.

    Args:
        llm_provider: LLM provider string or LLMProvider enum
        component_db: Optional component database for part selection
        allow_fallback: When False, LLM failures raise instead of silently
            falling back to the rule-based template generator.
        max_repairs: Number of validate-and-repair rounds for invalid designs.
    """
    if isinstance(llm_provider, str):
        try:
            provider = LLMProvider(llm_provider.lower())
        except ValueError:
            raise ValueError(f"Unknown provider: {llm_provider}")
        llm_client = create_llm_client(provider)
    else:
        provider = llm_provider
        llm_client = create_llm_client(llm_provider)

    # "mock" means *no model*: parse the prompt with rules and generate the
    # design from the templates. It is not a stub that returns a canned answer
    # while pretending to read the prompt.
    deterministic = provider == LLMProvider.MOCK

    return NLToCircuitPipeline(
        llm_client=llm_client,
        deterministic=deterministic,
        component_db=component_db,
        allow_fallback=allow_fallback,
        max_repairs=max_repairs,
    )


# Module-level schema exports for testing
REQUIREMENT_SCHEMA = RequirementParser.REQUIREMENT_SCHEMA
SPECIFICATION_SCHEMA = CircuitSpecificationGenerator.SPEC_SCHEMA