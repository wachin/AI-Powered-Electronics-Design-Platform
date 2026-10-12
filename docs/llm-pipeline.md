# LLM Circuit Pipeline: Architecture, Verification, and Postmortem

This document describes the natural-language design pipeline as it actually
works, the failure that made every AI design silently fall back to a template,
and the deterministic checks that now stand between an LLM and the delivered
hardware.

**Status:** implemented and covered by tests (`tests/test_llm_providers.py`,
`tests/test_circuit_builder.py`, `tests/test_llm_pipeline_repair.py`).

---

## 1. Pipeline

```
User prompt
   │
   ▼
RequirementParser.parse()                    src/llm/integration.py
   │  LLM + REQUIREMENT_SCHEMA, keyword fallback
   ▼
CircuitRequirement (type, voltages, current, features)
   │
   ▼
CircuitSpecificationGenerator.generate_validated()
   │
   ├─ 1. LLM + SPEC_SCHEMA + catalog grounding ──► raw specification dict
   │
   ├─ 2. CircuitIRBuilder.build()               src/core/circuit_builder.py
   │        • MPN → catalog lookup / substitution
   │        • role → ComponentType
   │        • pins from verified KiCad pinouts + alias resolution
   │        • connections resolved (designator or role, alias-aware)
   │        • power nets marked
   │
   ├─ 3. DesignValidator.validate()             src/llm/validation.py
   │        • shape (non-empty components, required fields)
   │        • MPN known / substituted
   │        • connection references valid pins
   │        • ERC (src/core/erc.py)
   │
   └─ 4. If invalid: send specific errors back to the LLM as feedback
            (up to `max_repairs`), keep the best-scoring attempt
   │
   ▼
CircuitIR ──► KiCadGenerator ──► .kicad_sch / .kicad_pcb / .kicad_pro
```

The LLM never writes KiCad. It produces a specification; deterministic code
decides whether that specification is physically expressible.

### Entry points

| Function | Returns |
|---|---|
| `NLToCircuitPipeline.nl_to_circuit_spec()` | `CircuitSpecification` (with `validation` payload) |
| `NLToCircuitPipeline.nl_to_circuit_ir()` | validated `CircuitIR` |
| `NLToCircuitPipeline.process()` | dict with specification, Circuit IR, validation, files |

`process()` raises `RuntimeError` when the design fails validation; a design
that violates ERC is not delivered as if it worked.

---

## 2. The postmortem: why every AI design was actually a template

**Symptom:** asking for a circuit produced a plausible design whose component
values looked templated, and the "AI" appeared to contribute nothing.

**Root cause:** `OllamaClient.complete()` was a copy-paste of
`MockLLMClient.complete()`:

```python
# before
async def complete(self, messages, ...):
    key = messages[-1].content if messages else "default"
    response = self.responses.get(key, {...})   # OllamaClient has no .responses
    return LLMResponse(content=json.dumps(response))
```

It never made an HTTP request, and `self.responses` does not exist on
`OllamaClient`, so every call raised `AttributeError`. That exception was caught
by broad handlers in the integration layer:

```python
except Exception as e:
    logger.warning(f"LLM parsing failed, using fallback: {e}")
    return self._fallback_parse(natural_language)
```

The pipeline therefore fell back to the rule-based template generator on every
request, and the user received a canned circuit with no indication that the LLM
had never run.

**Why the test suite did not catch it:** every LLM test used `MockLLMClient`,
which *does* have `responses` and hardcoded answers. The real provider path had
no test at all.

**Secondary defect:** even when the LLM did return a specification, the pipeline
discarded it. `_spec_to_circuit_ir()` took `requirements` (not the specification)
and built a hardcoded per-topology circuit, so component selection, connections
and power domains were ignored:

```python
spec = await self.spec_generator.generate(requirements)
circuit_ir = self._spec_to_circuit_ir(requirements)   # spec dropped
```

### Fixes

1. `OllamaClient` performs real `POST /api/chat` requests, passes a JSON schema
   in `format`, and falls back to unconstrained generation if the server rejects
   structured format.
2. `extract_json_object()` tolerates markdown fences and surrounding prose, so a
   fenced answer no longer fails the whole request.
3. The specification is now the input to a real builder
   (`src/core/circuit_builder.py`); the 830-line hardcoded builder was deleted.
4. An LLM failure is no longer silent: `used_llm` is recorded on the
   specification, and `allow_fallback=False` turns the failure into an error.
5. Tests drive the real provider code with a stubbed HTTP transport.

Each of these has a regression test.

---

## 3. Deterministic guarantees

### MPN resolution

`resolve_mpn()` tries an exact catalog hit, then a category search preferring
matching value and package. Outcomes:

