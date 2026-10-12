# AI-Powered Electronics Design Platform

<!--
  Badges are static on purpose. A CI status badge is only added once this
  repository has actually run the "CI" workflow on GitHub, so that it reports a
  real result instead of a plausible-looking placeholder.
  Every claim below is verifiable: LICENSE, pyproject.toml, and the test suite.
-->
[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![Tests](https://img.shields.io/badge/tests-249%20passing%2C%202%20skipped-brightgreen.svg)](tests/)
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

**What works today:** the full path from prompt to an ERC-clean, **auto-routed**
KiCad project with a correct netlist, Gerbers and drill files. **Not yet:**
datasheet understanding and multi-turn clarification. See
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
6. ✅ PCB Auto-routing - FreeRouting via `pcbnew` DSN/SES; verified 0 unconnected pads
7. ✅ Bill of Materials (BOM) Generation - real catalog MPNs, descriptions and pricing
8. ✅ Gerber/Drill Manufacturing Export - verified on generated boards via `kicad-cli`
9. ✅ CLI Interface - full pipeline from prompt to KiCad project
10. ✅ Natural Language Understanding (LLM integration) - Ollama / OpenAI-compatible / Anthropic,
    with schema-constrained output, catalog-grounded part selection, pin and ERC
    validation, and an automatic repair loop (see `docs/llm-pipeline.md`)

### Known Limitations
- ⚠️ **Auto-routing needs Java 25 and a FreeRouting jar**, neither of which is a
  Python dependency:
  - FreeRouting jars are compiled to class-file version 69, so Java 21 refuses
    them. Install a newer JDK (`sudo apt install openjdk-25-jdk`); the code
    discovers it and does not require changing the system default.
  - The jar is not bundled with anything. Place it at
    `libs/freerouting/freerouting.jar` or set `KICAD_MCP_FREEROUTING_JAR`.
  Verified working: 30 tracks routed, **0 unconnected pads**, on a generated
  board. Without these, generation still succeeds and routing reports a clear
  error instead of failing silently.
- ⚠️ **The full component catalog is a separate 145 MB download.** Without it
  the platform uses a built-in catalog of 38 common parts, so part selection and
  substitution are limited to those. Install it with
  `ai-electronics-design catalog-setup` (see
  [Component Catalog](#component-catalog-180000-real-parts)).
- ⚠️ **Parametric search covers 55,535 of the 179,894 parts** — those whose
  attributes state a number. The rest are reachable by text search only. A
  substitute is found by comparing parsed values, so a part described only by a
  part number cannot be substituted automatically.
- ⚠️ **The catalog's JLCPCB "Basic" library flag is effectively empty** (1 part
  of 179,894). Ranking uses the Preferred flag (972 parts) instead. See
  [Where it comes from](#where-it-comes-from).
- ⚠️ Three implemented subsystems are **not wired into the pipeline**: the
  permission system, the process sandbox, and the free-form MCP agent. They have
  tests but nothing calls them. See [`ROADMAP.md` §22](ROADMAP.md).
- ⚠️ The requirement parser fills defaults for unspecified values instead of
  asking the user.
- ⚠️ A working KiCad installation is required: symbol and footprint libraries
  are read at runtime (see `CREDITS.md` for licensing).

### Planned / In Progress

- 🔄 Wiring the orphaned modules into the pipeline (placement first)
- 🔄 Datasheet PDF parsing, to check pinouts automatically instead of by hand
- 🔄 Multi-turn clarification of missing requirements (the parser currently fills defaults)
- 🔄 Datasheet understanding / RAG (section 8 of the ROADMAP)
- 🔄 Enclosure generation and 3D component models

### Status of the larger pieces

| Piece | State |
|---|---|
| CLI + Python API | ✅ Works |
| Component search (numeric, 179,894 parts) | ✅ Works |
| Substitute lookup with per-part evidence | ✅ Works |
| Natural language → specification | ✅ Works (local or cloud LLM) |
| Specification → validated Circuit IR | ✅ Works |
| Schematic + PCB + Gerbers | ✅ Works and is KiCad-verified |
| SPICE simulation | ✅ Works |
| Web frontend + collaboration | ✅ Implemented (builds, WebSocket server present) |
| PCB autorouting | ✅ Works (needs Java 25 + the FreeRouting jar) |
| Smart component placement | ✅ Wired in — drives PCB layout and board outline |
| Permissions / sandbox / MCP agent | ⚠️ Implemented but not wired in |
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

### 🔧 Used as external programs (not linked)

- **KiCad** (`kicad-cli`) — netlist export, ERC, DRC, Gerber/drill export.
  Note: **no DSN export or SES import** — those `kicad-cli` subcommands do not
  exist in KiCad 7+ (the `pcbnew` Python API does provide them).
- **KiCad symbol + footprint libraries** — read at runtime for pin geometry and
  pad definitions. CC-BY-SA-4.0 with a design exception; see `CREDITS.md`.
- **ngspice** — SPICE simulation (batch mode).
- **FreeRouting** — PCB autorouter (Java JAR). Not currently runnable; see Known Limitations.
- **yaqwsx/jlcparts** — offline component catalog (MIT, SQLite).

### 📦 Research references (not part of this repository)

The project was built by studying open-source EDA software. Those repositories
are **not** submodules and are **not** downloaded when you clone this project.
They are listed in [`research/reference-repositories.md`](research/reference-repositories.md)
with their licences and what each was used for.

Clone only what you want to read:

```bash
git clone --depth 1 https://github.com/yaqwsx/jlcparts /tmp/refs/jlcparts
```

`research/repository_catalog.md` holds the full evaluation.

---

## Technical Stack (Current)

| Layer | Technology | License | Status |
|-------|------------|---------|--------|
| **Circuit IR** | Custom (Python) | GPL-3.0 | ✅ Implemented |
| **ERC** | Custom (Python) | GPL-3.0 | ✅ Implemented |
| **Component DB** | JLCParts (yaqwsx/jlcparts) | MIT | ✅ Implemented |
| **EDA Engine** | KiCad 8.x / 9.x (`kicad-cli`) | GPL-3.0 | ✅ Integrated |
| **Schematic/PCB Gen** | Custom S-expression compiler | GPL-3.0 | ✅ Implemented |
| **Routing** | FreeRouting | GPL-3.0 | ✅ Working (needs Java 25 + the jar in `libs/freerouting/`) |
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
  catalog-status            Show the component catalog in use
  catalog-setup [--dest P]  Download the full component catalog (~145 MB)
  parts-search "10k 0603"   Search it by value, package, tolerance, rating
  parts-substitute C12345   Find replacements, with what was verified
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
| Java 25 | Auto-routing | `sudo apt install openjdk-25-jdk` (Debian trixie+, Ubuntu jammy+). Installs alongside Java 21 |

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

# Required
sudo apt-get install -y \
    python3 python3-venv python3-dev \
    kicad \
    kicad-footprints kicad-symbols kicad-templates \
    openjdk-25-jdk

# Optional: SPICE simulation
sudo apt-get install -y ngspice

# Optional: virtual display, needed only by the MCP server's auto_route tool
sudo apt-get install -y xvfb

# Optional: alternative EDA tools, for comparison
sudo apt-get install -y librepcb horizon-eda sch-rnd-sim pcb-rnd
```

> On Debian and Ubuntu, `kicad-cli` ships inside the `kicad` package; a separate
> `kicad-cli` package is not needed on current releases.

#### Why Java 25 (`openjdk-25-jdk`)

Auto-routing needs it. The FreeRouting jars are compiled to Java class-file
version 69, so an older runtime refuses to start them with
`UnsupportedClassVersionError`. Java 21 is not enough.

`openjdk-25-jdk` installs **alongside** any existing JDK; it does not remove
Java 21. Note that installing it may make `java` point at 25 by default. This
project does **not** rely on the default: it locates a Java 25+ runtime itself
(`/usr/lib/jvm/java-*` and `JAVA_HOME`), so either default works.

To check or change which JDK is the system default:

```bash
update-alternatives --list java          # what is installed
sudo update-alternatives --config java   # choose the default interactively
```

#### Supported distributions

* **Debian** — `openjdk-25-jdk` is available from **trixie (13)** onward.
* **Ubuntu** and derivatives (Kubuntu, Xubuntu, Linux Mint, Pop!_OS, elementary,
  Zorin, …) — `openjdk-25-jdk` is available from **jammy (22.04)** onward.

The platform is developed and verified on Debian 13 (trixie) with KiCad 9.0.2,
ngspice 44.2 and OpenJDK 25.0.4. Package names above are the Debian/Ubuntu ones;
on other distributions install the equivalents (for example
`java-25-openjdk` on Fedora).

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

Nothing is installed from a research checkout: installable code is declared in `pyproject.toml` instead of being
cloned here, and why the MCP servers get their own isolated environments —
`kicad-mcp-server` and `pcbparts-mcp` require mutually exclusive versions of
`mcp`. See `AGENTS.md`.

If you want any of them for reading, clone it on demand — see
[`research/reference-repositories.md`](research/reference-repositories.md).
Nothing needs to be present for the build, the tests or the runtime.

---


## Component Catalog (180,000+ real parts)

The platform selects parts from an offline catalog of **real, in-stock,
purchasable components**. Install it once:

```bash
ai-electronics-design catalog-setup      # ~145 MB download
ai-electronics-design catalog-status     # confirm it is in use
```

```text
Component catalog:
  source : JLCPCB/LCSC offline catalog (179,894 parts)
  parts  : 179,894
  status : full offline catalog in use
```

### What it gives you

| Data | Why it matters |
|---|---|
| **Real LCSC part numbers** | Every part in the BOM can actually be ordered |
| **Stock levels** | You will not design around a part with zero stock |
| **Tiered pricing** | Real cost estimates for the BOM |
| **Package, manufacturer, datasheet** | Enough to verify a part before buying |
| **Parametric attributes** (JSON) | Resistance, tolerance, voltage, power — parsed into numbers, and the basis for finding a substitute |

Coverage of in-stock parts, by the catalog's own categories:

| Category | Parts | Category | Parts |
|---|---:|---|---:|
| *(uncategorized)* | 67,230 | Resistors | 5,146 |
| Connectors | 34,220 | Crystals / oscillators | 4,234 |
| Transistors / thyristors | 12,507 | Power management (PMIC) | 4,138 |
| Inductors, coils, chokes | 9,017 | Switches | 4,028 |
| Capacitors | 7,227 | Power modules | 2,528 |
| Diodes | 6,535 | Optoelectronics | 1,943 |
| Circuit protection | 6,443 | Logic | 1,392 |

**55,535 of those parts carry a numeric value** that parametric search can match.
The remaining rows are identified only by a description or a part number and are
reachable by text search.

The 67,230 uncategorized rows are not a gap in the download: the upstream data
simply leaves the category empty for them. Most still carry an unambiguous
`Resistance` or `Capacitance` attribute, or name their type in the description,
and the platform classifies them from that. After classification 16,171 parts
remain genuinely unclassified, and the platform says so rather than guessing.

The catalog's categories are also broader than the platform's. "Power Management
(PMIC)" contains linear regulators, switching converters, voltage references,
supervisors, chargers and load switches; "Diodes" contains zeners, Schottkys and
LEDs. Those are split by reading each row, and the searchable category list
reflects the result — 44 categories, including `zener`, `supervisor`,
`voltage_reference` and `power_switch`. The split matters for correctness: giving
a TL431 voltage reference an LDO symbol would assert IN/OUT/GND pins it does not
have.

### Searching the catalog

Search matches **values**, not substrings:

```bash
ai-electronics-design parts-search "10k 1% 0603"
```

```text
Query      : '10k 1% 0603'
Understood : 10k, ±1%, package 0603
Note       : Matched numerically: 10k, ±1%, package 0603
Source     : JLCPCB/LCSC offline catalog (179,894 parts)

    LCSC       MPN                        Package        Specification                      Stock      Unit
  1. C49330116  AST0310KF                  0603           10kΩ 100mW ±1%                   388,789    0.0042
  2. C49652949  GR0603F10KT5G00            0603           10kΩ 100mW ±1%                    29,904    0.0009
```

This matters because the obvious implementation is wrong. A `LIKE '%10k%'` search
also matches `110kΩ` and `910kΩ` — parts that look right in a list and are wrong
on the board. Here:

| Query | Understood as |
|---|---|
| `10k 0603` | 10 kΩ, package 0603 |
| `4R7` | 4.7 Ω (the R is a decimal point, not a unit) |
| `4k7` | 4.7 kΩ |
| `100nF 50V 0805` | 100 nF, **rated at least** 50 V, package 0805 |
| `ldo 3.3v` | LDO with a 3.3 V **output** — a 5 V LDO is not a match |
| `100nF 50V` | prefers the 50 V part over an unnecessary 500 V one |
| `esp32`, `1n4148` | text search: a part number is not the number 32 |

The interpretation is printed above the results, in the CLI and in the GUI, so
you can see what the search understood rather than guessing from the output.

### Finding a substitute

When a part is out of stock, the question is what to buy instead. The answer is
only useful if it says what was compared:

```bash
ai-electronics-design parts-substitute C22369937
```

```text
Replacing: C22369937 RCA0310KJLF
  category : resistor
  package  : 0603
  value    : 10kΩ 100mW ±5%

1. C49330116 AST0310KF (0603) — all checks passed
   + same resistance (10kΩ 100mW ±5%)
   + same package (0603)
   + tolerance ±1% is at least as tight as ±5%
   + power rating at least as high (100mW)
   + in stock (388,789)
```

Candidates are matched on **value and package**, which are identities: a 10 kΩ part
is not a substitute for a 12 kΩ one, and a different package will not fit the
footprint. Everything else — tolerance, voltage rating, power rating, stock — is
**reported rather than used to reject**, so a part whose tolerance is looser
appears with `! looser tolerance: ±5% vs ±1%` instead of being hidden. A hidden
part cannot be chosen; a flagged one can.

A part with no numeric value (identified only by a part number) cannot be
compared this way, and the command says so rather than guessing.

### Where it comes from

The catalog is built from the [yaqwsx/jlcparts](https://github.com/yaqwsx/jlcparts)
dataset (MIT). That upstream dataset is a ~10 GB multi-volume archive most zip
libraries cannot open, so this project fetches
[CDFER/jlcpcb-parts-database](https://github.com/CDFER/jlcpcb-parts-database),
which republishes the same data as a single SQLite file, rebuilt daily by GitHub
Actions and filtered to parts with stock.

Two caveats about the data, verified against this catalog copy rather than assumed:

* **The JLCPCB "Basic" library flag is effectively absent.** The `basic` column is
  set on 1 of 179,894 rows. The `preferred` column is set on 972. Ranking therefore
  uses Preferred, and `is_basic` is false for almost everything. Do not read the
  `library_type` column (`base` / `expand`) as the basic/preferred flag — an earlier
  version of this code did, and it made every part look non-preferred.
* **Attributes are not uniform.** Which keys exist depends on the category
  (`Resistance` for resistors, `Capacitance` and `Voltage Rating` for capacitors,
  `Output Voltage` for regulators). The parser accepts every spelling it knows and
  records nothing for what it cannot read, so an unstated tolerance is "unknown",
  never zero.

### Configuration

The catalog is looked up in this order:

1. `$JLC_PARTS_CATALOG` — an explicit file path
2. `$XDG_CACHE_HOME/kicad-tools/jlcparts.sqlite3` (default `~/.cache/...`)
3. `<repository>/jlcparts.sqlite3`
4. `/tmp/jlcparts.sqlite3`

To install it elsewhere:

```bash
ai-electronics-design catalog-setup --dest /path/to/jlcparts.sqlite3
export JLC_PARTS_CATALOG=/path/to/jlcparts.sqlite3
```

The download goes to a temporary file and is verified (it must open and contain
components) before replacing anything, so an interrupted transfer cannot leave a
half-written catalog silently degrading part selection.

### It is optional

Design generation works without it, using a built-in catalog of 38 common parts.
You lose real stock, real pricing and reliable substitution — the design may
still be valid, but its BOM is not guaranteed to be orderable.

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

### Installation

Nothing needs to be cloned. Both servers are declared in `pyproject.toml` and
installed into their own isolated environments by one command:

```bash
ai-electronics-design mcp-setup            # creates .mcp_envs/<name>/ for each
ai-electronics-design mcp-status           # confirm they are ready
```

That is the complete installation procedure. It installs:

| Server | Source | Why not a clone |
|---|---|---|
| `kicad-mcp-server` | PyPI (`kicad-mcp-server>=3.5.0`) | Published package |
| `pcbparts-mcp` | git URL (`git+https://github.com/Averyy/pcbparts-mcp.git`) | Not on PyPI, but pip installs directly from the URL |

Both are **optional**. Design generation, ERC, DRC, Gerbers and auto-routing all
work without them.

### Why this is optional (and what you lose without it)

The platform does not use MCP servers to *build* anything. They are a second,
independent opinion on a design that has already been built. That is why they are
optional:

| Task | Built in (no MCP needed) | What MCP adds |
|---|---|---|
| Understand the request | LLM pipeline | — |
| Choose real parts | Component database | Cross-distributor search, alternatives |
| Build the circuit | Circuit IR builder | — |
| Electrical rules | ERC, 6 rules | Same check via a different implementation |
| Design rules | `kicad-cli pcb drc` | DRC through KiCad's Python API |
| Schematic and PCB | Deterministic generators | Board statistics, netlist/SPICE export |
| Gerbers and drill files | `kicad-cli` | `export_jlcpcb` packaging |
| Auto-routing | `src/routing/freerouting.py` | `auto_route` inside the server |
| SPICE | ngspice | — |
| 3D output | glTF exporter | STEP export, 3D renders |

So a full design — schematic, PCB, ERC-clean, auto-routed, Gerbers, BOM, 3D — is
produced with no MCP server installed. Verified by running the pipeline with the
server environments renamed away.

What you gain by installing them:

* **An independent check.** `--mcp-validate` asks the KiCad MCP server to run ERC
  and DRC. It shares no code with our own checks, so agreement is meaningful and
  disagreement is a signal worth investigating.
* **Capabilities we do not implement**: part alternatives across JLCPCB/Mouser/
  DigiKey, curated PCB design rules, reference-board schematics, STEP/3D renders
  and JLCPCB packaging.

If they are not installed, they fail safely:

```text
🔎 Step 8: Independent validation via MCP server...
   ⚠️  MCP validation skipped: MCP server 'kicad' is not set up.
       Run: ai-electronics-design mcp-setup
```

The design is still generated and delivered. A missing MCP server is a skipped
extra check, never a failed build.

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
| `pcbparts` — [pcbparts-mcp](https://github.com/Averyy/pcbparts-mcp) | MIT | Cross-distributor part search (JLCPCB/Mouser/DigiKey), parametric filtering, alternatives, PCB design rules, ~285 reference boards |

Both are declared as dependencies in `pyproject.toml` (PyPI for the first, git URL
for the second), so **no repository needs to be cloned into the source tree**.

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

`auto_route` additionally needs `xvfb-run` (from the `xvfb` package) because the
MCP tool launches FreeRouting in a virtual display:

```bash
sudo apt install -y xvfb
```

The project's **own** router (`src/routing/freerouting.py`) does not need `xvfb`,
so `--no-routing` can be omitted even without it.

---

## Daily Usage (Every Session)

**You must perform these steps every time you start a new terminal session:**

### ⚡ Quick Reference

```bash
# Activate environment (every session)
source venv/bin/activate

# Run tests (pytest config lives in pyproject.toml)
pytest -q

# Run them again with the full catalog installed. Some behaviour differs when a
# real catalog is present — part substitution returns catalog parts instead of
# the curated ones, and the category list is derived from the catalog — so this
# is a genuinely different run, not a slower one. CI does it weekly.
ai-electronics-design catalog-setup
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

> Auto-routing needs Java 25 and the FreeRouting jar (see
> [System Dependencies](#system-dependencies-deb-packages)). Use `--no-routing`
> if you have not set those up yet.

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
| `.git` directory is several GB | Orphaned submodule caches under `.git/modules/`, left over from when reference repositories were submodules | `rm -rf .git/modules` — see below |
| Tests fail with `PermissionError` | The security sandbox is not wired into the pipeline; report the test and path involved |

---

## Installation, in one place

There are only **two** things to install, and neither is a clone:

```bash
# 1. The platform and its Python dependencies
pip install -e ".[dev]"

# 2. Recommended: the component catalog (~145 MB, ~180,000 real parts)
ai-electronics-design catalog-setup

# 3. Optional: the MCP servers, in their own isolated environments
ai-electronics-design mcp-setup

# Verify
pytest -q                                # tests
ai-electronics-design catalog-status     # component catalog
ai-electronics-design mcp-status         # optional servers
```

Plus two system packages, which are not Python and cannot come from pip:

```bash
sudo apt install kicad ngspice         # ngspice is optional (simulation)
```

For auto-routing only: a Java 25 runtime (`sudo apt install openjdk-25-jdk`) and
the FreeRouting jar in `libs/freerouting/` — see `libs/freerouting/README.md`.

### Everything else is a reference you never install

The `external/` directory that used to hold 32 Git submodules **no longer
exists**. Cloning this project downloads only this project.

The five repositories below appear in the research notes because their approach
was studied. **Do not install them**: the code never imports them, and the table
says what this project uses instead.

| Repository | Install? | What replaced it |
|---|---|---|
| [kicad-to-circuit-json](https://github.com/tscircuit/kicad-to-circuit-json) | **No** | KiCad parsing is done here: `src/generators/kicad_symbols.py`, `kicad_footprints.py` |
| [circuit-json-to-kicad](https://github.com/tscircuit/circuit-json-to-kicad) | **No** | KiCad is emitted directly: `src/generators/kicad_generator.py` |
| [tscircuit-core](https://github.com/tscircuit/tscircuit) | **No** | This project has its own Circuit IR (`src/core/circuit_ir.py`) |
| [automerge](https://github.com/automerge/automerge) | **No** | Collaboration uses Yjs instead |
| [skidl](https://github.com/devbisme/skidl) | **No** | Own ERC and Circuit IR (`src/core/erc.py`) |

To read any of them, clone outside the project tree:

```bash
git clone --depth 1 https://github.com/devbisme/skidl /tmp/refs/skidl
```

Full list with licences:
[`research/reference-repositories.md`](research/reference-repositories.md).

### Verified: a clean environment needs nothing else

A fresh virtual environment with only the declared dependencies passes the whole
suite (234 tests) and produces a fully routed design. No research repository, and
no undeclared package, is required.

---



The project's research notes list many repositories that were **read**, not
adopted. None of the following should be installed — the table says what
replaced each one:

| Repository | Install it? | Why |
|---|---|---|
| [kicad-to-circuit-json](https://github.com/tscircuit/kicad-to-circuit-json) | **No** | Studied for KiCad parsing; this project parses KiCad itself (`src/generators/kicad_symbols.py`, `kicad_footprints.py`) |
| [circuit-json-to-kicad](https://github.com/tscircuit/circuit-json-to-kicad) | **No** | Studied for conversion approach; this project emits KiCad S-expressions directly (`src/generators/kicad_generator.py`) |
| [tscircuit-core](https://github.com/tscircuit/tscircuit) | **No** | React-based schematic authoring; not used. This project has its own Circuit IR |
| [automerge](https://github.com/automerge/automerge) | **No** | Alternative CRDT, not adopted. Collaboration uses Yjs |
| [skidl](https://github.com/devbisme/skidl) | **No** | Studied for netlist/ERC concepts; this project has its own ERC (`src/core/erc.py`) and Circuit IR |

Installing these would add dependencies the code never imports and can introduce
version conflicts. To read any of them, clone outside the project:

```bash
git clone --depth 1 https://github.com/devbisme/skidl /tmp/refs/skidl
```

The full list with licences is in
[`research/reference-repositories.md`](research/reference-repositories.md).

---

## Verify Before You Buy Parts

A generated design is only useful if it works. This section is the checklist to
run **before ordering components**, ordered from "always run this" to "worth
doing for anything you care about".

### The 60-second check

```bash
ai-electronics-design -p "Design a 5V to 3.3V LDO regulator with an LED" \
    -o ./my_design -n my_ldo
```

Look at three things in the output:

```
✅ PASSED - Errors: 0, Warnings: 0          ← electrical rules
⚡ SPICE Simulation:
  DC operating point:
    vu1_in              5.000 V             ← does the input rail match your supply?
    vu1_out             3.300 V             ← does the output match what you need?
📊 Bill of Materials (BOM):                 ← real, purchasable part numbers
```

### Full checklist

| # | Check | Command | Proves |
|---|---|---|---|
| 1 | Electrical rules | automatic | No unconnected power pins, no LED without a resistor, no single-pin nets, decoupling present |
| 2 | Netlist is real | `kicad-cli sch export netlist -o /tmp/n.net ./my_design/*.kicad_sch` | KiCad extracts the same connectivity we intended |
| 3 | Design rules | `kicad-cli pcb drc -o /tmp/drc.rpt ./my_design/*.kicad_pcb` | Pads, clearances and the board outline are valid |
| 4 | SPICE operating point | automatic (`--no-spice` to skip) | Node voltages and passive-path currents |
| 5 | Independent ERC/DRC | `--mcp-validate` (needs `mcp-setup`) | A second implementation agrees with ours |
| 6 | Manufacturing files | `kicad-cli pcb export gerbers` / `drill` | The board can actually be fabricated |
| 7 | Visual check | open the `.kicad_sch` / `.kicad_pcb` in KiCad | Nothing looks wrong to your eyes — still the best filter |

Read the numbers at step 4 against your requirements: if you need 3.3 V and it
says 3.3 V, that rail is consistent. If the design has an LED, check its current
sits near the datasheet value (typically 2–20 mA).

### What the SPICE check does and does not prove

This matters, because it is easy to over-trust a green tick:

**It does prove:**

* the netlist is complete and solvable — every net has at least two connections;
* **currents through passive paths are genuinely computed** by ngspice from the
  component values (for example an LED current of 6.34 mA through a 330 Ω
  resistor, consistent with the diode model);
* the circuit is internally consistent.

**It does not prove:**

* **that a regulator actually regulates.** Active parts are modelled as *ideal
  sources*: an `AMS1117-3.3` becomes a fixed 3.3 V source, so "5 V in, 3.3 V out"
  is a statement about the netlist, not a simulated result. Dropout, efficiency,
  thermal behaviour, ripple and stability are **not** simulated.
* that the chosen part meets its datasheet specifications;
* that the board is manufacturable and assemblable — for that, use steps 3 and 6.

Treat the operating point as a **connectivity and sanity check**, not as a
guarantee of performance. For real confidence in an active circuit, simulate the
vendor SPICE model of the chosen part yourself.

### Verify a single subsystem

```bash
# Electrical rules only, on the built-in rule set
pytest tests/test_erc.py -v

# SPICE netlist compilation and ngspice execution
pytest tests/test_ngspice.py -v

# The full KiCad acceptance gates (need kicad-cli installed)
pytest tests/test_kicad_netlist.py tests/test_kicad_pcb.py -v

# Everything, treating a missing kicad-cli as a failure
DSH_REQUIRE_KICAD=1 pytest -q
```

### If something fails

| Symptom | What it means | What to do |
|---|---|---|
| ERC errors | The design is electrically incomplete | Re-run; the repair loop retries automatically. Use `--strict` to see the model's errors instead of a fallback |
| `ngspice not found` | Simulation unavailable | `sudo apt install ngspice`, or pass `--no-spice` |
| "SPICE ran but produced no operating point" | The netlist has no DC source | Check the design has a supply |
| DRC reports missing footprint libraries | KiCad's *global* library table is not populated | Harmless: the board embeds its footprints. Configure KiCad libraries to silence it |
| DRC reports clearance or short errors | A real board problem | Fix before ordering |

---

### Why `.git` can be huge (and how to fix it)

If `du -sh .git` reports gigabytes while the working tree is a couple of
megabytes, the history is almost never the cause. Check where the space is:

```bash
du -sh .git/* | sort -rh | head
git count-objects -vH          # the real history size
```

The usual culprit is `.git/modules/`: Git keeps a full clone of every submodule
inside it. This project used to have 32 reference repositories as submodules, so
those caches reached **14 GB** even after the submodules were removed — the
working tree was already gone, but the caches were not.

They are safe to delete once nothing references them:

```bash
# Confirm there is nothing to lose
test -f .gitmodules && echo "submodules still configured" || echo "none configured"
git ls-files -s | grep '^160000'        # should print nothing

# Free the space
rm -rf .git/modules
for s in $(git config --get-regexp '^submodule\.' | awk '{print $1}' \
           | sed 's/\.[^.]*$//' | sort -u); do
    git config --remove-section "$s"
done
```

In this repository that took `.git` from **14 GB to 3.8 MB** while keeping all 66
commits. Verify afterwards with `git fsck`.

**A fresh repository is not needed** for this: the history itself was only
~120 KB, so recreating the repo would have discarded the commit history for no
benefit.

---

## Where everything lives

A developer who clones this repository downloads **only this repository**. There
are no submodules, so nothing extra is fetched.

| What | Where it goes | How it arrives | Required? |
|---|---|---|---|
| Python dependencies | `venv/` | `pip install -e ".[dev]"` — declared in `pyproject.toml` | Yes |
| MCP servers | `.mcp_envs/<name>/` (isolated) | `ai-electronics-design mcp-setup` — declared in `pyproject.toml` | Optional |
| FreeRouting jar | `libs/freerouting/` | you download it (see the README there) | Only for auto-routing |
| KiCad and its libraries | system | `apt install kicad` | Yes |
| ngspice | system | `apt install ngspice` | Optional (simulation) |
| Research references | outside the repo, e.g. `/tmp/refs/` | `git clone --depth 1 <url>` | Never |

### Installing vs. browsing

These are kept deliberately apart, because mixing them is what forces every
developer to download gigabytes they will never open:

* **Installable code is declared as a dependency** and installed by a tool. This
  includes the MCP servers: `kicad-mcp-server` from PyPI, and `pcbparts-mcp`
  from its git URL.
* **Code you only want to read is never cloned into this repository.** It is
  listed in `research/reference-repositories.md` with a clone command. Reading
  someone's parser does not make it a dependency.

`tests/test_mcp_integration.py` enforces this: no installable component may point
at a local checkout.

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
├── scripts/tools_check_netlist.py           # Verifies schematic -> real KiCad netlist
├── scripts/tools_e2e_check.py               # End-to-end check against a real LLM
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
├── libs/
│   └── freerouting/                 # Downloaded jar only (gitignored)
└── research/
    ├── flux-ai-patent-search.md
    ├── reference-repositories.md    # Optional references + clone commands
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
