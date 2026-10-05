# AI-Powered Electronics Design Platform

---

## Project Purpose

This project builds an AI-powered electronics design platform that transforms natural language circuit descriptions into manufacturing-ready hardware projects.

**Current Capabilities (Implemented):**
1. ✅ Circuit Intermediate Representation (Circuit IR) - canonical data model
2. ✅ Deterministic Electrical Rule Checking (ERC) - 6 validation rules
3. ✅ JLCPCB/LCSC Component Database - 600k+ parts (yaqwsx/jlcparts offline catalog)
4. ✅ KiCad 8 Schematic & PCB Generation - via S-expression compiler
5. ✅ ngspice SPICE Simulation - DC op, transient, DC sweep
6. ✅ FreeRouting PCB Auto-routing - DSN export → routing → SES import
7. ✅ Bill of Materials (BOM) Generation - with pricing from JLCPCB
8. ✅ Gerber/Drill Manufacturing Export - via kicad-cli
9. ✅ CLI Interface - full pipeline from prompt to KiCad project

**Planned / In Progress:**
- 🔄 Natural Language Understanding (LLM integration)
- 🔄 Web Frontend (React/TypeScript + Yjs collaboration)
- 🔄 Datasheet Extraction (RAG pipeline)
- 🔄 Smart PCB Placement (thermal, signal integrity)
- 🔄 AI Agent Tool Architecture (MCP)

**It is built exclusively with open-source technologies.**

---

## Architecture Overview

```
Natural Language Prompt
         │
         ▼
┌──────────────────────────────────────┐
│  AIDesignOrchestrator (pipeline)    │
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
│  KiCad Generator (S-expressions)    │
│  .kicad_sch  .kicad_pcb  .kicad_pro │
└──────────────────────────────────────┘
    │
    ├─▶ ngspice (SPICE simulation)
    ├─▶ FreeRouting (PCB auto-routing)
    └─▶ kicad-cli (ERC/DRC/Gerber/DSN)
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

This project is licensed under **GNU GPL-3.0**.

**Important:** The GPL-3.0 license applies to the code you write. External GPLv3 tools (KiCad, FreeRouting) are used via subprocess calls, which helps maintain license separation.

---

## Getting Started

### Prerequisites

1. **Python 3.10+**
2. **KiCad 8+** (for `kicad-cli`)
3. **ngspice** (for SPICE simulation)
4. **Java 11+** (for FreeRouting JAR)
5. **Node.js 18+** (for future frontend - not yet required)

### Installation

```bash
# Clone the repository
git clone https://github.com/wachin/AI-Powered-Electronics-Design-Platform
cd AI-Powered-Electronics-Design-Platform

# Initialize submodules (reference implementations)
git submodule update --init --recursive

# Install Python dependencies
pip install -r requirements.txt

# Verify KiCad CLI
kicad-cli --version

# Verify ngspice
ngspice --version

# Optional: Download JLCParts catalog (600k+ parts, ~400MB)
# python -c "from src.components.database import ComponentDatabase; ComponentDatabase().download_catalog()"
```

### Quick Start

```bash
# Run full pipeline (ERC + SPICE + KiCad + FreeRouting)
python main.py -p "Design a 5V to 3.3V LDO regulator with LED indicator"

# Run without SPICE simulation (if ngspice not installed)
python main.py -p "Design a 5V to 3.3V LDO regulator" --no-spice

# Run without PCB auto-routing (if FreeRouting not installed)
python main.py -p "Simple LED circuit" --no-routing

# Run minimal (ERC + KiCad only)
python main.py -p "Simple LED circuit" --no-spice --no-routing
```

**Output** (in `./output_design/` or custom `-o` dir):
- `ldo_regulator.kicad_sch` - KiCad schematic
- `ldo_regulator.kicad_pcb` - KiCad PCB layout
- `ldo_regulator.kicad_pro` - KiCad project file
- `design_summary.json` - Complete design report

### Run Tests

```bash
PYTHONPATH=. pytest tests/ -v
# 15 tests passing: CircuitIR, ERC, KiCad Gen, SPICE, FreeRouting, Component DB, Orchestrator
```

---

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
├── main.py                          # CLI entry point
├── requirements.txt                 # Python dependencies
├── ROADMAP.md                       # Development roadmap with checkboxes
├── AGENTS.md                        # Agent policies
├── LEGAL_NOTICE.md                  # Legal notice
├── LEGAL_DISCLAIMER.md              # Legal disclaimer
├── src/
│   ├── core/
│   │   ├── circuit_ir.py           # Circuit Intermediate Representation
│   │   └── erc.py                  # Electrical Rule Checker
│   ├── components/
│   │   ├── database.py             # Unified component database
│   │   └── jlcparts.py             # JLCPCB/LCSC catalog wrapper
│   ├── generators/
│   │   └── kicad_generator.py      # KiCad S-expression compiler
│   ├── simulation/
│   │   └── ngspice.py              # SPICE simulation integration
│   ├── routing/
│   │   └── freerouting.py          # FreeRouting autorouter wrapper
│   ├── agents/
│   │   └── orchestrator.py         # AI design pipeline
│   └── api/
│       └── main.py                 # FastAPI REST API backend
├── tests/
│   ├── test_circuit_ir.py
│   ├── test_component_db.py
│   ├── test_erc.py
│   ├── test_kicad_generator.py
│   ├── test_ngspice.py
│   ├── test_freerouting.py
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
| `AGENTS.md` | Agent policies for external repositories |
| `LEGAL_NOTICE.md` | Legal notice |
| `LEGAL_DISCLAIMER.md` | Legal disclaimer |
| `research/flux-ai-patent-search.md` | Patent search guide |

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
- `research/flux-ai-patent-search.md` - How to search Flux.ai patents (provided for due diligence reference only; this project does **not** use, implement, or derive from any Flux.ai patents)