# AI-Powered Electronics Design Platform

**⚠️ IMPORTANT: READ THIS ENTIRE FILE BEFORE USING THIS SOFTWARE**

---

## Legal Notice

**THIS SOFTWARE IS AN INDEPENDENT OPEN-SOURCE IMPLEMENTATION THAT DOES NOT COPY OR DERIVE FROM FLUX.AI**.

Flux.ai is a proprietary commercial product. This project:

- Is **NOT** affiliated with Flux Lab Inc.
- Does **NOT** use Flux.ai's source code, trademarks, or proprietary assets
- References Flux.ai **only** for technical analysis and educational purposes
- Implements similar functionality using **only open-source tools**

**READ THE FOLLOWING FILES FOR LEGAL INFORMATION:**
- `LEGAL_NOTICE.md` - Legal considerations
- `LEGAL_DISCLAIMER.md` - Detailed legal guidance
- `research/flux-ai-patent-search.md` - How to search Flux.ai patents

---

## Project Purpose

This project aims to build an AI-powered electronics design platform that can:

1. Understand natural language circuit descriptions
2. Generate schematics structurally sound
3. Create PCB layouts
4. Export manufacturing files

**It is built exclusively with open-source technologies.**

---

## What We Build Ourselves vs. Use

### ✅ We BUILD:
- AI agent orchestration logic
- Natural language processing layer
- User interface (React/TypeScript)
- Circuit IR management
- Component search logic
- Datasheet extraction pipelines

### 🔧 We USE via subprocess (MIT/GPL-compatible):
- KiCad (EDA engine)
- FreeRouting (autorouter)
- ngspice (SPICE simulator)
- Circuit JSON (intermediate representation)
- SKiDL (circuit-as-code)
- Yjs (collaboration)

---

## Technical Stack

| Layer | Technology | License |
|-------|------------|---------|
| EDA Engine | KiCad | GPL-3.0 |
| Intermediate Representation | Circuit JSON | MIT |
| Automation | kicad-cli, SKiDL | GPL-3.0, MIT |
| Routing | FreeRouting | GPL-3.0 |
| Simulation | ngspice | BSD-3-Clause |
| Backend | FastAPI, PostgreSQL | MIT, PostgreSQL |
| Frontend | React, TypeScript | MIT |
| Collaboration | Yjs | MIT |

---

## License

This project is licensed under GNU GPL-3.0.

**Important:** The GPL-3.0 license applies to the code you write. External GPLv3 tools (KiCad, FreeRouting) are used via subprocess calls, which helps maintain license separation.

**NOT LEGAL ADVICE:** Review with a qualified attorney.

---

## Getting Started

### Prerequisites

1. Python 3.10+
2. KiCad 7+ (for CLI)
3. Node.js 18+ (for frontend)

### Quick Start

```bash
# Clone the repository
git clone <repo-url>
cd AI-Powered-Electronics-Design-Platform

# Initialize submodules
git submodule update --init --recursive

# Install Python dependencies
pip install -r requirements.txt

# Run
python main.py
```

See `ROADMAP.md` for the complete development plan.

---

## Patent Search Before Commercial Use

**YOU MUST SEARCH FOR FLUX.AI PATENTS BEFORE COMMERCIAL DISTRIBUTION.**

See `research/flux-ai-patent-search.md` for instructions.

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
| `ROADMAP.md` | Development plan |
| `AGENTS.md` | Agent policies |
| `LEGAL_NOTICE.md` | Legal notice |
| `LEGAL_DISCLAIMER.md` | Legal disclaimer |
| `research/flux-ai-patent-search.md` | Patent search guide |

---

## Contact

For legal/licensing questions, please consult a qualified attorney.

---

*Copyright (C) 2024 This Project*
*Licensed under GNU GPL-3.0*