* exact hit → used as-is;
* substitution → recorded on `spec.warnings` and reported as `MPN_SUBSTITUTED`
  (warning);
* no match → `MPN_UNKNOWN` (error), which triggers a repair attempt.

### Pin resolution

Pin numbers and names come from the KiCad symbol libraries, verified against
KiCad 9.0.2 (`/usr/share/kicad/symbols`). Examples:

| Symbol | Pins |
|---|---|
| `Regulator_Linear:AMS1117-3.3` | 1=GND, 2=VO, 3=VI |
| `Regulator_Linear:LM7805_TO220` | 1=VI, 2=GND, 3=VO |
| `Regulator_Switching:LM2596S-5` | 1=VIN, 2=OUT, 3=GND, 4=FB, 5=~{ON}/OFF |
| `Device:LED` | 1=K, 2=A |
| `Amplifier_Operational:LM358` | 1=OUT1, 2=IN1-, 3=IN1+, 4=V-, 5=IN2+, 6=IN2-, 7=OUT2, 8=V+ |

Because a model may reasonably write `VOUT` where the symbol calls the pin `VO`,
an alias layer resolves `VO`/`VOUT`/`OUT` to the same physical pin. An unknown
pin is reported (`CONNECTION_INVALID`) rather than dropped.

An exact pin *number* is matched before any name, so `D1.2` means pad 2 (the
anode) and never collides with a name lookup.

### Connection parsing

Accepted endpoint forms: `"U1.VIN"`, `"U1:VIN"`, `"U1"` plus a separate pin,
`{"ref": ..., "pin": ...}`, and role names such as `"input_capacitor.1"`.
Endpoints that are role names are mapped to the assigned designators.

A connection with no pin is only guessed for power/ground nets (`VIN`, `VOUT`,
`GND`, `VCC`, `VDD`, `VSS`), and the guess is recorded. A *signal* net without a
pin is reported instead of guessed, because guessing would silently corrupt the
netlist.

---

## 4. Repair loop semantics

`generate_validated(requirements, max_repairs=N, max_tokens=...)`:

1. generate a specification;
2. build and validate;
3. if there are errors, render them as instructions:

   ```
   - ERROR [CONNECTION_INVALID] Connection ignored: U1 has no pin 'MADE_UP_PIN'
     (available: ['1', '2', '3']). Every connection must name an existing
     component and one of its real pins.
   - ERROR [ERC005_LED_WITHOUT_RESISTOR] LED D1 does not appear to have a
     series current-limiting resistor connected.
   ```

4. send that feedback back, asking for the complete corrected specification;
5. keep the best attempt, ranked by fewest errors, then most components.

If a repair attempt fails or returns garbage, the previous specification is
kept. Verification and repair are bounded by `max_repairs`.

---

## 5. Provider notes and performance

| Provider | Structured output mechanism |
|---|---|
| Ollama | native `format` field carrying the JSON schema |
| OpenAI-compatible (NVIDIA NIM, Groq, OpenRouter, HF, Gemini, Together) | `response_format: {type: json_schema, strict: true}` |
| Anthropic | schema appended to the system prompt, then tolerant JSON extraction |

**Latency:** local CPU-only models are slow. Measured on this machine with
`qwen2.5:3b`: roughly 6 generated tokens/second, so a full specification
(200–300 tokens, plus a ~2.9k-character prompt) takes 40–60 seconds, and each
repair attempt costs the same again. Use `max_tokens` to bound a request and set
a generous client timeout. A 7B+ model or a GPU is materially faster; a hosted
OpenAI-compatible endpoint is fastest.

**Accuracy:** a 3B model tends to invent part numbers and omit connections, which
is exactly what the validator and repair loop exist to catch. Larger models
produce valid designs in fewer attempts.

---

## 6. KiCad output: what is verified, and what is not

A design is only delivered if the KiCad output is usable, so this section
records the verified state of each artifact.

### Schematic — VERIFIED

*(Schematic and PCB are both verified as of 2026-10; see the PCB section
below and `CREDITS.md` for the KiCad library licensing that makes embedding
pad and symbol data permissible.)*

The schematic generator previously emitted only `(symbol (lib_id ...))` blocks:
no `lib_symbols` definitions, no `(pin ...)` instances and no wires or labels.
KiCad would open the file but `kicad-cli sch export netlist` returned
`(nets)` — **an empty netlist**. Nothing downstream could have been correct.

It now emits, for every design:

1. a `lib_symbols` definition for each symbol, read from the installed KiCad
   libraries (`src/generators/kicad_symbols.py`);
2. a symbol instance declaring each of its pins with a UUID;
3. a wire stub plus a local label on every connected pin. Labels with the same
   text are the same net, so connectivity does not depend on drawing perfect
   wires between parts.

