# AI-Powered Electronics Design Platform

---

## Project Purpose

This project builds an AI-powered electronics design platform that transforms natural language circuit descriptions into manufacturing-ready hardware projects.

**Current Capabilities (Implemented):**
1. ✅ Circuit Intermediate Representation (Circuit IR) - canonical data model
2. ✅ Deterministic Electrical Rule Checking (ERC) - 6 validation rules
3. ✅ JLCPCB/LCSC Component Database - offline jlcparts catalog when present, built-in catalog otherwise
4. ✅ KiCad Schematic Generation - S-expression compiler with real electrical
   connectivity, verified by exporting a netlist with `kicad-cli`
5. ✅ ngspice SPICE Simulation - DC op, transient, DC sweep
6. ✅ FreeRouting PCB Auto-routing - DSN export → routing → SES import
7. ✅ Bill of Materials (BOM) Generation - real catalog MPNs, descriptions and pricing
8. ✅ Gerber/Drill Manufacturing Export - via kicad-cli (for valid boards)
9. ✅ CLI Interface - full pipeline from prompt to KiCad project
10. ✅ Natural Language Understanding (LLM integration) - Ollama / OpenAI-compatible / Anthropic,
    with schema-constrained output, catalog-grounded part selection, pin and ERC
    validation, and an automatic repair loop (see `docs/llm-pipeline.md`)

**Known Limitations:**
- ⚠️ **Auto-routing cannot run with KiCad 7+.** FreeRouting needs Specctra DSN
  input, and `kicad-cli pcb export dsn` was removed in KiCad 7 (verified absent
  in KiCad 9.0.2). Generated boards are unrouted; the router reports a clear
  error rather than failing silently. Workarounds: KiCad 6 alongside, an external
  DSN converter, or `pcbnew` scripting.
- ⚠️ The built-in component catalog only covers common parts; the 600k-part
  jlcparts catalog is used automatically when its offline database is present.
- ⚠️ The requirement parser fills defaults for unspecified values instead of
  asking the user.
- ⚠️ A working KiCad installation is required: symbol and footprint libraries
  are read at runtime (see `CREDITS.md` for licensing).

**Planned / In Progress:**
- 🔄 Multi-turn clarification of missing requirements (the parser currently fills defaults)
- 🔄 DSN export path so FreeRouting can run on modern KiCad
- 🔄 Web Frontend (React/TypeScript + Yjs collaboration)
- 🔄 Datasheet Extraction (RAG pipeline)
- 🔄 Smart PCB Placement (thermal, signal integrity)
- 🔄 AI Agent Tool Architecture (MCP)

**It is built exclusively with open-source technologies.**

---

## How It Works: From a Sentence to a Solderable Board

The platform never asks an AI to write KiCad files. Instead it asks the AI for a
**structured specification**, then builds the hardware deterministically. That
split is the core design decision, and this diagram shows the whole path from
your sentence to a board you can order, assemble and power on.

