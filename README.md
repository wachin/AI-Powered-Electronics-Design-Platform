# AI-Powered Electronics Design Platform

<!--
  Badges are static on purpose. A CI status badge is only added once this
  repository has actually run the "CI" workflow on GitHub, so that it reports a
  real result instead of a plausible-looking placeholder.
  Every claim below is verifiable: LICENSE, pyproject.toml, and the test suite.
-->
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-224%20passing%2C%202%20skipped-brightgreen.svg)](tests/)
[![KiCad](https://img.shields.io/badge/KiCad-8.x%20%7C%209.x-1a5fb4.svg)](https://www.kicad.org/)
[![ngspice](https://img.shields.io/badge/ngspice-44.x-orange.svg)](https://ngspice.sourceforge.io/)
[![Status](https://img.shields.io/badge/status-alpha-yellow.svg)](#known-limitations)
[![LLM providers](https://img.shields.io/badge/LLM-Ollama%20%7C%20OpenAI--compatible%20%7C%20Anthropic-6f42c1.svg)](docs/llm-pipeline.md)

**Turn a sentence into a validated, manufacturable KiCad project.**

Describe the circuit you need in plain language. The platform asks an AI for a
*structured specification*, checks that specification against real parts, real
pins and electrical rules, and then compiles it — deterministically — into a
KiCad schematic and PCB, a bill of materials you can order, and Gerber files you
can send to a board house.

**What works today:** the full path from prompt to an ERC-clean KiCad project
with a correct netlist and Gerbers. **Not yet:** PCB auto-routing (blocked by a
Java version mismatch) and datasheet understanding. See
[Known Limitations](#known-limitations).

---

## Project Purpose

This project builds an AI-powered electronics design platform that transforms natural language circuit descriptions into manufacturing-ready hardware projects.

**Current Capabilities (Implemented):**
1. ✅ Circuit Intermediate Representation (Circuit IR) - canonical data model
2. ✅ Deterministic Electrical Rule Checking (ERC) - 6 validation rules
3. ✅ Component Database - offline jlcparts catalog (MIT) when present, built-in catalog otherwise
4. ✅ KiCad Schematic Generation - S-expression compiler with real electrical
   connectivity, verified by exporting a netlist with `kicad-cli`
5. ✅ ngspice SPICE Simulation - DC op, transient, DC sweep
6. ⛔ PCB Auto-routing - wrapper written, **blocked** (Java version mismatch); see Known Limitations
7. ✅ Bill of Materials (BOM) Generation - real catalog MPNs, descriptions and pricing
8. ✅ Gerber/Drill Manufacturing Export - verified on generated boards via `kicad-cli`
9. ✅ CLI Interface - full pipeline from prompt to KiCad project
10. ✅ Natural Language Understanding (LLM integration) - Ollama / OpenAI-compatible / Anthropic,
    with schema-constrained output, catalog-grounded part selection, pin and ERC
    validation, and an automatic repair loop (see `docs/llm-pipeline.md`)

### Known Limitations
- ⚠️ **PCB auto-routing does not run on a current KiCad install.** Three
  separate blockers, all verified:
  1. `kicad-cli pcb export dsn` was **removed in KiCad 7** and
     `kicad-cli pcb import ses` never existed. (The working path is
     `pcbnew.ExportSpecctraDSN` / `pcbnew.ImportSpecctraSES`, which are available.)
  2. Every bundled FreeRouting jar is compiled for **Java 25**; this machine runs
     Java 21, so the jars refuse to start.
  3. The wrapper still calls the removed `kicad-cli` subcommands instead of
     `pcbnew`.
  Generated boards are therefore **unrouted**: route them in KiCad's editor, or
  fix the three items above. The router reports a clear error rather than
  failing silently.
- ⚠️ The built-in component catalog covers only common parts. The full
  jlcparts catalog is used automatically when its offline database is present,
  but it is **not** bundled — without it, part substitution is limited.
- ⚠️ Several implemented subsystems are **not wired into the pipeline**:
  smart PCB placement, the permission system, the sandbox, and the MCP agent.
  See [`ROADMAP.md` §22](ROADMAP.md) for the verified list.
- ⚠️ The requirement parser fills defaults for unspecified values instead of
  asking the user.
- ⚠️ A working KiCad installation is required: symbol and footprint libraries
  are read at runtime (see `CREDITS.md` for licensing).

### Planned / In Progress

- 🔄 DSN/SES path via `pcbnew`, plus a Java 25 runtime, to make auto-routing work
- 🔄 Wiring the orphaned modules into the pipeline (placement first)
- 🔄 Multi-turn clarification of missing requirements (the parser currently fills defaults)
- 🔄 Datasheet understanding / RAG (section 8 of the ROADMAP)
- 🔄 Enclosure generation and 3D component models

### Status of the larger pieces

| Piece | State |
|---|---|
| CLI + Python API | ✅ Works |
| Natural language → specification | ✅ Works (local or cloud LLM) |
| Specification → validated Circuit IR | ✅ Works |
| Schematic + PCB + Gerbers | ✅ Works and is KiCad-verified |
| SPICE simulation | ✅ Works |
| Web frontend + collaboration | ✅ Implemented (builds, WebSocket server present) |
| PCB autorouting | ⛔ Blocked (see above) |
| Smart placement / permissions / sandbox / MCP agent | ⚠️ Implemented but not wired in |
| Datasheet understanding | ❌ Not started |

**Built with open-source technologies.** (KiCad, ngspice and FreeRouting are used
as  programs; AI features can talk to hosted providers if you configure
one, or run fully locally with Ollama.)

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
└──────────────────────────────────────┬─────────────────────────────────────┘
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
└──────────────────────────────────────┬─────────────────────────────────────┘
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
└──────────────────────────────────────┬─────────────────────────────────────┘
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
└──────────────────────────────────────┬─────────────────────────────────────┘
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
└──────────────────────────────────────┬─────────────────────────────────────┘
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

### ✅ We build (implemented)

Core data model and engineering checks:

- Circuit Intermediate Representation (`src/core/circuit_ir.py`)
- Specification → Circuit IR builder, with real MPNs and pins (`src/core/circuit_builder.py`)
- Role/pin/MPN resolution against real KiCad symbols (`src/core/component_resolver.py`)
- ERC engine, 6 deterministic rules (`src/core/erc.py`)

AI layer:

- LLM providers: Ollama, OpenAI-compatible, Anthropic (`src/llm/providers.py`)
- Specification generation, validation and repair loop (`src/llm/integration.py`, `src/llm/validation.py`)

Output and verification:

- KiCad schematic + PCB S-expression compiler (`src/generators/kicad_generator.py`)
- Readers for installed KiCad symbol/footprint libraries (`kicad_symbols.py`, `kicad_footprints.py`)
- SPICE netlist compiler (`src/simulation/ngspice.py`)
- 3D glTF export (`src/generators/gltf_exporter.py`)
- Component database (`src/components/database.py`, `jlcparts.py`)
- Orchestrator, FastAPI backend, CLI (`src/agents/orchestrator.py`, `src/api/main.py`, `src/cli.py`)

### 🔧 Used as  programs (not linked)

- **KiCad** (`kicad-cli`) — netlist export, ERC, DRC, Gerber/drill export.
  Note: **no DSN export or SES import** — those `kicad-cli` subcommands do not
  exist in KiCad 7+ (the `pcbnew` Python API does provide them).
- **KiCad symbol + footprint libraries** — read at runtime for pin geometry and
  pad definitions. CC-BY-SA-4.0 with a design exception; see `CREDITS.md`.
- **ngspice** — SPICE simulation (batch mode).
- **FreeRouting** — PCB autorouter (Java JAR). Not currently runnable; see Known Limitations.
- **yaqwsx/jlcparts** — offline component catalog (MIT, SQLite).

### 📦  references (in `/`, reference only)

32 Git submodules are available for study — none are imported, linked, or
required. Highlights: `kicad`, `kicad-tools`, `kicad-mcp-server`, `circuit-json`,
`tscircuit`, `skidl`, `atopile`, `circuit-synth`, `freerouting`, `ngspice`,
`pyspice`, `yjs`, `automerge`, `jlcparts`, `librepcb`, `ecad-viewer`.

See `research/repository_catalog.md` for the full list with licenses, and
`AGENTS.md` for the reference-only policy.

---

## Technical Stack (Current)

| Layer | Technology | License | Status |
|-------|------------|---------|--------|
| **Circuit IR** | Custom (Python) | GPL-3.0 | ✅ Implemented |
| **ERC** | Custom (Python) | GPL-3.0 | ✅ Implemented |
| **Component DB** | JLCParts (yaqwsx/jlcparts) | MIT | ✅ Implemented |
| **EDA Engine** | KiCad 8.x / 9.x (`kicad-cli`) | GPL-3.0 | ✅ Integrated |
| **Schematic/PCB Gen** | Custom S-expression compiler | GPL-3.0 | ✅ Implemented |
| **Routing** | FreeRouting | GPL-3.0 | ⛔ Blocked (Java 25 jars, Java 21 runtime) |
| **Simulation** | ngspice | BSD-3-Clause | ✅ Integrated |
| **CLI** | Python argparse | GPL-3.0 | ✅ Implemented |
| **API** | FastAPI | MIT | ✅ Implemented |
| **LLM** | Ollama / OpenAI-compatible / Anthropic | provider-specific | ✅ Integrated |

*Implemented: FastAPI backend (`src/api/`), React/TypeScript/Yjs frontend (`frontend/`).*
*Planned: PostgreSQL persistence; datasheet understanding.*

---

## Getting Started

### Quick start

```bash
git clone https://github.com/wachin/AI-Powered-Electronics-Design-Platform
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

## CLI Usage

```bash
ai-electronics-design --help      # or: python main.py --help

Options:
  -p, --prompt TEXT         Natural language circuit description
  -o, --output-dir PATH     Output directory (default: ./output_design)
  -n, --project-name TEXT   Project name (default: ldo_regulator)
  --provider {mock,ollama,openai,anthropic}
                            mock = deterministic generator (default);
                            ollama = local model; openai = any OpenAI-compatible
                            endpoint (use --base-url); anthropic = Claude API
  --model TEXT              Model name for the provider (e.g. qwen2.5:3b)
  --base-url TEXT           Provider base URL (e.g. http://localhost:11434)
  --max-repairs INT         How many times an invalid design is sent back (default: 2)
  --strict                  Fail instead of falling back to the template generator
  --mcp-validate            Also validate with an MCP server (needs mcp-setup)
  --no-spice                Disable SPICE simulation
  --no-routing              Disable PCB auto-routing

Subcommands:
  mcp-status                Show optional MCP server availability
  mcp-setup [--server X]    Create isolated environments for MCP servers
```

The CLI exits with status `1` and a clear message when a design cannot be made
to pass validation, rather than emitting a project that does not work.

### Example Prompts

```bash
# Voltage regulator
python main.py -p "Design a 5V to 3.3V LDO regulator circuit with green LED indicator and decoupling capacitors"

# Simple circuit (no SPICE/routing needed)
python main.py -p "Simple LED circuit with current limiting resistor" --no-spice --no-routing

# Buck converter (uses component database search)
python main.py -p "Create a 12V to 5V buck converter 3A output"
```

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

### Python environment (one-time setup)

```bash
git clone https://github.com/wachin/AI-Powered-Electronics-Design-Platform
cd AI-Powered-Electronics-Design-Platform

python3 -m venv venv
source venv/bin/activate

pip install --upgrade pip
pip install -e ".[dev]"        # runtime + test dependencies

# Confirm the tools this project depends on
kicad-cli --version
ngspice --version
```

The `/` submodules are **not** installed and are **not** dependencies.
Do not `pip install -e /...`: those repositories exist only to be read,
and installing them risks version conflicts (for example `kicad-mcp-server` and
`pcbparts-mcp` require mutually exclusive versions of `mcp`). See `AGENTS.md`.

If you want them present for reading:

```bash
git submodule update --init --recursive   # optional, reference material only
```

---


## Optional MCP Servers (Analysis & Validation)

Beyond the built-in checks, the platform can drive external
[MCP](https://modelcontextprotocol.io) servers for a **second, independent
opinion** on a generated design. This is optional — design generation does not
need it.

```bash
ai-electronics-design mcp-status                        # what is available
ai-electronics-design mcp-setup                         # set up all servers
ai-electronics-design mcp-setup --server kicad          # or just one

# Then ask for the extra validation during generation
ai-electronics-design -p "Design a 5V to 3.3V LDO regulator" --mcp-validate
```

### Why each server gets its own virtual environment

MCP servers are separate processes speaking JSON-RPC over stdio, so they do not
share a Python environment with this project. That matters because they have
**mutually incompatible dependencies**: `kicad-mcp-server` requires
`mcp[cli]>=1.27,<2`, while `pcbparts-mcp` pins `mcp==1.25.0`.

Installing both into one environment is what produces the conflict noted in this
project's history. Giving each server its own environment under `.mcp_envs/`
removes the conflict entirely — no forks, no patched pins, no version
negotiation.

### Servers

| Server | License | What it adds |
|---|---|---|
| `kicad` — [kicad-mcp-server](https://pypi.org/project/kicad-mcp-server/) | MIT | 23 tools: ERC, DRC, board info, netlist/SPICE export, Gerber/drill, STEP/3D, SVG/PDF, JLCPCB packaging, `auto_route` |
| `pcbparts` — `pcbparts-mcp` | MIT | Cross-distributor part search (JLCPCB/Mouser/DigiKey), parametric filtering, alternatives, PCB design rules, ~285 reference boards |

### The `pcbnew` detail

`kicad-mcp-server` needs KiCad's native Python bindings for board analysis,
`auto_route` and the STEP/3D exports. Those bindings ship with KiCad, not with a
virtual environment. The launcher therefore runs the server with a **system**
interpreter that has `pcbnew`, while the server's own packages stay isolated and
are exposed through `PYTHONPATH`. Using this project's interpreter instead would
silently disable those tools.

### Verified behaviour

Against a generated LDO project:

```
ERC violations: 0
DRC violations: 5  (KiCad library-table notices only — the board embeds its footprints)
```

`get_board_info` correctly reported the generated board (5 components, 5 nets).
The DRC notices appear because KiCad's *global* footprint library table is not
populated; they are an environment notice, not a defect, and the code labels them
as such.

`auto_route` is present but **still blocked**: it needs a FreeRouting jar
(`KICAD_MCP_FREEROUTING_JAR`), and every jar bundled in `external/freerouting/`
is compiled for **Java 25** while this machine has Java 21. Same blocker as the
built-in router — see [Known Limitations](#known-limitations).

---

## Daily Usage (Every Session)

**You must perform these steps every time you start a new terminal session:**

### ⚡ Quick Reference

```bash
# Activate environment (every session)
source venv/bin/activate

# Run tests (pytest config lives in pyproject.toml)
pytest -q

# Generate a design
ai-electronics-design -p "Design a 5V to 3.3V LDO regulator with an LED"

# Quick run without SPICE
ai-electronics-design -p "Simple LED circuit" --no-spice --no-routing

# Single test file, or with coverage
pytest tests/test_erc.py -v
pytest --cov=src --cov-report=term-missing

# Deactivate when done
deactivate
```

You'll see `(venv)` in your prompt while the environment is active.

> PCB auto-routing is currently blocked, so `--no-routing` is the practical
> default. See [Known Limitations](#known-limitations).

---

## Web Interface (API + Frontend)

The same pipeline is exposed as a REST API with a React frontend.

```bash
# Terminal 1 — backend on http://localhost:8000
source venv/bin/activate
uvicorn src.api.main:app --reload --port 8000

# Terminal 2 — frontend on http://localhost:5173 (proxies /api to :8000)
cd frontend
npm install
npm run dev
```

Useful endpoints:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Liveness check |
| `POST` | `/api/design` | Submit a prompt and start a design job |
| `GET` | `/api/jobs/{job_id}` | Poll job status and results |
| `GET` | `/api/jobs` | List jobs |
| `GET` | `/api/components/search` | Search the component database |
| `WS` | `/api/collaboration/ws/{room_id}/{user_id}/{user_name}` | Real-time collaboration |

> **Security note:** the API currently ships with permissive CORS
> (`allow_origins=["*"]`) and no authentication, and it is not bound by the
> permission system. Do not expose it to an untrusted network as-is. See
> `ROADMAP.md` section 22.

---

## ⚠️ Important: One-Time vs. Repeated Steps

| Step | Frequency | Commands |
|------|-----------|----------|
| **Install system packages** | **ONCE** | `sudo apt-get install ...` |
| **Create virtual environment** | **ONCE** | `python3 -m venv venv` |
| **Install Python dependencies** | **ONCE** | `pip install -e ".[dev]"` |
| **Activate virtual environment** | **EVERY SESSION** | `source venv/bin/activate` |
| **Run tests** | **EVERY SESSION** | `pytest -q` |
| **Run design pipeline** | **EVERY SESSION** | `ai-electronics-design -p "..."` |
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
| `kicad` | Primary EDA engine; provides `kicad-cli` |
| `kicad-footprints`, `kicad-symbols`, `kicad-templates` | KiCad libraries — **required**, read at runtime by the generators |
| `ngspice` | SPICE simulation CLI |
| `librepcb`, `horizon-eda` | Alternative EDA engines (optional) |
| `sch-rnd-sim` | High-level circuit simulation |
| `pcb-rnd` | Alternative PCB tool |
| `default-jre` | Java runtime for FreeRouting |
| `default-jdk` | Java development kit (for FreeRouting dev) |

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| `venv/bin/activate: No such file` | Create it: `python3 -m venv venv` (the project targets Python 3.10+; tested on 3.13) |
| `ModuleNotFoundError: No module named 'src'` | Install the package: `pip install -e ".[dev]"`, or run from the repository root |
| `ai-electronics-design: command not found` | The console script comes from `pip install -e .`; alternatively run `python main.py` |
| `kicad-cli: command not found` | `sudo apt-get install kicad` (on current Debian/Ubuntu, `kicad-cli` ships inside the `kicad` package) |
| Schematic/PCB has no pins or pads | The KiCad symbol/footprint libraries are missing. Install `kicad-symbols` and `kicad-footprints` |
| `ngspice: command not found` | `sudo apt-get install ngspice`, or pass `--no-spice` |
| `pytest: command not found` | `pip install -e ".[dev]"` in the active venv |
| Routing reports a DSN error | Expected: `kicad-cli` has no DSN export in KiCad 7+. See Known Limitations |
| `UnsupportedClassVersionError` running FreeRouting | The bundled jars need Java 25; install it or skip routing |
| Tests fail with `PermissionError` | The security sandbox is not wired into the pipeline; report the test and path involved |

---

##  Submodules (Reference Only)

The `external/` directory contains Git submodules for reference only. They are **not required** for the main platform to function:

32 submodules are configured in `.gitmodules`, for example:

```
external/
├── kicad/                  # KiCad source
├── kicad-tools/            # KiCad automation utilities
├── kicad-mcp-server/       # MCP server for KiCad
├── circuit-json/           # Circuit JSON format and tooling
├── tscircuit/              # Circuit JSON → PCB toolchain
├── skidl/                  # Netlist generation from Python
├── atopile/                # Hardware description language
├── freerouting/            # Autorouter source
├── ngspice/  pyspice/      # SPICE simulators
├── yjs/  automerge/        # CRDT libraries
├── jlcparts/               # Component catalog generator
├── librepcb/  ecad-viewer/ # Alternative EDA tools
└── ...                     # (see research/repository_catalog.md)
```


The main platform does **not** require any of them. Initialise only if you want
to study them:

```bash
git submodule update --init --recursive
```

Submodules are reference material, never dependencies — see `AGENTS.md`.

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
├── external/                        # 32 Git submodules (reference only)
│   ├── kicad/ kicad-tools/          # KiCad source + automation
│   ├── circuit-json/ tscircuit/     # Circuit JSON toolchain
│   ├── freerouting/ ngspice/        # Autorouter + simulator source
│   ├── jlcparts/                    # Component catalog generator
│   └── ...                          # see research/repository_catalog.md
└── research/
    ├── flux-ai-patent-search.md
    └── repository_catalog.md
```



---

## Legal

**License:** GNU GPL-3.0 — see [`LICENSE`](LICENSE). Third-party components,
their licenses, and the KiCad library exception that lets generated designs be
used freely are recorded in [`CREDITS.md`](CREDITS.md).

### Independent implementation

**This software is an independent open-source implementation that does not copy
or derive from Flux.ai.**

Flux.ai is a proprietary commercial product. This project:

- is **not** affiliated with, endorsed by, or connected to Flux Lab Inc.;
- does **not** use Flux.ai source code, trademarks, or proprietary assets;
- references Flux.ai only for technical analysis and educational purposes;
- implements similar functionality using only open-source tools.

See [`LEGAL_NOTICE.md`](LEGAL_NOTICE.md) and
[`LEGAL_DISCLAIMER.md`](LEGAL_DISCLAIMER.md) for details, and
[`research/flux-ai-patent-search.md`](research/flux-ai-patent-search.md) for how
to search Flux.ai patents and verify — subsystem by subsystem — that this
project is an independent implementation. That file deliberately contains no
patent numbers, because the maintainers have not run a citable patent search.

### Disclaimer

THE AUTHORS PROVIDE NO WARRANTIES, EXPRESS OR IMPLIED, INCLUDING WARRANTIES OF
MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE, OR NONINFRINGEMENT. THE
AUTHORS ARE NOT LIABLE FOR ANY CLAIM, DAMAGES, OR OTHER LIABILITY ARISING FROM
THE USE OF THIS SOFTWARE.

PORTABILITY OF THIS SOFTWARE TO YOUR SPECIFIC USE CASE IS YOUR RESPONSIBILITY.

### Contributing

If you contribute:

1. You grant a GPL-3.0 license to your contributions
2. You represent that you have the right to contribute the code
3. You accept the project's license

### Related documentation

| File | Purpose |
|---|---|
| `ROADMAP.md` | Development plan, with a verified "what is wired in vs orphaned" section |
| `docs/llm-pipeline.md` | LLM pipeline architecture, postmortem, and verification status |
| `docs/llm-model-recommendations.md` | Choosing and running a model |
| `CREDITS.md` | Third-party dependencies, licenses, and the KiCad library exception |
| `AGENTS.md` | Agent policies for external repositories |
| `LEGAL_NOTICE.md` / `LEGAL_DISCLAIMER.md` | Legal notices |
| `research/flux-ai-patent-search.md` | Patent search and independence verification |
| `research/repository_catalog.md` | Evaluated open-source projects and their licenses |
