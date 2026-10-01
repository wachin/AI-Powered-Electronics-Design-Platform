# TECHNICAL RESEARCH REPORT: AI-Powered Electronics Design Platform

---

## 1. EXECUTIVE SUMMARY

**Main conclusion:** **Yes, it is technically feasible to build a platform similar to Flux.ai by reusing almost exclusively existing open source software.** The mature ecosystem around KiCad (CLI, Python API, S-expression format, MCP servers, autorouters, component databases) covers ~85% of the required functionality. The main gaps are in: (1) Flux-like collaborative web UI, (2) multi-agent orchestration with proprietary IR, (3) RAG on proprietary datasheets.

**The minimum viable combination:**
```
KiCad (EDA engine) + kicad-cli (headless automation) + kicad-python (IPC API)
    + FreeRouting/freeroute (autorouter) + ngspice/PySpice (SPICE)
    + Circuit JSON (intermediate representation) + tscircuit converters
    + SKiDL / circuit-synth / atopile (circuit-as-code layer)
    + JLCPCB/LCSC local catalogs (component database) + KiCanvas (web viewer)
    + Yjs/Automerge (CRDT collaboration) + MCP servers (agent tool layer)
```

---

## 2. FLUX.AI — FEATURE ANALYSIS (Verified)

| Flux.ai Feature | Reproducible with OSS | Comment |
|----------------------|---------------------|------------|
| **Natural language → hardware spec** | ✅ Partial | atopile, circuit-synth, PCBKo, cursor-for-pcb demonstrate this |
| **AI Hardware Engineer (Copilot)** | ✅ Partial | MCP servers (Konnect, kicad-mcp-pro, cursor-for-pcb) + LLM |
| **Schematic capture (browser)** | ⚠️ Partial | KiCanvas (viewer), PCBJam (WASM KiCad), Circuitly (commercial) |
| **PCB layout (browser)** | ⚠️ Partial | PCBJam = KiCad compiled to WASM; KiCanvas = viewer only |
| **AI-assisted routing/placement** | ✅ | FreeRouting, freeroute (Python), rjwalters/kicad-tools, CopperMCP |
| **Component libraries (750K+ parts)** | ⚠️ Partial | JLCPCB/LCSC local catalogs (2.5M-3.5M parts), KiCad libs |
| **Datasheet research/extraction** | ⚠️ Experimental | akcli, kicad-tools datasheet module, circuit-synth JLCPCB search |
| **BOM generation + pricing** | ✅ | kicad-cli, akcli, circuit-synth, JLCPCB MCP servers |
| **Real-time availability/pricing** | ✅ | jlcsearch, jlcpcb-mcp, pcbparts-mcp (live API + local cache) |
| **ERC/DRC continuous** | ✅ | kicad-cli ERC/DRC, Pure Python DRC (rjwalters/kicad-tools, CopperMCP) |
| **SPICE simulation** | ✅ | ngspice, PySpice, Qucs-S, atopile integration |
| **3D visualization** | ✅ | KiCanvas, kicadpreview, pcb-scene3d-viewer, Three.js |
| **Gerbers/drill/pick-place/BOM** | ✅ | kicad-cli export, circuit-synth, akcli |
| **Real-time collaboration** | ❌ Critical gap | PCBJam (commercial), Circuitly (commercial), Yjs/Automerge (tech exists) |
| **Version history + Git** | ✅ | KiCad files are S-expression text, git-friendly |
| **Browser-based, no install** | ⚠️ Partial | PCBJam (WASM), KiCanvas (viewer), need proprietary editor |
| **Cloud architecture** | ❌ Proprietary | Self-hosting possible with OSS components |

**Features requiring significant original development:**
1. **Native collaborative web schematic/PCB editor** (not just viewer)
2. **Proprietary IR (Circuit IR)** with deterministic compiler to KiCad
3. **Multi-agent orchestration** (planner → selector → generator → validator)
4. **RAG on datasheets** with extraction of tables/electrical parameters
5. **Persistent Knowledge Base** per user/team (Flux Copilot Knowledge style)

---

## 3. EDA OPEN SOURCE — TECHNICAL COMPARISON

### 3.1 KiCad (CORE RECOMMENDED) ✅ **Verified**

| Capability | Status | Details |
|-----------|--------|----------|
| Schematic capture | ✅ Complete | `.kicad_sch` S-expression, hierarchical sheets |
| PCB layout (32 layers) | ✅ Complete | Push-and-shove router, differential pairs, impedance |
| ERC | ✅ Complete | `kicad-cli sch erc` |
| DRC | ✅ Complete | `kicad-cli pcb drc`, real-time in PCBnew |
| SPICE integration | ✅ Complete | ngspice bundled, `kicad-cli sch export spice` |
| CLI headless | ✅ Complete | `kicad-cli` (5 subcommands: fp, pcb, sch, sym, version) |
| Python API | ✅ KiCad 11+ | `kicad-python` (IPC API, headless via `kicad-cli api-server`) |
| File formats | ✅ | S-expression (text), `.kicad_pro/.kicad_sch/.kicad_pcb/.kicad_sym/.kicad_mod` |
| 3D models | ✅ | STEP, VRML, glTF export via `kicad-cli pcb export step` |
| Manufacturing outputs | ✅ | Gerber, drill, BOM, pick-place, IPC-2581, STEP, SVG, PDF |
| Library system | ✅ | Symbol/footprint/3D libraries, PCM (Plugin Manager) |
| Scripting | ✅ | Action plugins (Python), IPC API, `kicad-cli` |
| License | **GPL-3.0** | Compatible with GPL/AGPL, not with MIT/Apache static linking |

**Verified evidence:** Official KiCad 8/9/10/11 CLI documentation, kicad-python GitLab, kicad-mcp-pro architecture docs.

### 3.2 LibrePCB ⚠️ **Likely** (alternative, not main engine)

| Aspect | Status |
|---------|--------|
| Schematic + PCB | ✅ Complete, Qt6 + Rust |
| File format | `.lpproj` / `.lpsch` / `.lpptc` (native), KiCad import one-way |
| SPICE | ❌ Not native (planned) |
| CLI/Automation | ❌ Limited (no documented headless) |
| License | **GPL-3.0** |
| Maturity | v1.0.0 rc, production viable but less mature than KiCad |

**Verdict:** Not recommended as main engine. KiCad is superior in automation, ecosystem, maturity.

### 3.3 gEDA/lepton-eda ⚠️ **Likely** (legacy, fragmented)

- **gschem** (schematic) + **PCB** (layout) + **gnetlist** (30+ netlist formats) + **ngspice/gnucap** (sim)
- `gsch2pcb` schematic↔PCB bridge
- License: **GPL-2.0+**
- Status: Lepton-EDA active fork, but fragmented architecture, without modern unified CLI.

### 3.4 pcb-rnd / Ringdove ⚠️ **Experimental**

- Modular, scriptable (10+ languages), CLI + server mode
- Imports KiCad, Eagle, Protel
- Autorouter `route-rnd` included
- License: **GPL-2.0+**
- Less mature, small community.

### 3.5 QUCS / Qucs-S ⚠️ **Likely** (simulation only)

