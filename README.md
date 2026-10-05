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

### System Dependencies (.deb packages)

Install required system packages **once**:

```bash
# Update package list
sudo apt-get update

# Install required system packages
sudo apt-get install -y \
    python3.11 python3.11-venv python3.11-dev \
    kicad kicad-cli \
    ngspice ngspice-dev ngspice-doc \
    librepcb horizon-eda \
    kicad-footprints kicad-symbols kicad-templates \
    default-jre  # For FreeRouting JAR

# Optional packages (useful for development)
sudo apt-get install -y \
    sch-rnd-sim \
    pcb-rnd \
    default-jdk  # For FreeRouting development
```

### Python Virtual Environment (One-Time Setup)

Create and configure the virtual environment **once**:

```bash
# Clone the repository
git clone https://github.com/wachin/AI-Powered-Electronics-Design-Platform
cd AI-Powered-Electronics-Design-Platform

# Initialize submodules (reference implementations)
git submodule update --init --recursive

# Create virtual environment (ONLY ONCE)
python3.11 -m venv venv

# Activate virtual environment
source venv/bin/activate

# Upgrade pip and install dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Install external submodule tools (optional, for development)
pip install -e external/kicad-mcp-server
pip install -e external/kicad-tools
pip install -e external/pcbparts-mcp

# Verify installations
kicad-cli --version
ngspice --version
```

---

## Daily Usage (Every Session)

**You must perform these steps every time you start a new terminal session:**

### 1. Activate Virtual Environment

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
| **Create virtual environment** | **ONCE** | `python3.11 -m venv venv` |
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
| `python3.11-venv` | Virtual environment support |
| `kicad`, `kicad-cli` | Primary EDA engine |
| `librepcb`, `horizon-eda` | Alternative EDA engines |
| `ngspice`, `ngspice-dev`, `ngspice-doc` | SPICE simulation CLI + docs |
| `librepcb`, `horizon-eda` | Alternative EDA engines |
| `kicad-footprints`, `kicad-symbols`, `kicad-templates` | KiCad libraries |
| `sch-rnd-sim` | High-level circuit simulation |
| `pcb-rnd` | Alternative PCB tool |
| `default-jre` | Java runtime for FreeRouting |
| `default-jdk` | Java development kit (for FreeRouting dev) |

---

## Project Structure

```
AI-Powered-Electronics-Design-Platform/
├── main.py                          # CLI entry point
├── requirements.txt                 # Python dependencies
├── ROADMAP.md                       # Development roadmap
├── AGENTS.md                        # Agent policies
├── venv/                            # Virtual environment (created once)
├── src/
│   ├── core/                        # Circuit IR, ERC
│   ├── components/                  # Component database, JLCParts
│   ├── generators/                  # KiCad S-expression generator
│   ├── simulation/                  # ngspice integration
│   ├── routing/                     # FreeRouting wrapper
│   ├── agents/                      # AI design orchestrator
│   └── api/                         # FastAPI backend
├── tests/                           # 63 tests (61 passing, 2 skipped)
├── frontend/                        # React/TypeScript frontend
└── external/                        # Git submodules (reference only)
```

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
# All tests (63 tests: 61 passing, 2 skipped)
PYTHONPATH=. pytest tests/ -v

# Quick sanity check
PYTHONPATH=. pytest tests/test_circuit_ir.py tests/test_erc.py -v

# With coverage
PYTHONPATH=. pytest tests/ --cov=src --cov-report=term-missing
```

---

## Legal Notice

⚠️ **IMPORTANT:** This software is an independent open-source implementation that does NOT copy or derive from Flux.ai. See `LEGAL_NOTICE.md` and `LEGAL_DISCLAIMER.md` for details. Patent search required before commercial distribution (`research/flux-ai-patent-search.md`).

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