Verified with `kicad-cli` (KiCad 9.0.2) both by
`tests/test_kicad_netlist.py::TestKiCadAcceptsSchematic` and by
`tools_check_netlist.py`. A generated LDO yields:

```
(net (code "1") (name "/GND")  ... U1 pin 1 (pinfunction "GND")
(net (code "2") (name "/LED_A") ... D1 pin 2 (pinfunction "A"), R1 pin 2
(net (code "3") (name "/VIN")  ... U1 pin 3 (pinfunction "VI"), C1 pin 1
(net (code "4") (name "/VOUT") ... U1 pin 2 (pinfunction "VO"), C2 pin 1, R1 pin 1
```

Notes learned while implementing this, which cost real debugging time:

* Unquoted pin numbers (`(number 1 ...)`) make KiCad reject the *entire* file
  with a bare "Failed to load schematic". Numbers and names must be quoted.
* An `extends` symbol (for example `AMS1117-3.3` extends `AP1117-15`) inherits
  its pins, so the base definition must be followed when reading pins.
* Symbol libraries use a Y-up axis while schematics use Y-down; the Y sign must
  be flipped when converting a pin position to a sheet coordinate.

### PCB — VERIFIED (unrouted)

`generate_pcb()` previously emitted footprints with no pads and wrote track
endpoints as designator references (`(start D1.2)`), where KiCad requires
coordinates; `kicad-cli pcb drc` reported "Failed to load board".

It now emits, for every component:

* a real footprint copied from the installed KiCad footprint libraries
  (`src/generators/kicad_footprints.py`), with its pads, courtyards and silkscreen;
* a net assigned to each pad, matched by pad number, plus board-level net
  declarations;
* a rectangular board outline on `Edge.Cuts`.

Using the real pad definitions is what makes net assignment meaningful: pad
numbers come from the same library the netlist uses, so they line up.

Verified with `kicad-cli` (KiCad 9.0.2) by `tests/test_kicad_pcb.py`:

* the board loads (a DRC report is produced);
* DRC reports **0 unconnected pads, 0 shorts, 0 crossing tracks** on an
  unrouted board — the pads are correctly netted;
* Gerber and drill files export successfully, so the board is manufacturable.

Naive straight-line stub routing is available but **off by default**
(`KiCadGenerator(circuit, route_pcb=True)`), because stubs between pads on the
same net cross other nets and short them. Real routing belongs to FreeRouting.

### Auto-routing — BLOCKED by upstream

FreeRouting consumes Specctra DSN, and `kicad-cli pcb export dsn` was **removed
in KiCad 7** (verified: `kicad-cli pcb export` on KiCad 9.0.2 lists no DSN
subcommand). `src/routing/freerouting.py` already detects this and returns an
explicit error rather than failing silently. Options are KiCad 6 in parallel, an
external DSN converter, or `pcbnew` Python scripting.

### How to re-verify

```bash
python tools_check_netlist.py                 # schematic -> netlist, with kicad-cli
python tools_e2e_check.py --provider mock     # full pipeline, offline
python tools_e2e_check.py --provider ollama --model qwen2.5:3b --timeout 900
pytest tests/test_kicad_netlist.py tests/test_kicad_pcb.py -v
```

---

## 7. Extending the pipeline

To support a new topology:

1. add the parts to `src/components/database.py` (real MPNs with KiCad symbol and
   footprint identifiers),
2. add pinouts to `_IC_PINOUTS` in `src/core/component_resolver.py` if the part
   is an IC (use the real KiCad pin names),
3. add a rule-based fallback spec with connections in `src/llm/integration.py`
   (`_spec_*`), and
4. add a test asserting the resulting circuit passes ERC.

---

## 8. Related files

* `src/llm/providers.py` — provider clients, JSON extraction
* `src/llm/integration.py` — parser, spec generator, repair loop, pipeline
* `src/llm/validation.py` — design validation and LLM feedback rendering
* `src/core/component_resolver.py` — role/type/pin/MPN resolution
* `src/core/circuit_builder.py` — specification → Circuit IR
* `src/core/erc.py` — electrical rule checks
* `src/core/circuit_ir.py` — the canonical representation
* `src/generators/kicad_generator.py` — schematic/PCB S-expression emission
* `src/generators/kicad_symbols.py` — reader for installed KiCad symbol libraries
* `tests/test_llm_providers.py`, `tests/test_circuit_builder.py`,
  `tests/test_llm_pipeline_repair.py`, `tests/test_kicad_netlist.py` — coverage
* `tools_e2e_check.py` — end-to-end check against a real provider
* `tools_check_netlist.py` — verifies the schematic produces a real netlist