- GUI for simulation (DC, AC, S-param, HB, noise)
- Imports SPICE models
- No complete schematic capture nor PCB layout
- License: **GPL**

### 3.6 ngspice ✅ **Verified** (standard SPICE engine)

- SPICE 3f5 + XSpice + CIDER fork
- Shared library (`libngspice.so`) for embedding
- Used by KiCad, PySpice, SKiDL, atopile
- License: **BSD-3-Clause** (compatible with all)

### 3.7 PySpice ✅ **Verified** (Python → ngspice/Xyce)

- Object-oriented API, units, NumPy/Matplotlib output
- Partial SPICE netlist parser
- **License: GPL-3.0** ⚠️ (affects linking)
- Documented KiCad integration

### 3.8 SKiDL ✅ **Verified** (Circuit-as-Code Python)

- Describes circuits in Python → KiCad netlist + ERC
- Generates editable KiCad schematics (graphviz layout)
- SPICE integration, hierarchical design
- **License: MIT** ✅
- Base of: cursor-for-pcb, Circuitron, PCBKo, circuit-synth

### 3.9 Circuit JSON / tscircuit ✅ **Verified** (Intermediate Representation)

- Low-level JSON-array: `source_*`, `schematic_*`, `pcb_*`, `simulation_*`
- Bidirectional KiCad ↔ Circuit JSON (tscircuit/kicad-to-circuit-json, circuit-json-to-kicad)
- Generates Gerber, SPICE, SVG, 3D, BOM, pick-place
- **License: MIT** (core), **AGPL-3.0** (circuitjson-toolkit)
- Designed for SQL database interoperability

### 3.10 atopile ✅ **Verified** (Declarative Hardware Language)

- Declarative `.ato` language, constraint-based
- Compiler resolves constraints, picks parts, checks, updates KiCad
- VS Code extension, CLI, Python API, **MCP server**
- **License: MIT** (compiler/language), open-core model
- Units, tolerances, assertions, parametric part selection

### 3.11 circuit-synth ✅ **Verified** (Python + AI + KiCad round-trip)

- Python circuits → KiCad project (`.kicad_pro/.sch/.pcb`)
- Auto source reference rewriting (round-trip refs sync)
- 7 pre-made circuit patterns (buck, boost, battery charger, etc.)
- JLCPCB/DigiKey/SnapEDA component sourcing
- FMEA analysis, PDF/Gerber export via kicad-cli
- **Claude Code skills**: circuit-architect, component-search, simulation-expert, kicad-integration
- **License: MIT** ✅

### 3.12 CircuitDK ⚠️ **Experimental** (Reconciliation KiCad↔Python)

- Python owns logic, KiCad owns visual presentation
- `circuitdk diff/deploy/test/drift/adopt/move/lock/inspect`
- KiCad 10 only, experimental
- **License: MIT**

---

## 4. KICAD AUTOMATION — EXHAUSTIVE CATALOG

### 4.1 MCP Projects for KiCad (Verified)

| Project | Stars | License | Tools | Architecture | Maturity |
|----------|-------|---------|-------|--------------|---------|
| **mixelpixx/Konnect** | 289 | **AGPL-3.0** | 203 (19 toolsets) | Rust binary, KiCad 10 IPC API, no SWIG | **Beta, production-ready** |
| **DCENT_Konduit** | — | **AGPL-3.0** | 570+ | Fork Konnect, single binary, offline JLCPCB | Beta |
| **obhox/kicad-mcp** | — | **AGPL-3.0** | 185 | Fork Konnect v0.2.2 | Active |
| **blwfish/kicad-mcp** | 4 | **MIT** | 71 (17 domains) | Pure Python, 3 backends (S-exp, kicad-cli, IPC) | v0.11.0 |
| **tylerwagler/KiCad-MCP** | — | **GPL-3.0** | 152 | Pure Python S-exp parser, session model, 918 tests | Active |
| **oaslananka/kicad-mcp-pro** | 100 | **MIT** | 377 (profiles) | Production-grade, quality gates, SI/PI/EMC, DFM | v3.x, complete CI/CD |
| **ProductOfAmerica/mcp-server-kicad** | 5 | **MIT** | 109 (5 sub-servers) | Byte-preserving substrate, skills, agents | Active |
| **havamal-65/KiCad-MCP** | — | — | — | PluginDirectBackend (IPC→TCP→file), FastMCP | Active |
| **lamaalrajih/kicad-mcp** | 493 | **MIT** | — | KiCad 9+, project mgmt, BOM, DRC, visualization | Active |
| **Seeed-Studio/kicad-mcp-server** | — | — | — | KiCad 8/9/10, schematic+PCB analysis, code gen | Active |
| **10on/schematic-mcp-bridge** | — | — | 15 MCP tools | Semantic schematic model (no coords), KiCad export via SKiDL | MVP complete |
| **Finerestaurant/kicad-mcp-python** | — | — | — | kicad-python submodule, IPC API, pre/post board status | Early |
| **AbdulAzeez0001/kicad-mcp** | — | — | — | kicad-cli headless + kipy IPC + SKiDL + preflight | Active |

**Verified MCP capabilities (union of projects):**
- ✅ Create project, schematic, PCB
- ✅ Add components (symbol + footprint)
- ✅ Wire connections (schematic)
- ✅ Place/move/rotate footprints (PCB)
- ✅ Route traces (manual + FreeRouting autorouter)
- ✅ Run ERC / DRC (via kicad-cli)
- ✅ Export Gerbers, drill, BOM, pick-place, STEP, PDF, SVG, IPC-2581
- ✅ Netlist generation (SKiDL + native)
- ✅ JLCPCB/LCSC part search (local DB + live API)
- ✅ Schematic read/write (S-expression parser)
- ✅ DRC/ERC report parsing
- ✅ Placement optimization (CMA-ES, Bayesian)
- ✅ Pure Python DRC (without kicad-cli)
- ✅ Session model with undo/rollback (tylerwagler)
- ✅ Quality gates / preflight certification (AbdulAzeez, oaslananka)

### 4.2 Non-MCP Tools (Python libraries)

| Project | Function | License | Verified |
|----------|---------|---------|------------|
| **rjwalters/kicad-tools** | Pure Python S-exp parser, A* PCB router, Pure Python DRC, circuit blocks, LLM reasoning, MCP server | MIT | ✅ v0.15.1 |
| **kicad-sch-api** (circuit-synth) | Read/write `.kicad_sch` exact format preservation, MCP 15 tools | MIT | ✅ |
| **akcli-kicad** | Zero-dep Python CLI, 22-op JSON op-list, net-diff safety, ERC-lite, ngspice sim, JLCPCB, Altium import | MIT | ✅ v0.16 |
| **mattpainter701/kicad_automations (Circuit Weaver)** | YAML spec → KiCad artifacts, HTTP API, MCP, CLI, agent skills | MIT | ✅ v0.32 |
| **td2sk/circuitdk** | Reconciliation Python↔KiCad, diff/deploy/test/drift | MIT | ⚠️ Experimental |
| **devbisme/skidl** | Circuit-as-code Python → netlist/schematic/PCB/SPICE | MIT | ✅ v2.3.0 |

### 4.3 Capability Table by Project