```
┌── 1. YOU DESCRIBE THE CIRCUIT ─────────────────────────────────────────────┐
│                                                                            │
│   "Design a 5V to 3.3V LDO regulator, 500 mA, with an LED power            │
│   indicator."                                                              │
│                                                                            │
│ This is the only thing you have to write.                                  │
└───────────────────────────────────────┬────────────────────────────────────┘
                                        │
                                        ▼
┌── 2. THE PLATFORM APPENDS AN OUTPUT CONTRACT ──────────────────────────────┐
│                                                                            │
│   Your request is not sent as free text. Two things are attached to it:    │
│                                                                            │
│   (a) SYSTEM INSTRUCTIONS                   (b) A JSON SCHEMA              │
│   - emit JSON only, no prose                { topology,                    │
│   - use real manufacturer part                components[],                │
│     numbers                                   connections[],               │
│   - every pin must exist on                   power_domains,               │
│     that part                                 design_notes, warnings }     │
│   - every net needs 2 or more               component: role, mpn, value,   │
│     pins                                      package, reasoning           │
│   - an LED needs a series                   connection: from, to, net      │
│     current-limiting resistor                                              │
│   - ICs need decoupling caps                                               │
│   - do not invent part numbers                                             │
│                                                                            │
│   Grounding: a short list of REAL catalog part numbers is included, so     │
│   the model has something concrete to choose from instead of inventing     │
│   parts.                                                                   │
└───────────────────────────────────────┬────────────────────────────────────┘
                                        │
                                        ▼
┌── 3. AN AI PRODUCES THE SPECIFICATION ─────────────────────────────────────┐
│                                                                            │
│   Local (Ollama) or cloud (OpenAI-compatible / Anthropic): the same        │
│   contract either way. Ollama receives the schema as its native            │
│   `format`; OpenAI-compatible endpoints receive it as `response_format:    │
│   json_schema`. Fenced or chatty replies are still parsed.                 │
│                                                                            │
│ The answer is a specification, NOT a schematic:                            │
│                                                                            │
│   {"topology": "LDO Linear Regulator",                                     │
│    "components": [{"role": "regulator", "mpn": "AMS1117-3.3"}],            │
│    "connections": [{"from": "U1.VIN", "to": "C1.1", "net": "VIN"}]}        │
└───────────────────────────────────────┬────────────────────────────────────┘
                                        │
                                        ▼
┌── 4. DETERMINISTIC PIPELINE (decides if this is buildable) ────────────────┐
│                                                                            │
│   The AI never writes KiCad files. Code does that, and code decides        │
│   whether the answer is physically real:                                   │
│                                                                            │
│   ROLE -> TYPE    MPN -> REAL PART  PIN RESOLUTION   BUILD CIRCUIT IR      │
│   input_capacitor exact catalog hit checked against  components, nets,     │
│    -> Capacitor   else substitute   the installed    power domains and     │
│   led_resistor    with the right    KiCad symbol's   designators (U1,      │
│    -> Resistor    value + package   real pin names   C1, R1, D1 ...)       │
│        |               |                |                 |                │
│        +---------------+-------+--------+-----------------+                │
│                                v                                           │
│   VALIDATE: schema ok | parts exist | pins exist | 6 ERC rules pass        │
│                                |                                           │
│                     errors? ---+- no --> emit KiCad files                  │
│                                |                                           │
│                                +- yes -> REPAIR: hand the model the exact  │
│                                          problems, ask for a corrected     │
│                                          spec, keep the best attempt       │
│                                          (up to N tries)                   │
└───────────────────────────────────────┬────────────────────────────────────┘
                                        │
                                        ▼
┌── 5. WHAT YOU RECEIVE ─────────────────────────────────────────────────────┐
│                                                                            │
│   design.kicad_sch  schematic with REAL electrical connectivity            │
│                     (verified by: kicad-cli sch export netlist)            │
│   design.kicad_pcb  board with real pads, each on its correct net          │
│   design.kicad_pro  KiCad project                                          │
│   design.gltf       3D view                                                │
│   BOM               REAL, purchasable part numbers and prices              │
│   gerbers/ + .drl   fabrication files for a board house                    │
│                                                                            │
│   KiCad itself checks this output in the test suite: netlist extraction,   │
│   DRC and Gerber/drill export all run against generated designs.           │
└───────────────────────────────────────┬────────────────────────────────────┘
                                        │
                                        ▼
┌── 6. YOUR PART ────────────────────────────────────────────────────────────┐
│                                                                            │
│   Order parts from the BOM  ->  have the board made from the Gerbers       │
│   (or etch it yourself)     ->  solder the components  ->  power it on.    │
│                                                                            │
│   The design is ERC-clean and uses real parts, so it is something you      │
│   can actually build -- not a plausible-looking sketch.                    │
└────────────────────────────────────────────────────────────────────────────┘
```json fences are still parsed, so a   │
│   stray wrapper does not break the run.                                    │
│                                                                            │
│ The answer is a specification, NOT a schematic:                            │
│                                                                            │
│   {"topology": "LDO Linear Regulator",                                     │
│    "components": [{"role": "regulator", "mpn": "AMS1117-3.3", ...}],       │
│    "connections": [{"from": "U1.VIN", "to": "C1.1", "net": "VIN"}, ...]}   │
└────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌── 4. DETERMINISTIC PIPELINE (decides if this is buildable) ───────────────┐
│                                                                            │
│   The AI never writes KiCad files. Code does that, and code decides        │
│   whether the answer is physically real:                                   │
│                                                                            │
│   ROLE -> TYPE      MPN -> REAL PART    PIN RESOLUTION      BUILD CIRCUIT IR │
│   input_capacitor   exact catalog hit   checked against     components, nets, │
│    -> Capacitor     or a substitute     the installed       power domains, │
│   led_resistor      with the right      KiCad symbol's      designators (U1, │
│    -> Resistor      value and package   real pin names      C1, R1, D1 ...) │
│         │                  │                  │                   │        │
│         └──────────────────┴────────┬─────────┴───────────────────┘        │
│                                     ▼                                      │
│   VALIDATE:  schema ok | parts exist | pins exist | 6 ERC rules pass       │
│                                     │                                      │
│                          errors? ───┴─── yes ──> REPAIR: hand the model the │
│                             │                     exact problems, ask for a │
│                             │                     corrected spec, keep the │
│                             │                     best attempt (up to N tries) │
│                             ▼  no errors                                   │
└────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌── 5. WHAT YOU RECEIVE ────────────────────────────────────────────────────┐
│                                                                            │
│   design.kicad_sch   schematic with REAL electrical connectivity           │
│                      (verified with: kicad-cli sch export netlist)         │
│   design.kicad_pcb   board with real pads, each pad on its correct net     │
│   design.kicad_pro   KiCad project                                         │
│   design.gltf        3D view                                               │
│   BOM                REAL, purchasable part numbers, descriptions, prices  │
│   gerbers/ + .drl    fabrication files for a board house                   │
│                                                                            │
│   KiCad itself checks this output in the test suite: netlist extraction,   │
│   DRC, and Gerber/drill export all run against generated designs.          │
└────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌── 6. YOUR PART ───────────────────────────────────────────────────────────┐
│                                                                            │
│   Order the parts from the BOM  ->  have the board made from the Gerbers   │
│   (or etch/mill it yourself)    ->  solder the components  ->  power it on. │
│                                                                            │
│   The design is ERC-clean and uses real parts, so it is something you      │
│   can actually build -- not a plausible-looking sketch.                    │
└────────────────────────────────────────────────────────────────────────────┘
```json wrapper does not break the run.      │
│                                                                             │
│    Output is a specification, NOT a schematic:                              │
│      {"topology": "LDO Linear Regulator",                                   │
│       "components": [{"role": "regulator", "mpn": "AMS1117-3.3", ...}],      │
│       "connections": [{"from": "U1.VIN", "to": "C1.1", "net": "VIN"}, ...]}  │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. DETERMINISTIC PIPELINE — the part that decides whether this is buildable │
│                                                                             │
│  ┌──────────────┐   ┌──────────────┐   ┌──────────────┐   ┌──────────────┐  │
│  │ ROLE → TYPE  │   │ MPN → REAL   │   │ PIN RESOLVE  │   │ BUILD CIRCUIT│  │
│  │ "input_cap"  │   │ PART         │   │ against the  │   │ IR:  comps,  │  │
│  │  → Capacitor │   │ exact catalog│   │ installed    │   │ nets, power  │  │
│  │ "led_resist" │   │ hit, else a  │   │ KiCad symbol │   │ domains, with│  │
│  │  → Resistor  │   │ substitute   │   │ pin names    │   │ designators  │  │
│  └──────────────┘   └──────────────┘   └──────────────┘   └──────────────┘  │
│                                                                             │
│  ┌───────────────────────────────────────────────────────────────────────┐  │
│  │ VALIDATE:  schema ✓   parts exist ✓   pins exist ✓   ERC rules ✓      │  │
│  └───────────────────────────────┬───────────────────────────────────────┘  │
│                                  │                                          │
│                        errors? ──┴── yes ──▶  ┌──────────────────────────┐  │
│                                              │ REPAIR: send the model   │  │
│                                              │ the exact problems and   │  │
│                                              │ ask for a corrected spec │  │
│                                              └────────────┬─────────────┘  │
│                                                           │ (up to N tries)│
│                              no errors ◀──────────────────┘                 │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. WHAT YOU RECEIVE                                                         │
│                                                                             │
│   design.kicad_sch ──► schematic with REAL electrical connectivity          │
│                        (checks with: kicad-cli sch export netlist)          │
│   design.kicad_pcb ──► board with real pads, each pad on its correct net    │
│   design.kicad_pro ──► KiCad project                                        │
│   design.gltf      ──► 3D view                                              │
│   design-BOM       ──► bill of materials with REAL, purchasable MPNs,       │
│                        descriptions and indicative prices                   │
│   gerbers/ + .drl  ──► fabrication files you can send to a board house      │
│                                                                             │
│   Verified by KiCad itself: netlist extraction, DRC, and Gerber/drill       │
│   export all run against generated output in the test suite.                │
└───────────────────────────────────┬─────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 6. YOUR PART                                                               │
│                                                                             │
│   Order the parts from the BOM  →  have the board made from the Gerbers     │
│   (or etch/mill it yourself)    →  solder the components                    │
│   →  power it on.                                                           │
│                                                                             │
│   The design is ERC-clean and uses real parts, so it is a design you can    │
│   actually build — not a plausible-looking sketch.                          │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Why the contract is appended (and why it matters)

Without the appended schema, a model returns prose or a schematic sketch that no
program can use. Two details make the contract work in practice:

1. **It is attached to the request, not left to the prompt.** The schema is
   derived from the same definition the validator enforces, so what the model is
   asked for and what it is checked against cannot drift apart.
2. **It constrains wording, not physics.** A perfectly formed JSON answer can
   still name a part that does not exist or a pin that is not on the symbol.
   That is why step 4 exists: format is necessary but never sufficient.

### What each later stage does

| Stage | What it does | What would go wrong without it |
|---|---|---|
| Role → type | `"input_capacitor"` becomes `Capacitor`, so the right symbol and pins are used | A part with the wrong footprint or no pinout |
| MPN → real part | Matches the requested part number against the catalog; substitutes a real equivalent when absent | A bill of materials you cannot order |
| Pin resolution | Resolves pin numbers/names against the installed KiCad symbol, including aliases (`VOUT` → the symbol's real `VO`) | Silent shorts or disconnected nets |
| Circuit IR build | Assigns designators (U1, C1, R1…) and connects nets | No stable identity for parts or nets |
| Validation | Schema, MPN existence, pin existence, and 6 ERC rules | A board that looks fine and does not work |
| Repair loop | Sends the specific errors back to the model and retries, keeping the best attempt | One bad answer ends the run |
| Emit | Deterministic S-expression writers for schematic and PCB | Files KiCad cannot open or netlist |

---

## Architecture Overview

```
Natural Language Prompt
         │
         ▼
