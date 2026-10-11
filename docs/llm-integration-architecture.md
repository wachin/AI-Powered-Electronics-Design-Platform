# LLM Integration Architecture

## Overview

The AI Electronics Design Platform includes a complete LLM integration layer that enables natural language to circuit design conversion. The system supports multiple LLM providers with a unified interface and includes robust fallback mechanisms.

## Architecture

```
Natural Language Prompt
        │
        ▼
┌───────────────────────┐
│  NLToCircuitPipeline  │
└───────────┬───────────┘
            │
     ┌──────┴──────┐
     ▼             ▼
┌─────────┐   ┌──────────────────┐
│ Parser  │   │ Spec Generator   │
└────┬────┘   └────────┬─────────┘
     │                 │
     ▼                 ▼
CircuitRequirement  CircuitSpecification
     │                 │
     └────────┬────────┘
              ▼
    _spec_to_circuit_ir()
              │
              ▼
        CircuitIR
              │
              ▼
    AIDesignOrchestrator
              │
     ┌────────┼────────┐
     ▼        ▼        ▼
   ERC      SPICE    KiCad
            ▼        ▼
         BOM       3D glTF
```

## Core Components

### 1. LLM Providers (`src/llm/providers.py`)

#### Abstract Base Class: `LLMClient`
```python
class LLMClient(ABC):
    @abstractmethod
    async def complete(messages, temperature=0.1, max_tokens=4096, response_format=None) -> LLMResponse
    
    @abstractmethod
    async def complete_structured(messages, response_schema, temperature=0.1) -> Dict[str, Any]
    
    @abstractmethod
    async def health_check() -> bool
```

#### Concrete Implementations

| Provider | Class | API Format | Use Case |
|----------|-------|------------|----------|
| Local Ollama | `OllamaClient` | Native + OpenAI-compatible | Primary (offline, free) |
| OpenAI-compatible | `OpenAIClient` | OpenAI API | NVIDIA NIM, HuggingFace, OpenRouter, Gemini, Together, Groq |
| Anthropic | `AnthropicClient` | Anthropic API | Claude models |
| Testing | `MockLLMClient` | In-memory | Unit tests, CI/CD |

#### Factory Function
```python
from src.llm.providers import create_llm_client, LLMProvider

# Local Ollama (native)
client = create_llm_client("ollama", model="qwen2.5:3b", base_url="http://localhost:11434")

# OpenAI-compatible (NVIDIA, HF, OpenRouter, etc.)
client = create_llm_client("openai", api_key="...", base_url="...", model="...")

# Anthropic
client = create_llm_client("anthropic", api_key="...", model="claude-3-5-sonnet-20241022")

# Mock for testing
client = create_llm_client("mock")
```

### 2. Requirement Parser (`src/llm/integration.py`)

Parses natural language into structured `CircuitRequirement`:

```python
@dataclass
class CircuitRequirement:
    circuit_type: str          # ldo_regulator, buck_converter, boost_converter, led_driver, mcu_board, generic
    description: str
    input_voltage: float | None
    output_voltage: float | None
    output_current: float | None
    features: List[str]
    constraints: Dict[str, Any]
```

**Features:**
- Structured output using JSON schema validation
- Few-shot examples for improved accuracy (4 examples: LDO, Buck, Boost, LED)
- Keyword-based fallback parser for reliability
- Graceful degradation when LLM unavailable

### 3. Circuit Specification Generator (`src/llm/integration.py`)

Generates detailed `CircuitSpecification` from requirements:

```python
@dataclass
class CircuitSpecification:
    requirements: CircuitRequirement
    topology: str
    components: List[ComponentSpec]
    connections: List[Dict[str, str]]
    power_domains: Dict[str, Dict[str, float]]
    design_notes: List[str]
    warnings: List[str]
```

**ComponentSpec:**
```python
@dataclass
class ComponentSpec:
    role: str          # regulator, controller, inductor, input_capacitor, etc.
    mpn: str           # Manufacturer Part Number (e.g., "LM2596S-5.0")
    manufacturer: str  # TI, AMS, Yageo, etc.
    value: str         # 5V, 47uH, 10uF, etc.
    package: str       # SOT-223, TO-220-5, 0805, etc.
    reasoning: str     # Design rationale
```

**Features:**
- LLM-based generation with few-shot examples per circuit type
- Rule-based fallback for reliability
- Real MPNs from major manufacturers
- Package selection based on current/power requirements

### 4. CircuitIR Generation (`src/llm/integration.py`)

Converts specifications to executable `CircuitIR`:

```python
def _spec_to_circuit_ir(self, requirements: CircuitRequirement) -> CircuitIR:
    # Creates components with pins and nets
    # Uses ComponentDatabase for real part data
    # Returns complete CircuitIR ready for ERC/SPICE/KiCad
```

**Supported Circuit Types:**
- `ldo_regulator`: AMS1117-3.3, 10uF/22uF caps, LED + resistor
- `buck_converter`: LM2596S-5.0, 47uH inductor, 10uF/100uF caps, SS14 Schottky
- `boost_converter`: MT3608, 10uH inductor, 10uF/22uF caps, SS14 Schottky, feedback resistors
- `led_driver`: Green LED + current-limiting resistor

### 5. AIDesignOrchestrator (`src/agents/orchestrator.py`)

End-to-end design pipeline:

```python
orchestrator = AIDesignOrchestrator()
request = DesignRequest(
    prompt="Design a 12V to 5V buck converter for 3A",
    project_name="my_buck",
    run_spice=True,
    run_routing=True
)
summary = await orchestrator.process_request(request, output_dir)
```