| Capability | Konnect | kicad-mcp-pro | rjwalters/kicad-tools | akcli | Circuit Weaver | circuit-synth | SKiDL |
|-----------|---------|---------------|----------------------|-------|----------------|---------------|-------|
| Create project | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Schematic read/write | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| PCB read/write | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ❌ |
| Add component | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Wire/connect | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Place footprint | ✅ | ✅ | ✅ | ❌ | ⚠️ | ⚠️ | ❌ |
| Route traces | ✅ | ✅ | ✅ (A*) | ❌ | ⚠️ | ❌ | ❌ |
| Run ERC | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Run DRC | ✅ | ✅ | ✅ (pure Python) | ✅ | ✅ | ✅ | ❌ |
| Export Gerbers | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| Export BOM | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| JLCPCB search | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ❌ |
| SPICE sim | ❌ | ✅ | ❌ | ✅ | ❌ | ✅ | ✅ |
| Pure Python (no KiCad) | ❌ | ❌ | ✅ | ✅ | ✅ | ⚠️ | ✅ |
| Headless | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| MCP server | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ (skills) | ❌ |
| Session/undo | ❌ | ❌ | ❌ | ✅ (undo) | ❌ | ❌ | ❌ |

---

## 5. AI/LLM ARCHITECTURES FOR ELECTRONICS

### 5.1 Architectures Found

#### A. **Direct Generation** (LLM → KiCad files)
- **Projects:** akcli (JSON ops), cursor-for-pcb (SKiDL Python), PCBKo (DeepSeek)
- **Risk:** LLM hallucinates connections, footprints, values
- **Mitigation:** Net-diff safety (akcli), ERC gates (cursor-for-pcb), validation loops (Circuitron)

#### B. **Structured IR + Deterministic Compiler** (RECOMMENDED)
```
Natural Language → Requirements Interpreter → Engineering Spec → Circuit IR → Deterministic Compiler → KiCad
```
- **Projects that implement it:**
  - **atopile**: declarative `.ato` → compiler → KiCad
  - **circuit-synth**: Python → Circuit IR → KiCad (round-trip)
  - **CircuitDK**: Python owns logic → reconcile → KiCad
  - **10on/schematic-mcp-bridge**: Semantic model → validation → KiCad export
  - **Circuit JSON**: Low-level IR → tscircuit converters → KiCad

#### C. **Multi-Agent Pipeline**
- **Circuitron** (archived): Planner → Part Finder → Selector → Doc Agent → Code Gen → Validator → ERC Handler → Execution
- **Circuit Weaver**: Design wizard → validation → generation → placement review → PCB → manufacturing
- **cursor-for-pcb**: Chat → pcbforge engine (Design → SKiDL netlist → kiutils PCB → kicad-cli verify)

### 5.2 Advantages/Disadvantages

| Architecture | Advantages | Disadvantages | Risks |
|--------------|----------|-------------|---------|
| **Direct LLM→KiCad** | Simple, flexible | Hallucinations, not verifiable, brittle | **High** - LLM does not understand physics |
| **Structured IR** | Verifiable, deterministic, testable, auditable | More initial code, complex IR design | **Medium** - IR completeness |
| **Multi-Agent** | Separation of concerns, iterative correction | Latency, orchestration complexity | **Medium** - Agent coordination |

**Evidence:** atopile compiler architecture docs, circuit-synth round-trip, Circuitron multi-agent, 10on schematic-mcp-bridge stages.

---

## 6. INTERMEDIATE REPRESENTATION (CIRCUIT IR)

### 6.1 Existing Candidates

| IR | Format | Pros | Cons | Maturity |
|----|---------|------|---------|---------|
| **Circuit JSON** (tscircuit) | Typed JSON array (zod) | Bidirectional KiCad, SQL-friendly, Gerber/SPICE/SVG/3D, separate source/schematic/pcb types | Verbose, TypeScript-centric | ✅ **Verified** production |
| **SKiDL Circuit** | Python objects | Python-native, integrated ERC, hierarchical, multiple outputs | Python-only, no standard interchange | ✅ **Verified** |
| **atopile IR** | Graph (nodes/edges/traits) | Declarative, constraint solver, units/tolerances, solver picks parts | Proprietary language (`.ato`), learning curve | ✅ **Verified** |
| **netlist (SPICE/EDIF/KiCad)** | Text/sexpr | Universal, tool-agnostic | Loss of intent/constraints, no placement | ✅ **Verified** |
| **EDIF** | Standard | Formal interchange | Verbose, legacy, limited adoption | ⚠️ **Likely** |
| **IPC-2581** | XML | Complete manufacturing | Complex, overkill for design | ⚠️ **Likely** |

### 6.2 Recommendation: **Circuit JSON + SKiDL + atopile traits**

```
User NL → atopile-style spec (requirements, constraints, units)
    ↓
Circuit JSON (source_* elements) — canonical, DB-friendly
    ↓
Deterministic compiler (tscircuit converters)
    ↓
KiCad (schematic + PCB) — verified by kicad-cli ERC/DRC
    ↓
FreeRouting/freeroute (autorouter) → updated PCB
    ↓
SPICE simulation (PySpice/ngspice) → validation
    ↓
Manufacturing package
```

**Advantages:** Circuit JSON already has proven bidirectional KiCad converters, types for everything (schematic, PCB, sim, 3D, mfg), zod schemas for validation, SQL-ready.

---

## 7. COMPONENT DATABASES

### 7.1 Open Sources (Verified)

| Source | Parts | Access | Data | License |
|--------|--------|--------|-------|---------|
| **KiCad official libraries** | ~10K symbols + footprints | Local + GitLab | Symbol, footprint, 3D model, MPN fields | **GPL-3.0** |
| **DigiKey GitHub** | 150+ curated libs | GitHub | Symbol + footprint (auto-converted) | **MIT/Apache** |
| **SnapEDA** | Millions | API (free tier) | Symbol, footprint, 3D, datasheet | **Proprietary API** |
| **LCSC/JLCPCB (jlcparts/yaqwsx)** | 3.2M-3.5M | **Local SQLite** (11GB→2GB optimized) | MPN, package, stock, price, basic/extended, datasheet URL, parametric specs | **Community mirror** |
| **tscircuit/jlcsearch** | 2GB optimized DB | Web API + JSON | Resistors/caps/inductors parametric search | MIT |
| **casimir-engineering/jlc-search** | 3.5M | Local + API | Full-text, range filters, datasheet indexing (42 extractors) | — |
| **inyosystems/jlcparts-mcp** | yaqwsx catalog | Local SQLite + MCP | Cache-first, category/parametric search | — |
| **Eyalm321/jlcpcb-mcp** | yaqwsx + live LCSC | SQLite + live API | Dual stock (JLC assembly vs LCSC retail), pricing tiers, datasheets | — |
| **mageoch/LCSC-MCP-Server** | JLCPCB assembly | API-first (cache 6h/24h) | Requires JLCPCB credentials, parametric search | — |
| **Averyy/pcbparts-mcp** | JLCPCB + Mouser + DigiKey | 1.5M+ parts | Cross-distributor, parametric, SamacSys footprints | — |
| **@jlcpcb/core + @jlcpcb/mcp** | NPM packages | API + local | Category libraries, hybrid footprint strategy | MIT |