┌──────────────────────────────────────┐
│  AIDesignOrchestrator (pipeline)     │
└──────────────────────────────────────┘
         │
    ┌────┼────┐
    ▼    ▼    ▼
┌──────┐ ┌──────────┐ ┌─────────────┐
│ JLC  │ │ Circuit  │ │   ERC       │
│Parts │ │    IR    │ │ Validator   │
│  DB  │ │          │ │             │
└──────┘ └──────────┘ └─────────────┘
    │         │            │
    ▼         ▼            ▼
┌──────────────────────────────────────┐
│  KiCad Generator (S-expressions)     │
│  .kicad_sch  .kicad_pcb  .kicad_pro  │
└──────────────────────────────────────┘
    │
    ├─▶ ngspice (SPICE simulation)
    ├─▶ FreeRouting (PCB auto-routing; see Known Limitations)
    └─▶ kicad-cli (netlist/ERC/DRC/Gerber/drill)
```

---

## What We Build Ourselves vs. Use

### ✅ We BUILD (Implemented):
- Circuit Intermediate Representation (`src/core/circuit_ir.py`)
- ERC Engine with 6 deterministic rules (`src/core/erc.py`)
- KiCad S-expression Generator (`src/generators/kicad_generator.py`)
- SPICE Netlist Compiler (`src/simulation/ngspice.py`)
- FreeRouting Integration (`src/routing/freerouting.py`)
- JLCParts Database Wrapper (`src/components/jlcparts.py`)
- Unified Component Database (`src/components/database.py`)
- AI Design Orchestrator Pipeline (`src/agents/orchestrator.py`)
- CLI Entry Point (`main.py`)

### 🔧 We USE via subprocess (MIT/GPL-compatible):
- **KiCad 8+** (`kicad-cli`) - EDA engine, ERC, DRC, Gerber, DSN export, SES import
- **ngspice** - SPICE simulation (batch mode)
- **FreeRouting** - PCB autorouter (Java JAR)
- **yaqwsx/jlcparts** - Offline component catalog (SQLite, CC0)

### 📦 External References (in `external/` submodules):
- `kicad-tools` - KiCad automation utilities
- `kicad-mcp-server` - MCP server for KiCad
- `freerouting` - Autorouter source
- `ngspice` - SPICE simulator source
- `circuit-json-to-kicad` - Circuit JSON converter
- `pcbparts-mcp` - Component database tools

---

## Technical Stack (Current)

| Layer | Technology | License | Status |
|-------|------------|---------|--------|
| **Circuit IR** | Custom (Python) | GPL-3.0 | ✅ Implemented |
| **ERC** | Custom (Python) | GPL-3.0 | ✅ Implemented |
| **Component DB** | JLCParts (yaqwsx/jlcparts) | CC0 | ✅ Implemented |
| **EDA Engine** | KiCad 8 (`kicad-cli`) | GPL-3.0 | ✅ Integrated |
| **Schematic/PCB Gen** | Custom S-expression compiler | GPL-3.0 | ✅ Implemented |
| **Routing** | FreeRouting | GPL-3.0 | ✅ Integrated |
| **Simulation** | ngspice | BSD-3-Clause | ✅ Integrated |
| **CLI** | Python argparse | GPL-3.0 | ✅ Implemented |

*Planned: FastAPI/PostgreSQL (Backend), React/TypeScript/Yjs (Frontend)*

---

## License

This project is licensed under **GNU GPL-3.0**. Third-party components,
their licenses, and the KiCad library exception that permits generated designs
to be used freely are documented in `CREDITS.md`.

**Important:** The GPL-3.0 license applies to the code you write. External GPLv3 tools (KiCad, FreeRouting) are used via subprocess calls, which helps maintain license separation.

---

## Getting Started

### Quick start

```bash
git clone <repository-url>
cd AI-Powered-Electronics-Design-Platform