**Pipeline Steps:**
1. Natural Language → CircuitIR (via NLToCircuitPipeline)
2. ERC Validation
3. SPICE Simulation (ngspice)
4. KiCad Project Generation (SCH, PCB, PRO)
5. PCB Auto-routing (FreeRouting - graceful on KiCad 9)
6. BOM Generation (with JLCParts pricing)
7. 3D glTF Export

## Usage Examples

### Basic Pipeline Usage
```python
from src.llm.integration import create_nl_pipeline

# Create pipeline with mock LLM (for testing)
pipeline = create_nl_pipeline("mock")

# Or with local Ollama
pipeline = create_nl_pipeline("ollama", model="qwen2.5:3b")

# Or with OpenAI-compatible API
pipeline = create_nl_pipeline(
    "openai",
    api_key="sk-xxx",
    base_url="https://openrouter.ai/api/v1",
    model="qwen/qwen-2.5-3b-instruct"
)

# Process natural language
result = await pipeline.nl_to_circuit_spec("Design a 5V to 3.3V LDO with LED indicator")
print(result.requirements.circuit_type)  # "ldo_regulator"
print(result.topology)  # "LDO Linear Regulator"
print(len(result.components))  # 5
```

### Full Design Flow
```python
from src.agents.orchestrator import AIDesignOrchestrator, DesignRequest
from pathlib import Path

orchestrator = AIDesignOrchestrator()
request = DesignRequest(
    prompt="Design a buck converter 12V to 5V 3A for Raspberry Pi",
    project_name="rpi_buck",
    run_spice=True,
    run_routing=False  # Skip routing on KiCad 9+
)

summary = await orchestrator.process_request(request, Path("output"))
print(f"ERC: {'PASS' if summary.erc_report.passed else 'FAIL'}")
print(f"Components: {len(summary.circuit_ir.components)}")
print(f"BOM items: {len(summary.bom)}")
print(f"Files: {list(summary.generated_files.keys())}")
```

## Configuration

### Environment Variables
```bash
# LLM Provider API Keys
export NVIDIA_API_KEY=nvapi-xxx
export HUGGINGFACE_API_KEY=hf_xxx
export OPENROUTER_API_KEY=sk-or-xxx
export GEMINI_API_KEY=AIzaSy...
export TOGETHER_API_KEY=xxx
export GROQ_API_KEY=gsk_xxx

# Local Ollama
export USE_OLLAMA=true
# ollama pull qwen2.5:3b
```

### Provider Selection
```python
# Use specific provider
pipeline = create_nl_pipeline(
    provider="openai",  # or "ollama", "anthropic", "mock"
    api_key="...",
    base_url="...",
    model="..."
)

# Or manually create client
from src.llm.providers import create_llm_client, LLMProvider
client = create_llm_client(LLMProvider.OPENAI, api_key="...", base_url="...", model="...")
pipeline = NLToCircuitPipeline(llm_client=client)
```

## Error Handling & Fallbacks

The system is designed for reliability:

1. **LLM Health Checks**: `health_check()` verifies API connectivity before use
2. **Structured Output Validation**: JSON schema validation with retry
3. **Graceful Degradation**: 
   - LLM parsing fails → keyword-based fallback parser
   - LLM spec generation fails → rule-based spec generator
   - SPICE simulation fails → continues with KiCad generation
   - FreeRouting fails (KiCad 9) → logs warning, continues with BOM/3D
4. **Mock Client**: Always available for testing/CI

## Testing

```bash
# Run all LLM integration tests
pytest tests/test_llm_integration.py -v

# Run all tests
pytest tests/ -v

# Test specific provider
python test_real_llm.py  # Set API keys as env vars first
```

## Supported Circuit Types

| Type | Keywords | Example Components |
|------|----------|-------------------|
| `ldo_regulator` | ldo, linear regulator, 5v to 3.3v | AMS1117, caps, LED |
| `buck_converter` | buck, step-down | LM2596, 47uH, SS14 |
| `boost_converter` | boost, step-up | MT3608, 10uH, SS14 |
| `led_driver` | led driver | LED, current-limit R |
| `mcu_board` | mcu, microcontroller | MCU, crystal, caps |
| `generic` | (fallback) | User-defined |

## Extending with New Circuit Types

1. Add circuit type to `REQUIREMENT_SCHEMA` enum
2. Add few-shot example to `RequirementParser.PARSE_EXAMPLES`
3. Add spec example to `CircuitSpecificationGenerator.SPEC_EXAMPLES`
4. Implement `_spec_to_circuit_ir` logic for new type
5. Add ComponentType if needed (e.g., `REGULATOR_BUCK`, `REGULATOR_BOOST`)

## Performance Notes

- **qwen2.5:3b** (local): ~8-12 tok/s, ~2.8 GB RAM
- **qwen2.5:7b** (local): ~6-8 tok/s, ~5.2 GB RAM
- **phi3:mini** (local): ~10-15 tok/s, ~2.8 GB RAM, better reasoning
- **OpenAI-compatible APIs**: Network latency dependent, typically 1-5s per request
- **Mock client**: Instant (for testing)

## Known Limitations

1. **KiCad 9 FreeRouting**: DSN export removed in KiCad 7+. Workarounds documented.
2. **SPICE Models**: Limited to predefined diode models. Add custom models as needed.
3. **LLM Structured Output**: Small models (3B) may occasionally miss required fields. Fallbacks handle this.
4. **Component Database**: Uses built-in JLCParts subset. Extend `src/components/database.py` for more parts.