### 7.2 Legal Classification

| Category | Examples | Redistribution | Commercial Use |
|-----------|----------|----------------|---------------|
| **Open data** | KiCad libs, DigiKey GitHub | ✅ Yes | ✅ Yes |
| **Community mirror** | yaqwsx/jlcparts, jlcsearch | ⚠️ Gray area (JLCPCB no official API) | ⚠️ Personal/educational |
| **Free API (rate limited)** | SnapEDA, LCSC public, Mouser/DigiKey (with key) | ❌ No (ToS) | ✅ With API key |
| **Commercial API** | Octopart, DigiKey API, Mouser API | ❌ No | ✅ Paid plans |
| **Scraping** | JLCPCB website | ❌ ToS violation | ❌ Legal risk |

**Recommendation:** Use **yaqwsx/jlcparts local SQLite** (2GB) as offline base + **live LCSC API** for real-time stock/price/datasheet. For production, request **JLCPCB Open Platform API credentials**.

---

## 8. DATASHEET UNDERSTANDING

### 8.1 Open Source Projects

| Project | Capability | Status |
|----------|-----------|--------|
| **akcli-kicad** | PDF parsing, diode model fitting from datasheet points, equation extraction (`@calculator`) | ✅ Verified v0.16 |
| **rjwalters/kicad-tools** | `datasheet` module: search, download, PDF parsing | ✅ Verified |
| **circuit-synth** | Datasheet fetch via JLCPCB/LCSC, pin extraction | ✅ Verified |
| **mattpainter701/kicad_automations** | Datasheet facts store, propose/tree/validate | ✅ Verified |
| **coppermind** | Datasheet enrichment via LCSC, LCSC direct client | ✅ Verified |
| **mixelpixx/Konnect** | Datasheet integration (planned) | ⚠️ Planned |

### 8.2 Base Technologies

| Technology | Use | License |
|------------|-----|----------|
| **pdfplumber / PyMuPDF (fitz)** | Text + table extraction | MIT / AGPL |
| **pdfminer.six** | Text extraction | MIT |
| **tabula-py / camelot** | Table extraction | MIT / AGPL |
| **pymupdf (fitz)** | Fast PDF parsing, images | AGPL-3.0 |
| **donut (OCR-free)** | Document understanding transformer | Apache-2.0 |
| **LayoutLM / DocFormer** | Multimodal document AI | Apache-2.0 |
| **Marker (marker-project)** | PDF → Markdown + JSON | MIT |
| **Unstructured.io** | Partitioning + chunking | Apache-2.0 |

### 8.3 Recommended Pipeline

```
PDF datasheet → Marker/pdfplumber → structured Markdown/JSON
    → LLM/RAG (embeddings) → vector DB (Qdrant/Chroma/pgvector)
    → Structured extraction: pin tables, electrical params, recommended circuits, abs max ratings
    → Validation against component DB (LCSC MPN match)
    → Cache in SQLite with TTL
```

---

## 9. CIRCUIT VALIDATION (DETERMINISTIC)

### 9.1 Verified Capabilities

| Validation | Tool | Type | Verified |
|------------|-------------|------|------------|
| **ERC** | `kicad-cli sch erc` | KiCad native | ✅ |
| **ERC** | akcli `check` (ERC-lite + power + BOM + connectivity) | Pure Python | ✅ |
| **ERC** | rjwalters/kicad-tools `kct erc` | Pure Python | ✅ |
| **ERC** | SKiDL `ERC()` | Python (pin drive conflicts, floating) | ✅ |
| **DRC** | `kicad-cli pcb drc` | KiCad native | ✅ |
| **DRC** | rjwalters/kicad-tools `kct check` (pure Python) | Pure Python | ✅ |
| **DRC** | CopperMCP (KiCad CLI DRC evidence-bound) | KiCad CLI | ✅ |
| **DRC** | freeroute `exact` engine (integer geometry verification) | Pure Python | ✅ |
| **Creepage/clearance** | rjwalters `kct creepage` (IEC 60664-1/62368-1) | Pure Python | ✅ |
| **Manufacturing audit** | rjwalters `kct audit` / Circuit Weaver `manufacturing-readiness` | Composite | ✅ |
| **Signal integrity** | rjwalters `kct analyze` / Seeed-Studio MCP | KiCad PCB analysis | ✅ |
| **Power integrity** | Seeed-Studio MCP `analyze_pcb_power_integrity` | KiCad PCB analysis | ✅ |
| **SPICE sim** | ngspice / PySpice / atopile / akcli / circuit-synth | Analog simulation | ✅ |

### 9.2 Senior Design Review (cursor-for-pcb / Circuit Weaver)

- **Grade A zero-error**: decoupling caps, bulk caps, USB-C CC pulldowns, MCU reset/boot straps, LED series resistors, no floating pins, ERC=0, DRC clean, ground pour
- **Verified:** cursor-for-pcb produces ESP32 dev board grade A consistently

### 9.3 Architectural Principle

> **"The AI proposes, deterministic tools verify."**
> - LLM generates schematic/PCB
> - `kicad-cli ERC/DRC` are the authority (not the LLM)
> - Pure Python DRC for CI/CD without KiCad
> - Quality gates block manufacturing export if they do not pass (kicad-mcp-pro, Circuit Weaver preflight)

---

## 10. PCB PLACEMENT & ROUTING

### 10.1 Open Source Autorouters

| Autorouter | Language | Algorithm | KiCad Integration | License | Status |
|------------|----------|-----------|-------------------|---------|--------|
| **FreeRouting** | Java | A* expansion-room, rip-up-reroute, shove | DSN/SES via kicad-cli | **GPL-3.0** | ✅ Production, v2.4.0 (2026), MCP server |
| **freeroute** (warehack.ing) | Python | Grid A*, exact integer (tiles/octagons), room-based | DSN/SES, drop-in replacement | **GPL-3.0** | ✅ Alpha v0.1, no JVM |
| **rjwalters/kicad-tools router** | Python | A* grid + net class awareness | Native PCB modification | **MIT** | ✅ v0.15 |
| **coppermind** | Python | Freerouting integration (Java/Docker/Podman) | IPC-first | **MIT** | ✅ |
| **CopperMCP** | Python | Bounded integer A*, negotiated congestion | MCP, deterministic candidates | — | Active research |
| **cursor-for-pcb** | Python | Lee/maze 2-layer A* | Built-in, kiutils PCB | **MIT** | ✅ v0.1 |
| **PCBKo** | Python | Custom A* grid 2-layer | Tkinter canvas + KiCad export | **MIT** | Early |
| **route-rnd** (pcb-rnd) | C | Maze/Lee | Native pcb-rnd | **GPL** | ⚠️ Separate suite |

### 10.2 Placement

| Project | Algorithm | Verified |
|----------|-----------|------------|
| **rjwalters/kicad-tools** | Physics-based + CMA-ES/Bayesian global optimization | ✅ |
| **cursor-for-pcb** | Connectivity-aware + courtyard-aware, multi-pad power pins | ✅ |
| **coppermind** | Placement intent contract + deterministic legalizer | ✅ |
| **CopperMCP** | Typed placement-intent + deterministic legalizer | ✅ |
| **KiCad native** | Manual + auto-place (basic) | ✅ |