python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"          # runtime + test dependencies

# Generate a design with the built-in deterministic generator (no AI needed)
ai-electronics-design -p "Design a 5V to 3.3V LDO regulator with an LED indicator" \
    --no-spice --no-routing -o ./output_design

# Confirm the setup can actually verify its own output
pytest -q
```

This writes a KiCad project to `./output_design`:

| File | What it is |
|---|---|
| `<name>.kicad_sch` | Schematic with real electrical connectivity |
| `<name>.kicad_pcb` | Board with real pads, each assigned to its net |
| `<name>.kicad_pro` | KiCad project |
| `<name>.gltf` | 3D view |
| `design_summary.json` | Full result: specification, validation, BOM, notes |

Then either open it in KiCad, or verify it from the command line:

```bash
kicad-cli sch export netlist --output /tmp/check.net ./output_design/*.kicad_sch
kicad-cli pcb drc --output /tmp/drc.rpt ./output_design/*.kicad_pcb
```

### Using a real AI

The `mock` provider (the default) runs the deterministic rule-based generator, so
you can try the whole pipeline with no API key and no model download. To let a
model design the circuit instead:

```bash
# Local model via Ollama
ollama pull qwen2.5:3b
ai-electronics-design -p "Design a 5V to 3.3V LDO regulator, 500 mA, with an LED" \
    --provider ollama --model qwen2.5:3b --no-spice --no-routing

# Any OpenAI-compatible endpoint (NVIDIA NIM, Groq, OpenRouter, Gemini, ...)
export NVIDIA_API_KEY=...
ai-electronics-design -p "Create a 12V to 5V buck converter, 3A output" \
    --provider openai --base-url https://integrate.api.nvidia.com/v1 \
    --model nvidia/nemotron-3-ultra-550b-a55b

# Fail instead of silently falling back to the template generator
ai-electronics-design -p "..." --provider ollama --strict
```

Every result reports its own provenance. If the model was unavailable and the
template generator was used instead, the run says so explicitly — a canned
design is never presented as an AI-generated one.

Note: a small local model on CPU is slow (roughly 5–6 generated tokens/second on
the reference machine, so budget a minute or more per attempt). Hosted endpoints
are far quicker for interactive use. See `docs/llm-pipeline.md`.

### Requirements

| Requirement | Needed for | Notes |
|---|---|---|
| Python 3.10+ | Everything | Tested on 3.13 |
| **KiCad** (9.x) | Schematic/PCB generation, ERC, DRC, Gerbers | Provides `kicad-cli` **and** the symbol/footprint libraries the generators read at runtime. `.kicad_sym` / `.kicad_footprint` data is not vendored — see `CREDITS.md` |
| ngspice | SPICE simulation | Optional; simulation is reported as failed, not silently skipped, when absent |
| Node.js 18+ | Web frontend only | Not needed for the CLI |
| Java 25 | FreeRouting auto-routing | Currently a blocker: every bundled jar targets Java 25 and will not run on Java 21. See Known Limitations |

Verify the system dependencies:

```bash
kicad-cli --version          # expect 8.x or 9.x
ngspice --version | head -1
```

The test suite skips the KiCad acceptance tests when `kicad-cli` is absent. In
CI, `DSH_REQUIRE_KICAD=1` turns that skip into a failure, so "verified against
KiCad" can never quietly become "skipped".

### System Dependencies (.deb packages)

Install required system packages **once**:

```bash
# Update package list
sudo apt-get update

# Install required system packages
sudo apt-get install -y \
    python3 python3-venv python3-dev \
    kicad \
    ngspice \
    kicad-footprints kicad-symbols kicad-templates

# Optional extras
sudo apt-get install -y \
    librepcb horizon-eda \
    sch-rnd-sim pcb-rnd \
    default-jre  # For FreeRouting (version mismatch — see Known Limitations)
```

> On Debian/Ubuntu, `kicad-cli` ships inside the `kicad` package; installing a
> separate `kicad-cli` package is not needed on current releases.

### Python Virtual Environment (One-Time Setup)

Create and configure the virtual environment **once**:

```bash
# Clone the repository
git clone https://github.com/wachin/AI-Powered-Electronics-Design-Platform
cd AI-Powered-Electronics-Design-Platform

# Initialize submodules (reference implementations)
git submodule update --init --recursive

# Create virtual environment (ONLY ONCE)
# Note: Use `python3` (not python3.11) - the system's default python3
# The python3-venv package will install the appropriate venv module
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip and install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Install external submodule tools (optional, for development)
# IMPORTANT: There is a KNOWN INCOMPATIBILITY between kicad-mcp-server and pcbparts-mcp:
# - kicad-mcp-server requires mcp>=1.27 (installs mcp 1.30.0)
# - pcbparts-mcp requires mcp==1.25.0 (exact version)
# THESE ARE FUNDAMENTALLY INCOMPATIBLE - you cannot have both installed simultaneously.
# 
# Choose ONE of the following options:
# 
# Option A: Use kicad-mcp-server (recommended for KiCad MCP integration)
pip install -e external/kicad-mcp-server
pip install -e external/kicad-tools
# DO NOT install pcbparts-mcp if you need kicad-mcp-server

# Option B: Use pcbparts-mcp (for PCB parts database)
# pip install -e external/pcbparts-mcp
# pip install -e external/kicad-tools
# # DO NOT install kicad-mcp-server if you need pcbparts-mcp

# Verify installations
kicad-cli --version
ngspice --version
```

# Verify installations
kicad-cli --version
ngspice --version
```

---

## Daily Usage (Every Session)

**You must perform these steps every time you start a new terminal session:**

### ⚡ Quick Reference

```bash
# Activate environment (every session)
source venv/bin/activate

# Run tests
PYTHONPATH=. pytest tests/ -v

# Run design pipeline
python main.py -p "Design a 5V to 3.3V LDO regulator with LED indicator"

# Run without SPICE/routing for quick testing
python main.py -p "Simple LED circuit" --no-spice --no-routing

# Deactivate when done
deactivate
```

## 1. Activate Virtual Environment

```bash
cd AI-Powered-Electronics-Design-Platform
source venv/bin/activate
```

You'll see `(venv)` in your prompt, indicating the virtual environment is active.

### 2. Run Tests

```bash
# Run all tests
PYTHONPATH=. pytest tests/ -v

# Run specific test file
PYTHONPATH=. pytest tests/test_ai_agent.py -v

# Run with coverage
PYTHONPATH=. pytest tests/ --cov=src --cov-report=term-missing
```

### 3. Run the Design Pipeline

```bash
# Full pipeline (ERC + SPICE + KiCad + FreeRouting)
python main.py -p "Design a 5V to 3.3V LDO regulator with LED indicator"

# Without SPICE simulation
python main.py -p "Design a 5V to 3.3V LDO regulator" --no-spice

# Without PCB auto-routing
python main.py -p "Simple LED circuit" --no-routing

# Minimal (ERC + KiCad only)
python main.py -p "Simple LED circuit" --no-spice --no-routing
```

### 4. Deactivate Virtual Environment

When you're done working:

```bash
deactivate
```

---

## ⚠️ Important: One-Time vs. Repeated Steps

| Step | Frequency | Commands |
|------|-----------|----------|
| **Install system packages** | **ONCE** | `sudo apt-get install ...` |
| **Create virtual environment** | **ONCE** | `python3 -m venv venv` |
| **Install Python dependencies** | **ONCE** | `pip install -r requirements.txt` |
| **Activate virtual environment** | **EVERY SESSION** | `source venv/bin/activate` |
| **Run tests** | **EVERY SESSION** | `PYTHONPATH=. pytest tests/ -v` |
| **Run design pipeline** | **EVERY SESSION** | `python main.py -p "..."` |
| **Deactivate venv** | **EVERY SESSION** | `deactivate` |

> **⚠️ IMPORTANT:** Do NOT re-run the one-time setup steps (installing packages, creating venv, pip install) every time. They only need to be done once. The virtual environment activation and test execution must be done every time you start a new terminal session.

---

## Verification Commands

```bash
# Verify all tools are working
kicad-cli --version       # Should show 9.x.x
ngspice --version         # Should show 44.x
python -c "import src; print('Python imports OK')"
```

---

## Installed System Packages Summary

| Package | Purpose |
|---------|---------|
| `python3-venv` | Virtual environment support (installs python3.13-venv) |
| `kicad`, `kicad-cli` | Primary EDA engine |
| `librepcb`, `horizon-eda` | Alternative EDA engines |
| `ngspice`, `ngspice-dev`, `ngspice-doc` | SPICE simulation CLI + docs |
| `librepcb`, `horizon-eda` | Alternative EDA engines |
| `kicad-footprints`, `kicad-symbols`, `kicad-templates` | KiCad libraries (via kicad-libraries) |
| `sch-rnd-sim` | High-level circuit simulation |
| `pcb-rnd` | Alternative PCB tool |
| `default-jre` | Java runtime for FreeRouting |
| `default-jdk` | Java development kit (for FreeRouting dev) |

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `venv/bin/activate: No such file` | Run `python3.11 -m venv venv` first |
| `ModuleNotFoundError` | Run `pip install -r requirements.txt` with venv active |
| `kicad-cli: command not found` | Install `kicad` package: `sudo apt-get install kicad` |
| `ngspice: command not found` | Install ngspice: `sudo apt-get install ngspice` |
| `pytest: command not found` | Run `pip install pytest` in active venv |
| `freerouting.jar not found` | Build: `cd external/freerouting && ./gradlew build -x test` |
| Tests fail with `PermissionError` | Ensure sandbox paths are correct in `src/security/sandbox.py` |

---

## External Submodules (Reference Only)

The `external/` directory contains Git submodules for reference only. They are **not required** for the main platform to function:

```
external/
├── kicad-tools/           # KiCad automation utilities
├── kicad-mcp-server/      # MCP server for KiCad
├── freerouting/           # Autorouter source (build with ./gradlew)
├── ngspice/               # SPICE simulator source
├── circuit-json-to-kicad/ # Circuit JSON converter
└── pcbparts-mcp/          # Component database tools
```

Initialize submodules if you want to explore them:
```bash
git submodule update --init --recursive
```

---

## Running the Full Test Suite

```bash
# Everything (no PYTHONPATH needed: pytest config lives in pyproject.toml)
pytest -q

# Just the unit tests, skipping the KiCad acceptance gates
pytest -q --ignore=tests/test_kicad_netlist.py --ignore=tests/test_kicad_pcb.py

# With coverage
pytest --cov=src --cov-report=term-missing
```

The acceptance tests (`test_kicad_netlist.py`, `test_kicad_pcb.py`) ask KiCad to
read generated output — netlist extraction, DRC and Gerber/drill export. They
skip automatically when `kicad-cli` is not installed, and fail instead of
skipping when `DSH_REQUIRE_KICAD=1` is set (as CI does).

---

## Legal Notice

⚠️ **IMPORTANT:** This software is an independent open-source implementation that does NOT copy or derive from Flux.ai. See `LEGAL_NOTICE.md` and `LEGAL_DISCLAIMER.md` for details. `research/flux-ai-patent-search.md` explains how to look up Flux.ai patents and compare them against this repository yourself; it contains no patent numbers, because the maintainers have not run a citable search.

---

*This project is licensed under GNU GPL-3.0. See `LICENSE` file for details.*

## CLI Usage

```bash
python main.py --help

Options:
  -p, --prompt TEXT       Natural language circuit description
  -o, --output-dir PATH   Output directory (default: ./output_design)
  -n, --project-name TEXT Project name (default: ldo_regulator)
  --no-spice              Disable SPICE simulation
  --no-routing            Disable PCB auto-routing
```

### Example Prompts

```bash
# Voltage regulator
python main.py -p "Design a 5V to 3.3V LDO regulator circuit with green LED indicator and decoupling capacitors"

# Simple circuit (no SPICE/routing needed)
python main.py -p "Simple LED circuit with current limiting resistor" --no-spice --no-routing

# Buck converter (uses component database search)
python main.py -p "Create a 12V to 5V buck converter 3A output"
```

---

## Project Structure

```
AI-Powered-Electronics-Design-Platform/
├── main.py                          # CLI shim (implementation in src/cli.py)
├── pyproject.toml                   # Packaging, dependencies, pytest config
├── requirements.txt                 # pip-installable dependency list
├── ROADMAP.md                       # Development roadmap with checkboxes
├── CREDITS.md                       # Third-party licenses (incl. KiCad data)
├── AGENTS.md                        # Agent policies
├── LEGAL_NOTICE.md                  # Legal notice
├── LEGAL_DISCLAIMER.md              # Legal disclaimer
├── .github/workflows/ci.yml         # CI: tests (with KiCad), frontend, compile
├── docs/
│   └── llm-pipeline.md             # Pipeline architecture + verification status
├── research/
│   └── flux-ai-patent-search.md    # Patent search + independence verification
├── tools_check_netlist.py           # Verifies schematic -> real KiCad netlist
├── tools_e2e_check.py               # End-to-end check against a real LLM
├── src/
│   ├── cli.py                      # CLI implementation
│   ├── core/
│   │   ├── circuit_ir.py           # Circuit Intermediate Representation
│   │   ├── circuit_builder.py      # Specification -> Circuit IR (real parts/pins)
│   │   ├── component_resolver.py   # Role/type/pin/MPN resolution
│   │   └── erc.py                  # Electrical Rule Checker
│   ├── components/
│   │   ├── database.py             # Unified component database
│   │   └── jlcparts.py             # JLCPCB/LCSC catalog wrapper
│   ├── llm/
│   │   ├── providers.py            # Ollama / OpenAI-compatible / Anthropic clients
│   │   ├── integration.py          # NL -> spec -> repair loop -> Circuit IR
│   │   └── validation.py           # Design validation and repair feedback
│   ├── generators/
│   │   ├── kicad_generator.py      # KiCad S-expression compiler
│   │   └── kicad_symbols.py        # Reader for installed KiCad symbol libraries
│   ├── simulation/
│   │   └── ngspice.py              # SPICE simulation integration
│   ├── routing/
│   │   └── freerouting.py          # FreeRouting autorouter wrapper
│   ├── pcb/
│   │   └── smart_placement.py      # Placement engine (NOT yet wired in)
│   ├── security/
│   │   ├── permissions.py          # Capability-based permissions (NOT wired in)
│   │   └── sandbox.py              # Process/path sandboxing (NOT wired in)
│   ├── agents/
│   │   ├── orchestrator.py         # AI design pipeline
│   │   ├── ai_agent.py             # Agent + MCP tools (NOT wired in)
│   │   └── mcp_client.py           # MCP stdio client
│   └── api/
│       └── main.py                 # FastAPI REST API backend
├── tests/
│   ├── test_circuit_ir.py
│   ├── test_component_db.py
│   ├── test_erc.py
│   ├── test_kicad_generator.py
│   ├── test_kicad_netlist.py       # verifies KiCad extracts a real netlist
│   ├── test_circuit_builder.py     # spec -> Circuit IR + validation
│   ├── test_llm_providers.py       # real provider request/response handling
│   ├── test_llm_pipeline_repair.py # validated generation and repair loop
│   ├── test_ngspice.py
│   ├── test_freerouting.py
│   ├── test_smart_placement.py
│   ├── test_security.py
│   ├── test_ai_agent.py
│   └── test_orchestrator.py
├── frontend/                        # React/TypeScript web frontend
│   ├── src/
│   │   ├── components/             # DesignForm, JobStatus, ComponentSearch, Header, Toast
│   │   ├── lib/api.ts              # Axios API client
│   │   ├── types.ts                # TypeScript interfaces
│   │   ├── App.tsx                 # Main app with routing
│   │   ├── main.tsx                # Entry point + ToastProvider
│   │   └── index.css               # Global styles (dark theme)
│   ├── package.json                # NPM dependencies
│   ├── vite.config.ts              # Vite config with API proxy
│   └── tsconfig.json               # TypeScript config
├── api_output/                      # Runtime output (gitignored)
│   └── <job_id>/                   # Per-job KiCad project files
├── external/                        # Git submodules (reference only)
│   ├── kicad-tools/
│   ├── kicad-mcp-server/
│   ├── freerouting/
│   ├── ngspice/
│   ├── circuit-json-to-kicad/
│   └── pcbparts-mcp/
└── research/
    └── flux-ai-patent-search.md
```

---

## Disclaimer

THE AUTHORS PROVIDE NO WARRANTIES, EXPRESS OR IMPLIED, INCLUDING WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, OR NONINFRINGEMENT. THE AUTHORS ARE NOT LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER LIABILITY ARISING FROM THE USE OF THIS SOFTWARE.

PORTABILITY OF THIS SOFTWARE TO YOUR SPECIFIC USE CASE IS YOUR RESPONSIBILITY.

---

## Contributing

If you contribute:

1. You grant a GPL-3.0 license to your contributions
2. You represent that you have the right to contribute the code
3. You accept the project's license

---

## Related Documentation

| File | Purpose |
|------|---------|
| `ROADMAP.md` | Development plan with implementation status checkboxes |
| `docs/llm-pipeline.md` | LLM pipeline architecture, postmortem, and verified KiCad status |
| `CREDITS.md` | Third-party dependencies, licenses, and the KiCad library exception |
| `AGENTS.md` | Agent policies for external repositories |
| `LEGAL_NOTICE.md` | Legal notice |
| `LEGAL_DISCLAIMER.md` | Legal disclaimer |
| `research/flux-ai-patent-search.md` | How to search Flux.ai patents and verify independent implementation |

---

## Legal Notice

**⚠️ IMPORTANT: READ THIS ENTIRE FILE BEFORE USING THIS SOFTWARE**

---

**THIS SOFTWARE IS AN INDEPENDENT OPEN-SOURCE IMPLEMENTATION THAT DOES NOT COPY OR DERIVE FROM FLUX.AI**.

Flux.ai is a proprietary commercial product. This project:

- Is **NOT** affiliated with Flux Lab Inc.
- Does **NOT** use Flux.ai's source code, trademarks, or proprietary assets
- References Flux.ai **only** for technical analysis and educational purposes
- Implements similar functionality using **only open-source tools**

**READ THE FOLLOWING FILES FOR LEGAL INFORMATION:**
- `LEGAL_NOTICE.md` - Legal considerations
- `LEGAL_DISCLAIMER.md` - Detailed legal guidance
- `research/flux-ai-patent-search.md` - How to search Flux.ai patents and verify, subsystem by subsystem, that this project is an independent implementation (this project does **not** use, implement, or derive from any Flux.ai patents)