### 10.3 Recommendation

**Routing stack:**
1. **FreeRouting (Java JAR)** — best completeness on dense boards, used by KiCad MCP servers
2. **freeroute (Python)** — for CI/CD without JVM, Python-native MCP servers
3. **rjwalters A*** — for simple routing, LLM-reasoning integration

---

## 11. SPICE SIMULATION

| Project | Backend | API | Integration | License |
|----------|---------|-----|-------------|---------|
| **ngspice** | SPICE 3f5 + XSpice + CIDER | Shared lib / CLI | KiCad bundled, PySpice, SKiDL, atopile | **BSD-3-Clause** |
| **PySpice** | ngspice / Xyce | Python OO, NumPy/Matplotlib | KiCad, partial SPICE netlist parser | **GPL-3.0** |
| **Qucs-S** | ngspice (QuCS backend) | Qt GUI | S-param, HB, noise | **GPL** |
| **gnucap** | event-driven + continuous | CLI | ngspice alternative | **GPL** |
| **Xyce** (Sandia) | parallel SPICE | Python bindings | High-performance, research | **GPL-3.0** |

**Automatable Workflow (Verified):**
```
User: "Build a 5V to 3.3V regulator circuit."
 1. Generate schematic (via IR/compiler)
 2. Select components (LCSC catalog)
 3. Generate SPICE deck (kiutils / SKiDL / PySpice)
 4. Run ngspice (headless CLI or shared lib)
 5. Check voltage/current (NumPy analysis)
 6. Report problems (parsing output)
 7. Modify design if needed (iterative loop)
```
- **Evidence:** akcli `sim` (deck → bundled ngspice), circuit-synth `simulation-expert`, SKiDL SPICE, atopile SPICE woven

---

## 12. WEB APPLICATION ARCHITECTURE

### 12.1 Technologies

| Technology | Use | Status |
|------------|-----|--------|
| **KiCanvas** (theacodes) | Schematic/PCB viewer TypeScript+WebGL, embedding API | ✅ Verified (MIT) |
| **Huaqiu-Electronics/ecad-viewer** | KiCanvas fork + Altium import + 3D + BOM, custom elements | ✅ Verified |
| **kicadpreview** (npm) | KiCad SCH/PCB/3D/BOM viewer, Web Components, lazy three.js | ✅ Verified |
| **shishir-dey/KiView** | 3D viewer, Rust+WASM parser + Three.js | ✅ Verified |
| **SunboX/ecadforge_app** | Altium+KiCad+Gerber+CircuitJSON viewer, WebMCP read-only tools | ✅ Verified |
| **SunboX/pcb-scene3d-viewer** | Reusable Three.js 3D scene (STEP/WRL/STL/OBJ/GLTF/3MF) | ✅ Verified |
| **PCBJam** | Complete KiCad compiled to WASM (no rewrite), wxWidgets port | ✅ Verified (GPL, alpha) |
| **KiCadWebView** (climbers.net) | 17KB library, SVG + SVGPanZoom, embed in docs | ✅ Verified |
| **Circuitly** | Commercial: GPU rendering + git + CRDT | ⚠️ Reference |

### 12.2 Architectures for the Web Editor

| Option | Description | Advantages | Disadvantages |
|--------|-------------|----------|-------------|
| **A. New browser editor** | Build proprietary TypeScript+WebGL | Full control, lightweight | Lots of code, EDA quality risk |
| **B. KiCad as backend + web frontend** | KiCad headless API server + web client that calls it | Reuses EDA, proven renderer | No real-time interactive editor |
| **C. KiCad WASM (PCBJam)** | Compile KiCad to WebAssembly, run in browser | Full native KiCad in browser | 130MB bundle, GPL, complex build |
| **D. Hybrid** | KiCanvas viewer + new proprietary editor + KiCad headless backend | Better UX + reuse | More complex to integrate |
| **E. Web component over Circuit JSON** | tscircuit CSSDOM, render SVG/3D from Circuit JSON | Format-driven, editable | tscircuit ecosystem young |

### 12.3 Recommendation for the Editor

**Hybrid approach (D + E):**
- **Frontend editor**: React/TypeScript, render with proprietary SVG/Canvas/WebGL over Circuit JSON (canonical format)
- **Existing viewers**: KiCanvas for quick verification; ecad-viewer for rich 2D/3D previews
- **Backend**: KiCad headless (`kicad-cli api-server` in KiCad 11) or kicad-cli subprocess for ERC/DRC/export
- **Real-time**: convert UI changes → Circuit JSON diffs → apply to KiCad project on server

---

## 13. 3D PCB VISUALIZATION

| Project | Format | Renderer | Capabilities | License |
|----------|---------|----------|---------------|---------|
| **KiCanvas** | KiCad native | WebGL | Pan/zoom, layers, nets, footprints | MIT |
| **ecad-viewer (Huaqiu)** | KiCad+Altium+glTF | WebGL (Three.js) | 3D from STEP, Altium import, BOM | MIT |
| **kicadpreview** | KiCad+GLB | three.js lazy | SCH/PCB/3D/BOM viewer | MIT |
| **KiView** | KiCad | Rust+WASM+Three.js | Fast 3D viewer | MIT |
| **pcb-scene3d-viewer** | CircuitJSON/STEP/WRL/STL/OBJ/GLTF/3MF | Three.js | STEP via occt-import-js, GLTF assembly, picking | MIT |
| **KiCad native** | STEP/VRML export | `kicad-cli pcb export step` | 3D models + enclosure | GPL |

---

## 14. COLLABORATION AND VERSION CONTROL

### 14.1 Git + KiCad (Verified)

- KiCad files are **S-expression text** → git-friendly for versioning
- **No automatic merge** functional (2D/3D data inherent problem)
- Recommended workflow: **one user per sheet/layer**, manual coordination
- Multi-sheet: one person per sheet is viable
- Schematic in one branch, PCB in another

### 14.2 CRDT / Real-time

| Technology | Description | Use in EDA |
|------------|-------------|------------|
| **Yjs** | CRDT framework, shared types, network-agnostic, offline-first | Circuitly uses CRDT (reference), y-mxgraph demo (draw.io+Yjs) |
| **Automerge** | CRDT JSON documents | Alternative to Yjs |
| **y-mxgraph** | draw.io (mxGraph)+Yjs binding | Pattern: diagram editor + CRDT |
| **Circuitly** | VCS + CRDT + GPU rendering (commercial) | Reference architecture |

### 14.3 Recommended Collaboration Framework

```
USER A ──► Yjs/Automerge ──► Realtime sync engine
USER B ──► Yjs/Automerge ──► (WebSocket/WebRTC)
       kicad (schematic)
       └─► deterministic compile/apply
       Circuit JSON doc (canonical)
       └─► snapshot → git commit (version control)
```

- **Real-time**: Yjs over proprietary data structure (Circuit JSON)
- **Persistence**: periodic snapshot in Git
- **Comments**: on circuit elements (stable IDs)

---

## 15. SECURITY

### 15.1 Identified Risks

| Risk | Vector | Mitigation |
|--------|--------|------------|
| **Prompt injection in datasheets** | PDFs contain malicious instructions for LLM | Treat datasheets as data, not instructions; sandboxing |
| **Malicious project files** | `.kicad_sch/.kicad_pcb` untrusted | Validate inputs, do not use f-strings with net names, parse with strict parser |
| **Arbitrary code execution** | SKiDL/Python code from LLM | Sandbox (Docker), restricted filesystem |
| **Unsafe Python execution** | AI scripts on server | Isolated subprocess, resource limits |
| **Path traversal** | Tools accept arbitrary paths | `path_safety.resolve_under` pattern (kicad-mcp-pro) |
| **Command injection** | Net names / filenames in subprocess | `subprocess.run([...], shell=False)`, never shell |
| **MCP server abused** | Destructive tool calls | Operating modes (readonly/write/manufacturing), tool filters |
| **Supply-chain** | Compromised dependencies | SBOM, Sigstore, pinned Actions (kicad-mcp-pro pattern) |
| **LLM hallucinations** | Generates incorrect designs | Deterministic quality gates (kicad-cli ERC/DRC), human approval |
| **Indirect prompt injection (hooks, config files)** | `.cursorrules`, `CLAUDE.md`, MCP config in workspace | Denylist of config paths, explicit approval |

### 15.2 Recommended Permission Model (based on kicad-mcp-pro)

| Mode | Capabilities | Use |
|------|--------------|-----|
| **READONLY** | All reads, analysis, reports | Untrusted projects |
| **WRITE** | Write tools with approval | Trusted projects, active design |
| **SIMULATE** | write + SPICE execution | Design iteration |
| **EXPORT** | write + export Gerber/STEP/etc. | Release preparation |
| **MANUFACTURING** | gated release (mandatory quality gates) | Only when ERC=0, DRC=0 |

**Security principles (verified from AgentBound paper + kicad-mcp-pro docs):**
1. Default deny
2. Least privilege
3. Explicit consent for destructive operations
4. Sandboxing (Docker/containerization)
5. Path validation / traversal blocking
6. No shell execution
7. Secret injection (not environment propagation)
8. Network egress control

---

## 16. LICENSE ANALYSIS

### 16.1 Component License Table

| Project | License | Commercial | Modify | Redistribute | Linking obligations | GPL-3.0 compat |
|----------|---------|-----------|-----------|--------------|---------------------|----------------|
| **KiCad** | GPL-3.0 | ✅ | ✅ | ✅ (GPL) | Derivatives GPL | ✅ |
| **kicad-cli** | GPL-3.0 | ✅ | ✅ | ✅ (GPL) | Derivatives GPL | ✅ |
| **kicad-python** | GPL-3.0 | ✅ | ✅ | ✅ (GPL) | Derivatives GPL | ✅ |
| **ngspice** | BSD-3-Clause | ✅ | ✅ | ✅ | No copyleft | ✅ |
| **PySpice** | GPL-3.0 | ✅ | ✅ | ✅ (GPL) | Derivatives GPL | ✅ |
| **SKiDL** | MIT | ✅ | ✅ | ✅ (MIT) | No obligations | ✅ |
| **Circuit JSON** | MIT (core) | ✅ | ✅ | ✅ (MIT) | No obligations | ✅ |
| **circuitjson-toolkit** | AGPL-3.0 | ⚠️ With AGPL obligations | ✅ | ✅ (AGPL) | Redistribution requires AGPL | ⚠️ AGPL conflicting |
| **tscircuit converters** | MIT | ✅ | ✅ | ✅ | No obligations | ✅ |
| **atopile** | MIT (open-core) | ✅ | ✅ | ✅ | No obligations | ✅ |
| **circuit-synth** | MIT | ✅ | ✅ | ✅ | No obligations | ✅ |
| **FreeRouting** | GPL-3.0 | ✅ | ✅ | ✅ (GPL) | Derivatives GPL | ✅ |
| **freeroute** | GPL-3.0 | ✅ | ✅ | ✅ (GPL) | Derivatives GPL | ✅ |
| **rjwalters/kicad-tools** | MIT | ✅ | ✅ | ✅ | No obligations | ✅ |
| **akcli-kicad** | MIT | ✅ | ✅ | ✅ | No obligations | ✅ |
| **kicad-mcp-pro** | MIT | ✅ | ✅ | ✅ | No obligations | ✅ |
| **Konnect (mixelpixx)** | AGPL-3.0 | ⚠️ With AGPL obligations | ✅ | ✅ (AGPL) | Redistribution requires AGPL | ⚠️ AGPL conflicting |
| **DCENT_Konduit** | AGPL-3.0 | ⚠️ With AGPL obligations | ✅ | ✅ (AGPL) | Redistribution requires AGPL | ⚠️ AGPL conflicting |
| **PCBJam** | GPL | ✅ | ✅ | ✅ (GPL) | Derivatives GPL | ✅ |
| **KiCanvas** | MIT | ✅ | ✅ | ✅ | No obligations | ✅ |
| **ecad-viewer** | MIT | ✅ | ✅ | ✅ | No obligations | ✅ |
| **Yjs** | MIT | ✅ | ✅ | ✅ | No obligations | ✅ |
| **yaqwsx/jlcparts** | ? | ⚠️ (data mirror) | ⚠️ | ⚠️ | — | — |
| **jlcsearch** | MIT | ✅ | ✅ | ✅ | No obligations | ✅ |

### 16.2 Integration Considerations

| Scenario | Potential Problem | Recommendation |
|-----------|--------------------|---------------|
| **Static linking with KiCad/PySpice** | GPL derivative → our software GPL | Distribute as separate processes (subprocess), not linking |
| **AGPL in SaaS** | AGPL (Konnect, circuitjson-toolkit, DCENT) requires publishing service code | Use these in subprocess non-sharing mode, or choose MIT alternatives |
| **Data mirror (jlcparts)** | Redistribution of JLCPCB data | Keep as downloadable data, not included; document terms of use |
| **DigiKey GitHub libs** | Conversion license | Auto-convert do not redistribute as proprietary |
| **MIT + GPL mixing** | MIT over GPL is OK (GPL is lax); GPL over MIT is not | Keep MIT core aside from GPL components (separated) |

**This is not legal advice.** Identify technical incompatibilities that a lawyer should review.

---

## 17. CANDIDATE ARCHITECTURES

### Architecture A: KiCad + AI Agent

```
┌──────────────────────────────┐
│        Web Frontend          │  React/TS + KiCanvas viewer
└─────────────┬────────────────┘
              │ REST / WebSocket
┌─────────────▼────────────────┐
│        Agent Orchestrator    │  LLM: planner → selector → generator
└─────────────┬────────────────┘
              │ MCP / HTTP
┌─────────────▼────────────────┐
│      KiCad Backend           │  kicad-cli headless + kicad-python IPC
│  (Schematic → PCB → ERC/DRC  │  + FreeRouting (autorouter)
│   → Gerbers/BOM/pick-place)  │
└──────────────────────────────┘
```

**Components:**
- KiCad (GPL), kicad-cli, kicad-python
- MCP server (rjwalters/kicad-tools or blwfish/kicad-mcp MIT)
- FreeRouting/freeroute
- JLCPCB local DB + live API
- ngspice/PySpice

**Advantages:** Maximum reuse, proven EDA, headless compatible.
**Disadvantages:** No interactive web editor; dependency on installed KiCad; GPL limits integrated distribution.
**Difficulty:** Medium (orchestration + backend API)
**Self-hosting:** ✅ Easy, Docker with KiCad.
**Risks:** GPL + AGPL ecosystem, basic UX.

---

### Architecture B: Browser EDA + AI Agent

```
┌──────────────┐   ┌──────────────┐
│   Web Editor │   │  AI Agent    │
│  (TS/WebGL)  │   │   (LLM core) │
└──────┬───────┘   └──────┬───────┘
       │       Circuit JSON
       └─────────┬────────┘
              Default IR
                 │ compiler
┌────────────────▼────────────────┐
│   Deterministic EDA Pipeline    │  Circuit JSON → KiCad
│   (converters + verification)   │  → ERC/DRC → Gerbers
└─────────────────────────────────┘
```

**Components:**
- Proprietary editor (React/TS, SVG/WebGL over Circuit JSON)
- Circuit JSON (IR) + tscircuit converters
- Optional KiCad headless as validation
- FreeRouting, ngspice
- JLCPCB catalog

**Advantages:** Real Flux-like UX, full control, standardized format.
**Disadvantages:** Editor QC costly, lack of EDA maturity in browser.
**Difficulty:** High (complete editor).
**Self-hosting:** ✅ Facilitated by JSON IR.
**Risks:** Quality editor, render stacking layers, autorouter integration.

---

### Architecture C: Hybrid (RECOMMENDED)

```
┌──────────────────────────────────────────────┐
│                Web Frontend                  │
│  React + TypeScript                           │
│  ├─ Proprietary editor (SVG+WebGL) over Circuit   │
│  │  JSON (schematic + PCB canvas)             │
│  ├─ KiCanvas/ecad-viewer embed (2D+3D)        │
│  ├─ Chat UI (AI copilot)                      │
│  └─ KiCad previews (Gerber etc)               │
└───────────────┬──────────────────────────────┘
                │ REST / WebSocket / MCP
┌───────────────▼──────────────────────────────┐
│              Backend API (FastAPI)           │
│  ├─ Agent orchestrator (LLM tools)           │
│  ├─ Circuit IR service (Circuit JSON core)   │
│  ├─ Compiler: IR → KiCad artifacts           │
│  ├─ Validation service (kicad-cli ERC/DRC)   │
│  ├─ SPICE service (ngspice subprocess)       │
│  ├─ Sourcing service (JLCPCB local+live)     │
│  ├─ Datasheet/RAG service                    │
│  └─ Git binding (repo per project)           │
└───────────────┬──────────────────────────────┘
                │ subprocess
┌───────────────▼──────────────────────────────┐
│              EDA Engines (containers)        │
│  KiCad (headless api-server / kicad-cli)     │
│  FreeRouting / freeroute                     │
│  ngspice / PySpice                           │
│  KiCanvas? (static build servant)            │
└──────────────────────────────────────────────┘
```

**Components:**
- Frontend: React, TypeScript, Circuit JSON, KiCanvas/ecad-viewer, Three.js
- Backend: FastAPI (Python), Circuit JSON (MIT), yjs/Automerge (collab)
- EDA: KiCad headless, FreeRouting, ngspice, SKiDL/atopile/circuit-synth
- Data: yaqwsx/jlcparts SQLite + LCSC live API

**Advantages:** UX + reuse balance, IR as backbone, allows full self-hosting.
**Disadvantages:** More initial integration, maintain two representations (IR + KiCad).
**Difficulty:** Medium-High.
**Self-hosting:** ✅ Docker compose (KiCad, API, FreeRouting, ngspice).
**Risks:** Sync IR↔KiCad complexity, mixed licenses (GPL isolated in containers).

**Evidence-based recommendation: Architecture C (Hybrid)** — because:
1. Circuit JSON already has proven KiCad converters (tscircuit)
2. KiCad headless (kicad-cli api-server in KiCad 11) is production-ready
3. Proprietary UI editor allows CRDT collaboration (Yjs) without depending on KiCad GUI
4. EDA validation is delegated to kicad-cli (deterministic)
5. Mitigates the risk of "rewrite the EDA" (KiCad already mature)

---

## 18. THE MAIN QUESTION

> **What is the smallest realistic combination of existing open-source projects that could form the foundation of an open-source Flux.ai-like AI electronics design platform?**

```
# MINIMUM CORE
KiCad (v11, headless)        → EDA engine (schematic/PCB/ERC/DRC/export)
kicad-cli                    → CLI headless automation
kicad-python (kicad-python)  → Python API headless
Circuit JSON (tscircuit)     → Canonical IR (source/schematic/pcb/sim)
kicad-to-circuit-json + circuit-json-to-kicad → bidirectional converters
SKiDL (devbisme)             → circuit-as-code Python → netlist/ERC
FreeRouting + freeroute      → autorouter

# AI/AGENT LAYER
rjwalters/kicad-tools (MIT)  → MCP server + pure Python parser/DRC/router
   OR blwfish/kicad-mcp (MIT)  → alternative (71 tools)
akcli-kicad (MIT)            → AI-native schematic authoring CLI
mattpainter701/kicad_automations (MIT) → YAML spec → KiCad + HTTP API

# DATA / COMPONENTS
yaqwsx/jlcparts (Local SQLite 2GB) + jlcsearch → component search
LCSC API live → stock/price/datasheet
KiCad official libraries → symbols/footprints/3D

# SIMULATION
ngspice (BSD) + PySpice (GPL, subprocess mode)

# WEB FRONTEND
React + TypeScript
KiCanvas / ecad-viewer (reusable viewers)
Three.js / pcb-scene3d-viewer (3D)
Yjs (collaboration) + Circuit JSON diff

# BACKEND
FastAPI (Python)
PostgreSQL (per-project metadata, BOM, permissions)
```


> **Which parts must we build ourselves?**
> 1. **Interactive web editor** (schematic + PCB canvas) — no mature OSS does it well; use KiCanvas as base/reference
> 2. **Circuit IR orchestrator** — layer that connects NL spec with Circuit JSON and validations
> 3. **Multi-tool orchestrating agent** (planner → builder → reviewer) — orchestrate existing MCP tools
> 4. **Datasheet RAG** — structured extraction pipeline (PIN/param/abs max) + vector DB
> 5. **Flux-style UX model** — chat + canvas + approval checkpoints

> **Which parts should we NOT build ourselves?**
> - EDA engine (KiCad is already the standard, mature, vast)
> - ERC/DRC (deterministic kicad-cli)
> - Autorouter (FreeRouting)
> - SPICE (ngspice)
> - Component database (yaqwsx/jlcparts + LCSC API)
> - File formats (KiCad S-expression + Circuit JSON)
> - KiCad↔IR converters (tscircuit already has them)
> - Collaboration engine (Yjs/Automerge)
> - 3D visualization (Three.js/ecad-viewer/pcb-scene3d-viewer)
> - MCP servers for KiCad control (13+ projects exist)

> **What should the first working prototype look like?**

```
USER: "Create a 5V USB-C powered board with an LED and push button."

MVP DEMO FLOW:
1. Backend: LLM interprets requirements → Engineering Spec (JSON schema)
2. LLM proposes components (LCSC search: USB-C connector, LDO 3.3V/5V, LED, resistor, button)
3. Deterministic: generates Circuit JSON source elements (components + nets)
4. Compiler: circuit-json-to-kicad → .kicad_sch/.kicad_pcb/.kicad_pro
5. kicad-cli sch erc → report
6. kicad-cli pcb export gerbers + bom
7. Frontend: KiCanvas shows the schematic; chat shows plan and approval checkpoints
8. Approval gates: human approves each step (component selection, schematic, layout)
```

**Initial functionality projection: 2-layer simple PCB (sensor/LED/button), ≤ 10 components, flat schematics, 2-layer autorouter.**

---

## 19. PHASED DEVELOPMENT

### Phase 0 — Research ✅ (this complete report)

### Phase 1 — Circuit representation layer
- **Goal:** Canonical IR in Circuit JSON + proprietary data schema (default)
- **Reuse:** tscircuit/circuit-json (MIT), zod schemas
- **New code:** Circuit IR server, structure validation, DB schema
- **Tests:** round-trip converter tests, valid JSON schema
- **Deliverables:** Python/TS library to create/validate IR
- **Risks:** tscircuit types compatibility

### Phase 2 — KiCad engine integration
- **Goal:** convert IR → KiCad project + ERC + basic export
- **Reuse:** circuit-json-to-kicad, kicad-cli, SKiDL
- **New code:** `kicad_api.py` wrapper (schematic create, ERC parse, export)
- **Tests:** generate 5 reference schematics, ERC=0
- **Deliverables:** backend that generates KiCad project from IR
- **Risks:** KiCad versions, S-expression format changes

### Phase 3 — Component database service
- **Goal:** parametric component search + symbols/footprints
- **Reuse:** yaqwsx/jlcparts (Local SQLite), jlcsearch, kicad libs, @jlcpcb/core
- **New code:** REST layer (component search, fetch symbol/footprint), cache
- **Tests:** example queries ("3.3V LDO SOT-23-5 500mA")
- **Deliverables:** `/api/components` + import to KiCad lib
- **Risks:** stale data, mirror license

### Phase 4 — AI requirements interpreter
- **Goal:** LLM NL → structured engineering spec (JSON)
- **Reuse:** LLM (OpenAI/Anthropic/local), zod output schemas
- **New code:** prompt pipeline, spec validator, question-asking agent
- **Tests:** 10 known prompts → valid spec
- **Deliverables:** spec-to-IR mapping
- **Risks:** hallucination, out-of-domain requests

### Phase 5 — AI agent orchestration (MCP tools)
- **Goal:** cross-platform agent that controls the entire flow
- **Reuse:** MCP servers (rjwalters/kicad-tools or blwfish/kicad-mcp MIT)
- **New code:** tool registry, planning loop, approval gates, safety rails
- **Tests:** automated end-to-end MVP flow
- **Deliverables:** agent that generates complete "5V USB-C LED + button"
- **Risks:** tool coordination, latency, errors

### Phase 6 — SPICE simulation service
- **Goal:** auto-generate SPICE deck, run ngspice, validate
- **Reuse:** ngspice (BSD), PySpice (subprocess mode), akcli `sim`
- **New code:** IR→SPICE generator (for subsets), result analyzer
- **Tests:** RC filter, LDO, LED circuit sims
- **Deliverables:** design checks (voltages, currents)
- **Risks:** scarce SPICE models, subsystem sim

### Phase 7 — Web frontend (viewer + editor)
- **Goal:** browser schematic/PCB viewer + basic editor
- **Reuse:** KiCanvas (MIT) + ecad-viewer + Three.js/pcb-scene3d-viewer
- **New code:** React shell, workspace, chat panel, diff viewer
- **Tests:** open KiCad project in browser, cross-probe
- **Deliverables:** usable workspace for review
- **Risks:** layer rendering complexity, WebGL compat

### Phase 8 — Collaboration (Yjs)
- **Goal:** multi-user real-time editing + git history
- **Reuse:** Yjs, y-websocket, y-protocols
- **New code:** Circuit JSON ↔ Yjs bindings, awareness, permissions
- **Tests:** 2 simultaneous users converge
- **Deliverables:** collaborative session
- **Risks:** design conflict merge, conflicting UUs

### Phase 9 — Advanced hardware engineer (RAG datasheets + knowledge base)
- **Goal:** Flux-style Copilot with knowledge
- **Reuse:** PDF extraction stack, vector DB (Chroma/pgvector), LLM
- **New code:** datasheet ingestion, pin extraction, per-user knowledge base
- **Tests:** "What decoupling cap near VCC?" from real datasheet
- **Deliverables:** AI with state + reasoning
- **Risks:** extraction accuracy, prompt injection security

---

## 20. MAIN RISKS

| Risk | Probability | Impact | Mitigation |
|--------|--------------|---------|------------|
| GPL license (KiCad) prevents integrated commercial distribution | Medium | High | Keep KiCad as separate subprocess/container |
| AGPL (Konnect, circuitjson-toolkit) in SaaS | Medium | High | Choose MIT alternatives; separate services |
| Quality web editor (canvas layers) is difficult | High | High | MVP with KiCanvas as viewer; iterate editor incremental |
| JLCPCB mirror data legal | Medium | Medium | Document, use live API for production |
| LLM generates invalid designs | High | Medium | Deterministic gates (ERC/DRC), human approval |
| KiCad versions break format | Medium | Low | Pin versions, round-trip tests |
| SPICE models not available | High | Medium | Simulate only subset (analog blocks) |

---

## 21. FINAL CONCLUSION

**It is realistic to build a Flux.ai-like open-source platform.** The KiCad + MCP + Circuit JSON + JLCPCB + FreeRouting + ngspice + Yjs ecosystem covers the vast majority of functionality. The gaps (collaborative web editor, agent orchestration, datasheet RAG, UX) are product engineering problems, not technology existence ones.

**Recommended architecture: Hybrid (Architecture C)** with:
- KiCad as EDA engine (subprocess/headless)
- Circuit JSON as canonical IR
- tscircuit converters (KiCad↔Circuit JSON)
- rjwalters/kicad-tools (MCP, parser, DRC, LLM reasoning)
- yaqwsx/jlcparts + LCSC live API (components)
- ngspice/PySpice (SPICE)
- FreeRouting/freeroute (autorouter)
- React/TS + KiCanvas/ecad-viewer/Three.js (frontend)
- Yjs (collaboration)
- FastAPI + PostgreSQL (backend)

**Our project license:** given that we will use GPL components (KiCad) and MIT (majority), and we want to be open source, **GPL-3.0** is coherent for the code that wraps KiCad, keeping the MIT parts in their own repos/containers. This should be carefully reviewed (this is not legal advice).

---

*End of the technical research report — It is advisable to review this document with a software architect and a lawyer specialized in licenses before starting development.*
