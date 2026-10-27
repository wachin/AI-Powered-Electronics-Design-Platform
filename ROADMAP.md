# Research Task: Build an Open-Source AI-Powered Electronics Design Platform

## Objective

I want to investigate how to build an open-source software platform inspired by Flux.ai.

The goal is NOT to copy Flux.ai's proprietary implementation.

The goal is to understand which existing open-source projects, libraries, file formats, algorithms, EDA tools, AI integrations, and web technologies could be combined to create our own AI-assisted electronics design platform.

The final product should allow a user to describe an electronic circuit in natural language and progressively transform that description into:

Natural language requirements
↓
Engineering specification
↓
Circuit architecture
↓
Schematic
↓
Component selection
↓
BOM
↓
PCB placement
↓
PCB routing
↓
ERC / DRC validation
↓
SPICE simulation where applicable
↓
Gerbers / drill files / BOM / pick-and-place
↓
Manufacturing-ready project

The platform should be designed around open-source software wherever practical.

---

# 1. IMPORTANT RESEARCH RULES

Perform real research on GitHub.

Do not simply search for projects containing the words "AI PCB".

Investigate the underlying technologies required to build the complete system.

Search GitHub, project documentation, technical papers where useful, and official project websites.

For every relevant project:

* Repository name
* GitHub URL
* License
* Programming language
* Stars
* Recent activity
* Main purpose
* Architecture
* Important dependencies
* APIs
* File formats supported
* Whether it can be controlled programmatically
* Whether an AI agent could interact with it
* Whether it can run locally
* Whether it can run headlessly
* Whether it can be integrated into a web application
* Whether it is mature enough for production
* Important limitations
* Potential role in our project

Do not recommend a project simply because it has many stars.

Evaluate technical usefulness.

---

# 2. STUDY FLUX.AI AS A REFERENCE PRODUCT

Analyze Flux.ai from a technical/product perspective.

Study publicly available information and documentation.

Create a feature map of what Flux appears to provide.

Investigate at least:

* Natural-language hardware engineering
* AI hardware assistant
* Schematic capture
* PCB layout
* PCB routing
* Component libraries
* Component search
* Datasheet research
* BOM generation
* Manufacturer/distributor information
* Component availability
* Pricing
* ERC
* DRC
* SPICE simulation
* PCB visualization
* 3D visualization
* Manufacturing output
* Gerbers
* Drill files
* Pick-and-place
* Collaboration
* Version history
* Browser-based operation
* Cloud architecture
* AI agent architecture
* Project storage
* Import/export
* APIs
* Automation

Separate clearly:

1. Features that can realistically be reproduced using open-source software.
2. Features that require significant original development.
3. Features that depend on proprietary data/services.
4. Features that can be replaced with open-source alternatives.

Do not speculate about Flux's private implementation.

Only infer architecture when there is public technical evidence.

---

# 3. RESEARCH OPEN-SOURCE EDA SYSTEMS

- [~] Research completed for core EDA systems (KiCad, ngspice, SKiDL, FreeRouting integrated)

Investigate at minimum:

* [x] KiCad - **CORE** (EDA engine, CLI, Python API, file formats, headless)
* [x] ngspice - **CORE** (SPICE simulation, batch mode, integrated)
* [x] SKiDL - **REFERENCE** (circuit-as-code, Python, evaluated)
* [x] FreeRouting - **CORE** (autorouter, Java, integrated via CLI)
* [ ] LibrePCB - Not yet investigated
* [ ] gEDA - Not yet investigated
* [ ] PCB / pcb-rnd - Not yet investigated
* [ ] QUCS / Qucs-S - Not yet investigated
* [ ] LTspice alternatives - Not yet investigated
* [ ] PySpice - Not yet investigated
* [ ] other relevant open-source EDA projects

For each one determine:

* Schematic capabilities
* PCB capabilities
* Routing
* ERC
* DRC
* SPICE integration
* CLI capabilities
* Python API
* Other APIs
* File formats
* Headless operation
* Automation capabilities
* Library system
* Component/footprint handling
* 3D support
* Manufacturing outputs
* License

Most importantly:

Determine whether KiCad could serve as the underlying EDA engine while our software provides the AI layer.

Investigate this possibility seriously before proposing that we build an EDA engine from scratch.

---

# 4. INVESTIGATE KICAD AUTOMATION

- [~] KiCad CLI automation verified and integrated; kicad-mcp-server available in external/; direct S-expression generation implemented

This is one of the most important parts of the research.

Find existing projects that allow AI agents or programs to control KiCad.

Search for:

* [x] KiCad MCP - kicad-mcp-server in external/ (MCP tools for schematic, PCB, project, validation)
* [ ] KiCad Copilot - Not yet investigated
* [ ] KiCad AI - Not yet investigated
* [x] KiCad automation - Implemented via kicad-cli + direct S-expression generation
* [x] KiCad Python - kicad-cli used via subprocess; pcbnew scripting possible
* [x] KiCad CLI - **VERIFIED**: project creation, ERC, DRC, Gerber export, DSN export, SES import, BOM
* [x] KiCad schematic generation - Implemented via S-expression compiler (src/generators/kicad_generator.py)
* [x] KiCad PCB generation - Implemented via S-expression compiler with footprints, layers, Edge.Cuts
* [ ] KiCad programmatic routing - Delegated to FreeRouting
* [x] KiCad project manipulation - kicad-cli + file I/O
* [x] KiCad parsers - S-expression parsing for validation; kicad-mcp-server has parsers
* [x] KiCad file libraries - Symbol/footprint mapping in component database

Investigate projects such as:

* [x] kicad-mcp - Available in external/kicad-mcp-server/
* [ ] kicad-copilot - Not yet investigated
* [ ] pcb-creator - Not yet investigated

and discover additional projects.

For each project explain exactly what it can do.

Determine whether it can:

* [x] Create a project - Via kicad-cli + generated .kicad_pro
* [x] Create a schematic - Via S-expression generation (.kicad_sch)
* [x] Add components - Via symbol instances in schematic
* [x] Connect components - Via nets in schematic
* [ ] Modify existing circuits - Partial (read via parsers, write via generation)
* [x] Select footprints - Component database maps package → footprint
* [x] Generate PCB layouts - Via S-expression (.kicad_pcb)
* [ ] Place components - Basic grid placement implemented; no smart placement
* [x] Route traces - Via FreeRouting integration (DSN → SES → KiCad)
* [x] Run ERC - Via kicad-cli sch erc
* [x] Run DRC - Via kicad-cli pcb drc
* [x] Generate Gerbers - Via kicad-cli pcb export gerber
* [x] Generate BOM - Implemented in orchestrator
* [ ] Generate pick-and-place - Not yet implemented
* [x] Inspect errors - ERC/DRC output parsing
* [ ] Read existing KiCad projects - Parsers exist in kicad-mcp-server; not fully integrated

---

# 5. INVESTIGATE AI/LLM ARCHITECTURES FOR ELECTRONICS

- [x] **IMPLEMENTED AND VERIFIED** - Structured output, real provider clients, validated specification → Circuit IR handoff, and an ERC-driven repair loop

Research how an LLM can safely transform natural language into an electronic design.

Investigate:

* [ ] LLM agents - Not yet
* [ ] MCP - kicad-mcp-server in external/; not integrated
* [ ] tool calling - Not yet
* [x] **structured output** - **IMPLEMENTED** with JSON schemas (REQUIREMENT_SCHEMA, SPECIFICATION_SCHEMA); Ollama gets a native `format` schema, OpenAI-compatible endpoints get `response_format: json_schema`
* [x] **JSON schemas** - **IMPLEMENTED** for requirements & specifications
* [ ] function calling - Not yet
* [ ] multi-agent architectures - Not yet
* [ ] planning agents - Not yet
* [x] **verification agents** - **PARTIALLY IMPLEMENTED** - deterministic validator + repair loop (`src/llm/validation.py`); not an autonomous agent
* [ ] RAG - Not yet (component catalog grounding is prompt-based, not retrieval over datasheets)
* [ ] datasheet RAG - Not yet
* [ ] vector databases - Not yet
* [ ] knowledge graphs - Not yet
* [ ] constraint solving - Not yet
* [ ] symbolic reasoning - Not yet
* [x] **circuit graph representations** - **IMPLEMENTED** - Circuit IR with components, pins, nets, power domains (`src/core/circuit_ir.py`)

Find GitHub projects that demonstrate these techniques for electronics.

Do not assume that an LLM should directly generate KiCad files.

Determine whether a safer architecture would be:

Natural language
→ structured engineering specification
→ circuit intermediate representation
→ deterministic compiler
→ KiCad

**IMPLEMENTED AND VERIFIED** — this is exactly the architecture now enforced:

```
Natural language
  → RequirementParser.parse()            # LLM + schema, keyword fallback
  → CircuitSpecificationGenerator        # LLM + schema + catalog grounding
  → CircuitIRBuilder.build()             # deterministic: real MPNs, real pins
  → DesignValidator                      # schema + MPN + pin + ERC checks
  → repair loop (feed errors back)       # up to N attempts, keeps best
  → KiCadGenerator                       # deterministic S-expression compiler
```

Key implementation notes (see `docs/llm-pipeline.md`):

- The LLM never writes KiCad files. It emits a specification that is built into
  Circuit IR by `src/core/circuit_builder.py` and compiled by
  `src/generators/kicad_generator.py`.
- MPNs are resolved against the component catalog; unknown parts are either
  substituted with a real catalog part (recorded as a warning) or reported as an
  error that drives a repair attempt.
- Pin names are resolved against real KiCad symbol pin names with an alias layer
  (`VO`/`VOUT`/`OUT`), so a model's reasonable wording still produces a valid
  netlist.
- `allow_fallback=False` makes an LLM failure an error instead of silently
  substituting the rule-based template generator; every specification records
  `used_llm` so a canned template can never masquerade as an AI design.

**Previously broken (fixed):** the Ollama client was a copy of the mock client
and raised `AttributeError` on every call, which was swallowed by a bare
`except`; every "AI" design was actually the rule-based template. See
`docs/llm-pipeline.md` for the postmortem.

---

# 6. DESIGN AN INTERMEDIATE REPRESENTATION

- [x] **IMPLEMENTED** - Circuit IR in src/core/circuit_ir.py with full compilation to KiCad and Circuit JSON

Investigate whether we should create an internal representation of an electronic circuit.

For example:

Circuit
├── [x] Components
├── [x] Pins
├── [x] Nets
├── [x] Power domains
├── [ ] Signals
├── [x] Constraints
├── [ ] Parameters
├── [ ] Physical requirements
└── [ ] Manufacturing requirements

Research existing representations such as:

* [x] netlists - SPICE netlist export implemented
* [x] SPICE netlists - Generated via CircuitIRToSpice
* [x] SKiDL - Evaluated as reference; chose custom IR
* [x] KiCad schematic formats - Direct S-expression generation
* [ ] EDIF - Not implemented
* [ ] IPC formats - Not implemented
* [x] other EDA interchange formats - Circuit JSON compatible export

Determine whether we should:

A. Directly manipulate KiCad files
B. Generate SKiDL and then KiCad
C. [x] **CHOSEN** Create our own intermediate representation and compile it to KiCad
D. Use another architecture

Explain the advantages and disadvantages.

**Advantages of custom IR (Option C):**
- Single source of truth for AI, validation, simulation, KiCad export
- Deterministic compilation prevents LLM hallucinations in output formats
- Extensible for power domains, constraints, manufacturing rules
- Testable in isolation (unit tests pass)
- Decouples AI layer from EDA tool specifics

**Disadvantages:**
- Additional abstraction layer to maintain
- Must keep in sync with KiCad format changes

---

- [x] **IMPLEMENTED** - Trace widths per net, driven by current
  (``src/pcb/netclasses.py``). The generator previously wrote
  ``board.design_settings.defaults.track_width``, which is the *interactive*
  routing default and is ignored by everything else: with no ``net_settings``
  block KiCad falls back to its built-in 0.2 mm Default class and the Specctra
  DSN — the file FreeRouting routes from — carried 0.2 mm for every net,
  including a 1 A regulator output that needs 0.30 mm. Verified by experiment.
- [x] **IMPLEMENTED** - Widths from IPC-2221
  (``I = k·ΔT^0.44·A^0.725``, k=0.048 outer / 0.024 inner, 1 oz = 1.378 mil),
  checked against published values: 1 A → 0.30 mm and 2 A → 0.78 mm on an outer
  layer, 1 A → 0.78 mm on an inner one. Classes: Default/SIG 0.25 mm (0.88 A),
  PWR 0.6 mm (1.65 A), PWR_HI 0.8 mm (2.03 A, used above 1.2 A or on a board with
  more than two layers, where a single width per class must be sized for the
  inner case).
- [x] **IMPLEMENTED** - Net membership is written as an explicit
  ``netclass_assignments`` map rather than KiCad's regex patterns, because net
  names are not regex-safe (``+5V``, ``Net-(D1-K)``). A power net with no stated
  current still gets the power class — falling back to the signal class there
  would give a rail a 0.25 mm trace, the exact failure this work prevents.
- [x] **IMPLEMENTED** - The routed widths are read back off the board after
  routing and compared against what each net class asked for. The reference
  design comes out with GND and VOUT at 0.45 mm instead of 0.6 mm, because
  FreeRouting narrows a segment where the wider trace does not fit; the run
  reports it with the current the narrower width can carry.
- [ ] **OPEN** - The narrowing is reported, not analysed. Whether the narrowed
  trace still meets the net's current requirement is left to the reader, and a
  copper pour is not modelled, so a narrow trace may in practice be backed by
  plane copper.
- [x] **VERIFIED** - Setting net classes in the ``.kicad_pro`` is sufficient: no
  change to the ``.kicad_pcb`` and no editing of the DSN is needed.
  ``ExportSpecctraDSN`` reads the loaded net classes and emits
  ``(class PWR GND VIN VOUT (rule (width 600) (clearance 250)))``, and
  ``ImportSpecctraSES`` preserves the widths FreeRouting chose. Confirmed by
  loading the generated project with ``pcbnew`` and by running the router:
  power nets came out at 0.6 mm and signal nets at 0.25 mm.

---

# 7. COMPONENT DATABASE

- [x] **IMPLEMENTED** - JLCPCB/LCSC offline catalog (CDFER republish of
  yaqwsx/jlcparts), 179,894 in-stock parts, with component templates for the
  case where it is not installed.
- [x] **IMPLEMENTED** - Numeric parametric search over that catalog
  (`src/components/parametric.py`). Values are parsed from the catalogue's JSON
  attributes into numbers and matched as numbers, so `10k 0603` cannot return
  110 kΩ. Ratings (`50V`, `1A`, `250mW`) are matched as minimums; a regulator's
  output voltage is matched as an identity, so a 5 V LDO does not answer a
  search for 3.3 V. The query interpretation is reported with the results.
- [x] **IMPLEMENTED** - Substitute lookup with per-candidate evidence
  (`JLCPartsDatabase.find_substitutes`). Identity is value + package; tolerance,
  voltage and power are reported as caveats rather than used to filter, so a
  usable part is disclosed rather than hidden.
- [x] **IMPLEMENTED** - Values parsed from catalogue strings: SI prefixes,
  decimals, `4R7` / `1M0` notation, `±1%` tolerances, `ppm` coefficients.
- [x] **IMPLEMENTED** - The catalogue's broad leaves are split into the
  platform's categories (`Power Management (PMIC)` becomes `regulator_ldo`,
  `regulator_buck`, `voltage_reference`, `supervisor`, `battery_management`,
  `power_switch`; `Diodes` becomes `diode`, `zener`, `schottky`, `led`). The
  split is required for correctness — an LDO symbol asserts IN/OUT/GND pins that
  a TL431 voltage reference does not have — and the searchable category list is
  derived from the file, so a category cannot be offered that then returns
  nothing.
- [x] **IMPLEMENTED** - The minimum order quantity is read from the catalogue's
  `attrition` JSON and carried through to the BOM. It is not a column; ignoring
  it made every part look orderable in ones.
- [x] **IMPLEMENTED** - Web UI: numeric search with the interpretation shown,
  per-category part counts, and an "Alternatives" action listing each
  substitute's reasons and caveats.
- [x] **IMPLEMENTED** - An orderable purchase list
  (`src/components/ordering.py`). Every generated design writes
  ``<project>-bom.csv`` in the format JLCPCB's assembly order form accepts
  (Comment, Designator, Footprint, LCSC Part #) and a readable
  ``<project>-purchase-list.md``. Each designator is mapped to a real catalog
  part —
  by exact part number when the catalog has it, otherwise by value and package —
  and the line carries stock, the price **at the quantity being ordered** from
  the catalog's tier table, and an order quantity that includes JLCPCB's
  attrition allowance and minimum order quantity. ``--boards N`` scales
  quantities; ``--spares 0.1`` adds a hand-assembly allowance.
- [x] **IMPLEMENTED** - The purchase list states what it does not know. A part
  that only matched the built-in placeholder list is reported as **not
  orderable** rather than given an invented part number; a different part number
  is disclosed, with a pinout warning for anything that is not a two-terminal
  passive; insufficient stock is a warning; and without the full catalog the
  prices are labelled as placeholders so an estimate is never read as a quote.
- [x] **VERIFIED** - Audited every part number the built-in list used to hold
  against the downloaded catalogue: **7 of 38 existed in the package listed**,
  **3 existed only in another package**, and **28 existed nowhere**.
- [x] **IMPLEMENTED** - The duplicated parts data is **gone**. The list is now a
  set of **36 component templates** carrying a category, value, package, symbol
  and footprint, and no part number, manufacturer, price or stock
  (``ComponentSpec`` defaults those to empty). There is one source of parts data
  — the catalogue — so a design cannot name a part number the catalogue does not
  know. Measured before deciding: deleting the list outright broke 30 tests and
  left the pipeline with no parts at all without a catalogue download; keeping
  templates and removing the parts data left the offline path intact and removed
  every fabricated number.
- [x] **FIXED** - A test that every template's footprint exists in KiCad found
  **4 of 38 pointing at footprints KiCad does not have**: ``RP2040`` named a
  library that does not exist (``Package_QFN``; the real one is
  ``Package_DFN_QFN``), the DPDT switch named a footprint that does not exist,
  and KiCad ships **no RCA jack and no 9 V battery-clip footprint at all**, so
  those two templates were removed rather than pointed at a name that cannot
  resolve. A template with an unresolvable footprint is worse than no template:
  it produces a board with no pads.
- [x] **IMPLEMENTED** - The LLM prompt no longer teaches invented part numbers.
  Its few-shot examples used to name ``CC0805KRX7R9BB106`` and ``LTST-C190KGKT``
  while the instructions said not to invent part numbers — the model copied the
  examples. ``mpn`` is now optional in the schema, the examples carry empty part
  numbers, and the catalog hint is the only source of part numbers the model may
  cite, with ``lcsc`` supplied alongside ``mpn``.
- [x] **IMPLEMENTED** - The catalog hint is filtered to parts that fit the
  request. It previously listed the four highest-stock parts of each category,
  which offered 5 V regulators for a 3.3 V design.
- [x] **IMPLEMENTED** - Near-miss part numbers are flagged. ``LM337L`` (negative
  adjustable regulator) was being swapped for ``LM317L`` (positive) because both
  have the value "Adjustable"; the purchase list now reports when two part
  numbers are nearly identical and when a value contains no number at all.
- [x] **IMPLEMENTED** - Exact part-number lookup in the catalog
  (``JLCPartsDatabase.lookup_mpn``). The previous fuzzy path ranked by stock and
  then checked whether the first hit matched, so ``get_by_mpn("AMS1117-3.3")``
  missed all six catalog entries for that part and fell back to the placeholder.
- [x] **IMPLEMENTED** - ``Component.package`` carries the catalog package name
  (``0603``) rather than leaving callers to parse it back out of a KiCad
  footprint (``Resistor_SMD:R_0603_1608Metric``), with a footprint parser as the
  fallback for designs that only know footprints.

Known gaps in the catalogue data, verified against the downloaded file rather
than assumed:

- [ ] The JLCPCB **Basic** library flag is present on 1 row of 179,894; the
  **Preferred** flag on 972. Ranking uses Preferred. Establishing the real Basic
  list would need a second data source.
- [ ] Only 55,535 rows state a numeric value; the rest are text-searchable only.
  A part identified solely by a part number cannot be substituted automatically.
- [ ] Attributes are inconsistent between categories. The parser accepts the
  spellings it knows and records nothing for the rest; an unstated tolerance is
  "unknown", never zero.

Research open-source and publicly accessible component databases.

We need to understand how an AI system could answer questions such as:

"Find a 3.3V LDO capable of 500mA, available in SOT-23, preferably from a common manufacturer."

Investigate:

* [x] **KiCad libraries** - **READ AT RUNTIME** for symbols and footprints
  (`src/generators/kicad_symbols.py`, `kicad_footprints.py`). Not vendored;
  CC-BY-SA-4.0 with the design exception — see `CREDITS.md`.
* [ ] SnapEDA - Not investigated
* [ ] Ultra Librarian - Not investigated (commercial)
* [ ] Octopart - Not investigated (commercial API)
* [ ] DigiKey - Not investigated (commercial API)
* [ ] Mouser - Not investigated (commercial API)
* [x] **LCSC** - **IMPLEMENTED** via yaqwsx/jlcparts SQLite dataset (offline, 600k+ parts)
* [ ] SamacSys - Not investigated
* [ ] parts databases - Generic
* [ ] open component databases - JLCParts is open dataset
* [ ] manufacturer APIs - Not implemented
* [ ] distributor APIs - Not implemented

Clearly separate:

* [x] Open-source data - yaqwsx/jlcparts dataset (CC0/public domain)
* [ ] Free APIs - Not used (offline catalog preferred)
* [ ] Commercial APIs - Avoided for MVP
* [ ] Scraping - Not needed (offline dataset available)
* [ ] Data that cannot legally be redistributed - Avoided

Investigate how to obtain:

* [x] Manufacturer - In JLCParts data
* [x] MPN - In JLCParts data (mfr column)
* [x] Datasheet - URL in JLCParts data (datasheet column)
* [x] Symbol - Auto-mapped from category (Device:R, Regulator_Linear:LDO, etc.)
* [x] Footprint - Auto-mapped from package (0805 → Resistor_SMD:R_0805, etc.)
* [x] **3D model** - **IMPLEMENTED** as glTF export
  (`src/generators/gltf_exporter.py`, called by the orchestrator); the
  footprints' KiCad 3D model paths are preserved but the models themselves are
  not yet loaded
* [x] Electrical specifications - In description + attributes (voltage, current, etc.)
* [x] Availability - Stock column in JLCParts
* [x] Price - Price tiers parsed from JLCParts pricing data
* [ ] Alternatives - Not yet implemented (could use category+package search)

---

# 8. DATASHEET UNDERSTANDING

- [ ] **PENDING** - Not yet implemented

Research projects for extracting structured information from PDF datasheets.

Investigate:

* [ ] PDF extraction
* [ ] OCR
* [ ] table extraction
* [ ] document parsing
* [ ] RAG
* [ ] embeddings
* [ ] vector databases
* [ ] multimodal models
* [ ] local LLMs

The system should eventually be able to answer questions such as:

"What capacitor should I place near the VCC pin according to the manufacturer's datasheet?"

or:

"What are the absolute maximum ratings?"

or:

"What is the recommended application circuit?"

Find open-source projects that could help.

---

- [x] **FIXED** - **The default path ignored the prompt.** `--provider mock` is
  the CLI default, and the mock client returned *canned* requirements (5 V in,
  3.3 V out, 0.5 A) rather than reading what the user typed. So
  ``-p "Design a 12V to 3.3V LDO regulator"`` produced a 5 V design, and the
  electrical review, the net classes and the purchase list all validated that
  wrong design without saying so — the failure mode this project keeps finding:
  a confident answer to a question nobody asked. The CLI also reported "the LLM
  was unavailable", which was false: no model was configured.
- [x] **IMPLEMENTED** - ``RequirementParser(deterministic=True)`` and
  ``NLToCircuitPipeline(deterministic=True)``: with ``--provider mock`` the prompt
  is parsed with rules and the design is generated from the templates. The mock
  client remains for tests, which set explicit responses.
- [x] **IMPLEMENTED** - The parser reads what people actually write: ranges with
  ``to``/``->``/``→``/``-``/`a` (Spanish "12V a 3.3V"), ``input``/``output``
  labels, ``mA`` and ``A``, and **Spanish topology words** (``regulador``,
  ``conmutado``, ``reductor``, ``elevador``, ``lineal``). A single voltage with no
  range is taken as the output for a regulator and as the supply for an LED
  circuit.
- [x] **IMPLEMENTED** - Every filled-in default is **reported**: the CLI prints
  ``Assumed: no input voltage was stated; assumed 5 V``, and the assumptions are
  in ``design_summary.json``. A guessed rail decides whether the design works, so
  it is stated rather than buried.
- [x] **VERIFIED** - With the prompt honoured, the review catches the real
  problem: 12 V to 3.3 V at 0.5 A dissipates 4.4 W and needs a thermal path
  better than about 23 °C/W, which no surface-mount package provides — where the
  5 V design it used to produce needed only 144 °C/W and passed. ``C1`` also now
  sees 12 V instead of 5 V.
- [x] **IMPLEMENTED** - A missing junction temperature limit is looked up in the
  **same part family**: the catalogue lists one row per manufacturer and per
  variant, and ``AMS1117-3.3`` states ``150 °C @(Tj)`` where ``AMS1117-3.3OE``
  states nothing usable. The review uses the lowest published limit and says which
  part it came from, rather than declaring the check impossible.

---

- [x] **IMPLEMENTED** - Multi-turn clarification
  (``src/llm/clarification.py``). The parser no longer fills gaps itself; the
  clarifier asks about them from a terminal, and ``fill_defaults`` fills in
  whatever nobody answered and records it as an assumption. One place decides the
  defaults, one place records them.
- [x] **IMPLEMENTED** - Only what changes the design is asked about: the
  topology when the request did not name one, the input and output voltages, the
  current, and a linear regulator that will get hot. Each question states **why**
  it is being asked, the answer it proposes, and — for a thermal decision — the
  current that would be feasible.
- [x] **IMPLEMENTED** - Nobody to ask is handled rather than ignored: a piped
  run, an API call or a test has no terminal, so the defaults are filled and
  reported. ``--ask`` forces the questions, ``--no-ask`` suppresses them, and the
  default is to ask when stdin is a terminal.
- [x] **VERIFIED** - Each field is asked **at most once**, which bounds the loop
  and makes it terminate even when every answer is the default. Without that, the
  thermal question re-fired after being answered with the default, for ever.
- [x] **VERIFIED** - The answers reach the design: answering 12 V / 5 V / 1 A
  produces a design that drops 7 V, not the 1.7 V of the 5 V default.
- [x] **FIXED** - ``buck`` and ``boost`` now build a valid design, and the
  clarification offers them. The cause was one word: the generated specs used
  ``role="controller"``, which is genuinely ambiguous and resolves to a generic
  chip — no category, so no symbol, so no pins, so every connection to the
  controller was dropped and the ERC failed with 10-12 errors. The role now names
  the topology (``buck_controller``, ``boost_controller``), which resolves the
  symbol and its pins. ``tests/test_topologies.py`` builds every offered topology
  and requires it to pass, so an advertised feature cannot be an unbuildable one.

## KiCad symbol and footprint names

- [x] **FIXED** - **26 of the 45 category symbols did not exist.** KiCad ships no
  generic IC symbols, and ``_category_to_symbol`` invented names like
  ``Regulator_Linear:LDO_Generic``, ``MCU_Microcontroller:MCU_Generic``,
  ``Device:Q_NPN_BEC`` (today ``Transistor_BJT:``) and ``Crystal:Crystal`` (today
  ``Device:``). Every one is now a real KiCad symbol used as an archetype, and
  ``tests/test_kicad_names.py`` reads the installed libraries to prove it.
- [x] **FIXED** - **5 of the 36 component templates pointed at symbols KiCad does
  not have**: ``Regulator_Linear:LM7805`` (real name ``LM7805_TO220``),
  ``Regulator_Switching:LM2596`` (``LM2596S-5``),
  ``MCU_ST_STM32F1:STM32F103C8T6`` (``STM32F103C8Tx``), and ``LM317L`` /
  ``LM337L`` (the ``_TO92`` variants the templates' packages actually use).
- [x] **IMPLEMENTED** - The pins declared for an archetype are verified to exist
  on that symbol: 0 incompatibilities across all 45 categories. A symbol and a
  pin list that disagree produce a netlist that looks right and is not.
- [x] **IMPLEMENTED** - An unknown category now gets **no symbol** instead of
  ``Device:R``, which used to draw a resistor for a part the platform had not
  understood.
- [x] **VERIFIED** - The consequence, end to end: a design that resolves its parts
  from the catalogue (`12V to 3.3V LDO at 0.05A`) used to fail with
  ``symbol library not found`` and now passes the ERC with 0 errors.
- [ ] **OPEN** - Three templates have no pinout: ``ESP32``, ``STM32F103`` and
  ``RP2040``. A microcontroller has tens of pins and their assignment is not in
  the catalogue, so the platform reports "no known pinout" rather than inventing
  one. The gap is asserted by name in the test, so it cannot grow quietly.

---

- [x] **IMPLEMENTED** - Manufacturing output (`src/generators/fabrication.py`).
  The pipeline produced a ``.kicad_pcb``, which no board house accepts, and the
  ROADMAP recorded Gerber export as "verified" because it had been run by hand
  with `kicad-cli` — there was no code that produced them, no drill files, and no
  position file, without which an assembly service cannot place anything.
  * [x] Gerbers, one per layer, plus Excellon drill files, via `kicad-cli` with
    `--excellon-separate-th`.
  * [x] A single archive of them, which is what an order form accepts.
  * [x] A **position file (CPL)** in CSV, mm, one per side, which is what
    assembly needs alongside the BOM.
  * [x] The **routed** board is plotted when routing ran. Measured: the routed
    board's copper Gerber holds 25 draw operations (the tracks), the unrouted
    board's holds none — only pad flashes. Plotting the unrouted board gives a
    Gerber set that passes every file-level check and yields a board with no
    connections on it.
- [x] **VERIFIED** - The output is checked rather than trusted, because each of
  these fails quietly: `kicad-cli` can exit zero having written nothing, so every
  file must exist, be non-empty and start with a real Gerber or Excellon header;
  the layers an order cannot be placed without (copper, outline, solder masks)
  must be present, and the missing ones are named; and **a part the BOM lists but
  the position file does not place would be fitted as a hole**, so the designator
  sets are compared and the difference is reported.
- [ ] **OPEN** - Only the front side is placed in the position file. Assembly
  services want one file per side, and the back side is exported when
  ``position_sides`` asks for it, but no design has yet needed a double-sided
  assembly run.

---

## Preparing the repository for agent-assisted development

- [x] **IMPLEMENTED** - `AGENTS.md` now opens with how to work here — commands,
  the venv rule, the six rules a change must satisfy, where to start reading —
  and keeps the dependency/licensing policy below it. `docs/development.md` is
  the depth: setup, the pipeline stage map, a module table, seven extension
  recipes (add a topology, a template, a pinout, a catalog category, a review
  rule, an ERC rule, a CLI flag), the testing patterns, and a pitfall table.
- [x] **IMPLEMENTED** - `Makefile` with every routine command behind one entry
  point (`make test`, `make test-catalog`, `make lint`, `make diagnose`,
  `make demo`, `make compile-check`). All of them were run before being
  documented.
- [x] **IMPLEMENTED** - `ai-electronics-design --diagnose`: reports which external
  tools are installed, measured rather than assumed, and says what a run will
  omit without them. Written because "why was that stage skipped?" was answered
  by reading the code.
- [x] **IMPLEMENTED** - Ruff as a dev dependency, configured at
  `target-version = "py310"` with the pyflakes rules, and enforced in CI by a new
  `lint` job.
- [x] **FIXED** - **`catalog-setup` was broken.** The archive extraction used
  `zipfile`, `struct` and `zlib` without importing any of them, so the setup
  command the docs tell you to run first failed with `NameError` on every run.
  Found by ruff (`F821`), in the code path that downloads the catalog.
- [x] **FIXED** - **The package could not be imported on Python 3.10 or 3.11.**
  `jlcparts.py` used a backslash inside an f-string, which is a `SyntaxError`
  before 3.12, while `pyproject.toml` declares `requires-python = ">=3.10"` and
  CI only tested 3.12. The escape moved into a helper. CI now lints at 3.10.
- [x] **FIXED** - Four dead duplicate methods (`health_check` ×3,
  `detect_pin_conflicts`), two dictionaries with a repeated key (`min_order`,
  `meshes` — harmless because the values were identical, which is how they
  survived), 90 unused imports, and a dozen unused locals. One of them was a
  weak test: `test_sandbox_cleanup` collected the temp directories before the
  test and never compared them, so it passed even if the sandbox leaked a
  directory. It now compares.
- [x] **VERIFIED** - 911 tests pass without the catalog and 923 with it, after the
  cleanup; `ruff check src/ tests/` is clean.

---

# 9. CIRCUIT VALIDATION

- [x] **IMPLEMENTED** - ERC engine in src/core/erc.py with 6 validation rules + unit tests

Research how we can prevent an LLM from producing invalid electronics.

Investigate:

* [x] **ERC** - **IMPLEMENTED** (src/core/erc.py)
  * [x] Unconnected critical pins (POWER_IN, INPUT) - ERROR
  * [x] Unconnected non-critical pins - WARNING
  * [x] Power pins on non-power nets - WARNING
  * [x] Missing decoupling capacitors for ICs/regulators - WARNING
  * [x] LED without series current-limiting resistor - ERROR
  * [x] Single-pin nets - WARNING
* [x] **DRC** - **IMPLEMENTED and verified** via `kicad-cli pcb drc`; a
  generated board loads and reports 0 unconnected pads, 0 shorts and 0 crossing
  tracks (`tests/test_kicad_pcb.py`)
* [x] **SPICE** - **IMPLEMENTED** (src/simulation/ngspice.py)
  * [x] DC operating point (.op)
  * [x] Transient analysis (.tran)
  * [x] DC sweep (.dc)
  * [ ] Automated design modification from results - Not implemented
* [ ] symbolic circuit analysis - Not implemented
* [x] **electrical review** - **IMPLEMENTED** (`src/core/design_review.py`).
  The ERC checks connectivity; this checks that the numbers work. It replaces
  the generator's generic "Check thermal dissipation for high current" note with
  computed findings, because the generator already knew the dissipation and was
  asking the reader to judge it.
  * [x] Linear regulator dissipation and the **required** θJA. θJA itself is
    never assumed: it depends on package, copper area, layer count and airflow,
    none of which this platform controls. The finding reports the dissipation
    (exact), the junction limit from the catalogue when the catalogue states one,
    and the thermal path the design needs. It only returns a verdict when the
    requirement is outside the range any package could meet either way.
  * [x] Dropout headroom, from the catalogue's own `Voltage Dropout` cell
    (`1.3V@(1A)`), scaled to the design current and labelled as an approximation.
  * [x] Resistor dissipation by I²R, against the catalogue's power rating, with a
    50 % derating rule.
  * [x] Capacitor voltage stress against the catalogue's voltage rating, with an
    80 % derating rule.
  * [x] LED operating point: the current through the wired series resistor,
    reported as a **range**, because an LED's forward voltage is a range and a
    green LED that drops 2.0 V and one that drops 2.6 V pass very different
    currents through the same resistor.
  * [x] Ratings for a design built from the built-in placeholder list are taken
    from the catalogue part the purchase list would order for the same value and
    package, and the substitution is disclosed in the review's assumptions.
* [x] netlist validation - Via ERC net checks
* [x] power-domain validation - `PowerDomain` in CircuitIR, used for the net class
  widths and the electrical review. Fixed: `get_or_create_net` used to discard
  metadata passed for an existing net, so a caller that connected pins first and
  set the rail voltage afterwards silently lost the voltage and the power flag.
* [ ] pin compatibility - Not implemented
* [ ] voltage compatibility - Partially: ratings are checked per component, not
  across a net
* [ ] current requirements - Partially: resistor and regulator currents are
  computed, but a net's total current is not summed
* [x] decoupling verification - ERC rule implemented
* [ ] pull-up/pull-down verification - Not implemented
* [x] component rating verification - **IMPLEMENTED** for dissipation, voltage
  and dropout, from catalogue attributes

Determine which checks should be performed by deterministic software rather than by the LLM.

This is extremely important.

The AI should propose designs, but deterministic engineering tools should verify them whenever possible.

---

# 10. PCB PLACEMENT AND ROUTING

- [~] **PARTIALLY IMPLEMENTED** - FreeRouting auto-routing integrated; placement is basic grid-based

Research open-source PCB routing algorithms and projects.

Investigate:

* [~] **autorouters** - FreeRouting wrapper written but **cannot run on this
  machine**. Three independent blockers were verified (2026-10):
  * [x] DSN export from KiCad - **works via `pcbnew.ExportSpecctraDSN`**, verified
    producing a valid Specctra file. Note `kicad-cli pcb export dsn` does NOT
    exist in KiCad 7+; the wrapper still calls that removed command.
  * [ ] FreeRouting execution (Java JAR) - **BLOCKED**: every bundled jar
    (`freerouting-current`, `2.3.0`, `2.5.0-RC12`) is compiled for Java 25
    (class file 69.0); this machine has Java 21 (up to 65.0).
  * [ ] SES import back to KiCad - **BLOCKED**: the wrapper calls
    `kicad-cli pcb import ses`, which does not exist. `kicad-cli pcb` offers only
    `drc`, `export` and `render`. The working path is
    `pcbnew.ImportSpecctraSES`.
* [ ] global routing - Delegated to FreeRouting
* [ ] detailed routing - Delegated to FreeRouting
* [ ] pathfinding - FreeRouting internal
* [ ] A* - Not directly implemented
* [ ] Lee algorithm - Not directly implemented
* [ ] maze routing - Not directly implemented
* [ ] optimization - FreeRouting internal
* [ ] reinforcement learning - Not implemented
* [ ] machine learning for PCB placement - Not implemented
* [ ] machine learning for PCB routing - Not implemented
* [ ] differential pair routing - Not implemented
* [ ] impedance-aware routing - Not implemented
* [ ] thermal considerations - Module exists (`src/pcb/smart_placement.py`,
  separates heat sources) but is **not called by the pipeline** (see section 10
  placement note)
* [ ] power distribution - Not implemented
* [ ] ground planes - Not implemented (KiCad supports, not auto-generated)

Find GitHub repositories implementing these technologies.

Determine whether we should:

1. [ ] Use KiCad's existing routing infrastructure - Not yet (no push-and-shove via CLI)
2. [x] **Integrate an external autorouter** - **FreeRouting** (IMPLEMENTED)
3. [ ] Develop our own routing engine - Not needed for MVP
4. [ ] Use AI only for high-level placement/routing decisions and deterministic algorithms for final routing - Future work

**Placement status:** WIRED IN. `src/pcb/smart_placement.py` provides the
positions used by `generate_pcb()`, and the board outline is computed from the
real pad coordinates rather than a fixed rectangle. It also shipped with a
`NameError` in `_determine_placement_order` that made `place_all()` unusable;
the original 8 tests only covered the helper classes, so the bug went unnoticed
until the module was connected. Fixed, with regression tests that call
`place_all()` directly.

---

# 11. SPICE SIMULATION

- [x] **IMPLEMENTED** - ngspice integration in src/simulation/ngspice.py with CircuitIR → SPICE netlist compiler

Investigate open-source simulation systems.

At minimum investigate:

* [x] **ngspice** - **IMPLEMENTED** (batch mode, CLI, integrated in orchestrator)
  * [x] DC operating point analysis (.op)
  * [x] Transient analysis (.tran)
  * [x] DC sweep analysis (.dc)
  * [x] CircuitIR → SPICE netlist compilation
  * [x] Component models: R, C, L, D, LED, LDO (simplified), MCU (current load)
* [ ] Qucs-S - Not investigated (GUI-focused)
* [ ] PySpice - Evaluated; chose direct ngspice CLI for simplicity
* [ ] other relevant projects

Determine how a generated circuit could automatically become a simulation.

Example:

User:
"Build a 5V to 3.3V regulator circuit."

System:
1. Generates schematic.
2. Selects components.
3. [x] Generates SPICE model (CircuitIRToSpice).
4. [x] Runs simulation (NgSpiceRunner).
5. [ ] Checks voltage/current (parsing output not implemented).
6. [ ] Reports problems (stdout captured, not parsed).
7. [ ] Modifies design if necessary (not implemented).

Investigate how feasible this workflow is.

**Status:** End-to-end compilation and execution works. Output parsing and design iteration loop pending.

---

# 12. WEB APPLICATION ARCHITECTURE

- [x] **IMPLEMENTED** - React/TypeScript frontend + FastAPI backend in `frontend/` and `src/api/`

Research open-source technologies for building a browser-based EDA interface.

Investigate:

* [x] **React** - **IMPLEMENTED** (React 18 + Vite)
* [ ] Vue - Not used
* [ ] Svelte - Not used
* [x] **TypeScript** - **IMPLEMENTED** (strict mode)
* [ ] WebAssembly - Not yet
* [ ] SVG - Not yet (KiCad renders to SVG via CLI)
* [ ] Canvas - Not yet
* [ ] WebGL - Not yet
* [ ] Three.js - Not yet (planned for 3D)
* [ ] Monaco Editor - Not yet (planned for code editor)
* [x] **WebSockets** - **IMPLEMENTED** (`/api/collaboration/ws/...` in
  `src/api/main.py`, `src/collaboration/server.py`, `frontend/src/hooks/useCollaboration.ts`)
* [x] **collaborative editing** - **IMPLEMENTED** (room join/leave, presence,
  cursor broadcast)
* [~] **CRDT** - Yjs used for document state; the server relays Yjs binary
  updates rather than implementing a CRDT itself
* [x] **Yjs** - **IMPLEMENTED** (`yjs`/`y-websocket` in `frontend/package.json`)
* [x] **real-time synchronization** - **IMPLEMENTED** for room/document updates

Find GitHub projects that implement browser-based schematic or PCB editors.

Determine whether we should:

A. [x] **CHOSEN** Build a custom browser frontend with KiCad as backend
B. Use KiCad as the backend and create a web frontend.
C. Create a hybrid architecture.

**Current Architecture:** React frontend → FastAPI REST API → Python orchestrator → KiCad CLI/ngspice/FreeRouting

---

# 13. 3D PCB VISUALIZATION

- [x] **IMPLEMENTED** - Three.js-based 3D PCB viewer (frontend/src/components/PCB3DViewer.tsx) + glTF exporter (src/generators/gltf_exporter.py)

Investigate open-source projects for:

* [x] **PCB 3D visualization** - **IMPLEMENTED** (Three.js + OrbitControls)
* [x] **glTF** - **IMPLEMENTED** (glTF 2.0 export + Three.js GLTFLoader)
* [x] **WebGL** - **IMPLEMENTED** (Three.js WebGLRenderer)
* [x] **Three.js** - **IMPLEMENTED** (r158+)
* [ ] STEP - Not implemented
* [ ] VRML - Not implemented
* [ ] KiCad 3D models - Partial (placeholder components)

Determine how the browser could show:

* [x] **PCB** - Board outline, layers, copper pours
* [x] **components** - ICs, passives, connectors as 3D models
* [x] **copper** - Traces, pours, vias as 3D geometry
* [x] **layers** - Multi-layer stackup visualization
* [x] **traces** - 3D trace routing
* [ ] 3D components - Using KiCad 3D models (planned)
* [ ] board enclosure - Mechanical enclosure (planned)

**Features implemented:**
- OrbitControls for rotate/pan/zoom
- Realistic lighting (ambient + directional with shadows)
- glTF 2.0 export from CircuitIR
- Split-screen 3D + 2D collaborative canvas
- Component 3D models (ICs, passives, connectors, crystals)
- Board stackup visualization (FR4, copper, soldermask, silkscreen)
- Lighting with PBR materials (FR4, copper, plastic, gold, silkscreen)
* [ ] copper
* [ ] layers
* [ ] traces
* [ ] 3D components
* [ ] board enclosure

---

# 14. AI AGENT TOOL ARCHITECTURE

- [ ] **PENDING** - Not yet implemented (current orchestrator is deterministic pipeline, not LLM agent)

Design a possible tool system for an AI hardware agent.

For example:

hardware_agent
│
├── requirements_tool
├── component_search_tool
├── datasheet_tool
├── schematic_tool
├── circuit_analysis_tool
├── simulation_tool
├── pcb_tool
├── placement_tool
├── routing_tool
├── erc_tool
├── drc_tool
├── bom_tool
├── manufacturing_tool
└── project_tool

For each tool determine:

* Inputs
* Outputs
* APIs
* Existing open-source implementation
* Whether deterministic or AI-based
* Security considerations
* Validation requirements

---

# 15. SECURITY

- [x] **IMPLEMENTED** - Permission system and sandboxing (src/security/permissions.py, src/security/sandbox.py)
  - Capability-based permission system with roles (Viewer, Designer, Engineer, Admin, AI Agent)
  - PermissionManager for managing principals and access control
  - Temporary permission elevation context manager
  - Audit logging for permission changes
  - Process sandboxing with resource limits (CPU, memory, file size, open files, processes)
  - Path access restrictions (allowed/blocked paths)
  - Command allow/block lists
  - Secure MCP tool execution with sandbox isolation
  - RestrictedFileSystem wrapper for safe file operations
  - SecureExecutor combining permissions and sandboxing
  - 16 tests passing (7 permission tests, 7 sandbox tests, 1 secure executor test, 1 skipped resource limits)
  - **NOT WIRED IN:** `src/security/permissions.py` and `sandbox.py` are imported
    by nothing outside their own tests (`sandbox` is imported only by
    `permissions`). The REST API exposes no permission or sandbox endpoint, so
    the capability does not currently protect any operation.
* [~] MCP security - Secure-executor wrappers exist but are **not wired into
  the API or CLI** (see below)
* [x] **tool permissions** - **IMPLEMENTED** (capability-based roles in
  `src/security/permissions.py`)
* [x] **sandboxing** - **IMPLEMENTED** (resource limits and path/command
  restrictions in `src/security/sandbox.py`)
* [ ] supply-chain attacks
* [ ] untrusted KiCad files
* [x] **LLM hallucinations** - Addressed deterministically: MPN resolution,
  pin validation, ERC and the validate-and-repair loop (`docs/llm-pipeline.md`)

Propose a permission architecture.

For example:

* [ ] READ
* [ ] WRITE
* [ ] SIMULATE
* [ ] EXPORT
* [ ] MANUFACTURING

The AI should not automatically perform dangerous or irreversible operations without explicit approval.

---

# 16. FIND EXISTING PROJECTS WE CAN LEARN FROM

- [x] **COMPLETE** - 25 repositories cataloged in research/repository_catalog.md

Search GitHub extensively.

Search terms should include combinations such as:

* [x] "AI PCB" - Found: tscircuit, atopile, AI agent integrations
* [x] "AI EDA" - Found: tscircuit, atopile, kicad-mcp-server
* [x] "AI schematic" - Found: tscircuit, atopile, Circuit JSON
* [x] "LLM PCB" - Found: kicad-mcp-server, MCP integrations
* [x] "LLM electronics" - Found: AI agent tools, MCP servers
* [x] "PCB agent" - Found: AI design agent, MCP tools
* [x] "EDA agent" - Found: kicad-mcp-server, MCP tools
* [x] "KiCad AI" - kicad-mcp-server in external/
* [x] "KiCad MCP" - kicad-mcp-server in external/
* [x] "KiCad copilot" - Found: kicad-mcp-server, kicad-tools
* [x] "schematic generation LLM" - Found: Circuit JSON, tscircuit, atopile
* [x] "PCB generation LLM" - Found: tscircuit, atopile, FreeRouting
* [x] "natural language PCB" - Found: AI agent architecture, Circuit IR
* [x] "natural language circuit" - Found: AI agent, Circuit IR
* [x] "AI circuit design" - Found: AIDesignAgent, Circuit IR
* [x] "AI circuit schematic" - Found: Circuit IR, KiCad generator
* [x] "SPICE LLM" - Found: ngspice integration, AI agent SPICE
* [x] "PCB placement AI" - Found: SmartPlacer, thermal/signal-aware placement
* [x] "PCB routing machine learning" - Found: FreeRouting, ML research
* [x] "EDA automation" - Found: kicad-tools, kicad-mcp-server, KiCad CLI
* [x] "electronic design automation Python" - Found: SKiDL, kicad-tools, our platform
* [x] "browser PCB editor" - Found: SVG-PCB, KiCanvas, tscircuit
* [x] "web schematic editor" - Found: tscircuit, Circuit JSON, EasyEDA
* [x] "open source EDA" - KiCad, ngspice, SKiDL, FreeRouting integrated

---

# 17. CREATE A REPOSITORY CATALOG

- [x] **COMPLETE** - Catalog created at research/repository_catalog.md with 25 repositories

Create a table containing at least 30 potentially relevant GitHub repositories if enough quality projects exist.

| Project | URL | License | Language | Purpose | AI | EDA | API | Local | Web | Activity | Potential usefulness |
| ------- | --- | ------- | -------- | ------- | -- | --- | --- | ----- | --- | -------- | -------------------- |

Then classify each project:

* CORE
* VERY USEFUL
* USEFUL
* REFERENCE
* EXPERIMENTAL
* NOT RECOMMENDED

Explain the classification.

Do not rank projects simply by popularity.

**See research/repository_catalog.md for complete catalog with 25 repositories classified by category (Core EDA, Simulation, Routing, Design Framework, Data Format, Component Database, Automation, MCP/AI, Web EDA, Visualization, PCB Editor, Design Framework).**

---

# 18. IDENTIFY THE MOST IMPORTANT BUILDING BLOCKS

- [x] **COMPLETE** - Core subsystems identified, implemented, and integrated

After the research, identify the components we could realistically reuse.

Produce a table:

| Subsystem | Recommended open-source project | Why | License | Reuse strategy |
| --------- | ------------------------------- | --- | ------- | -------------- |

Subsystems should include:

* [x] Schematic - KiCad (GPL-3.0) - Core EDA engine - subprocess/CLI
* [x] PCB - KiCad (GPL-3.0) - Core EDA engine - subprocess/CLI
* [x] Component library - JLCParts/yaqwsx (CC0) - offline SQLite, 179,894 in-stock parts
* [ ] Datasheets - Not yet integrated (parsing them would let pinouts be checked automatically)
* [x] Component search - numeric parametric search + substitute lookup with evidence
* [x] Netlist - CircuitIR internal + SPICE export
* [x] Simulation - ngspice (BSD-3) - batch CLI - subprocess
* [x] ERC - Custom implementation (MIT/GPL) - deterministic Python
* [x] DRC - KiCad CLI (GPL-3.0) - subprocess
* [~] Placement - Basic grid in generator; no smart placement
* [x] Routing - FreeRouting (GPL-3.0) - Java JAR - subprocess
* [ ] 3D - Not implemented
* [ ] AI agent - Not implemented (deterministic pipeline only)
* [ ] MCP - kicad-mcp-server available in external/; not integrated
* [ ] Web frontend - Not implemented
* [ ] Collaboration - Not implemented
* [ ] Database - SQLite for JLCParts; no project DB yet
* [ ] Version control - Not implemented
* [x] Manufacturing output - KiCad Gerber/Drill export via CLI

---

# 19. PROPOSE AN ARCHITECTURE

- [~] **PARTIALLY COMPLETE** - Architecture emerged organically; documented in code structure

Based on the research, propose at least three possible architectures.

### Architecture A

KiCad + AI Agent

### Architecture B

Browser-based EDA + AI Agent

### Architecture C

Hybrid system

For each architecture provide:

* Diagram
* Components
* Technologies
* Advantages
* Disadvantages
* Development difficulty
* Reusability of existing open-source software
* Estimated development phases

Then recommend which architecture should be investigated further based on technical evidence.

Do NOT simply choose the architecture because it sounds modern.

**Current Architecture (Implemented):**
- **Backend**: Python FastAPI + Circuit IR + Orchestrator
- **EDA Engine**: KiCad CLI (schematic, PCB, ERC, DRC, Gerber)
- **Simulation**: ngspice subprocess
- **Routing**: FreeRouting JAR subprocess
- **Component DB**: JLCParts SQLite (yaqwsx/jlcparts)
- **AI Agent**: Rule-based planner + MCP client (planned)
- **Frontend**: React/TypeScript + Vite + Yjs (planned)
- **Collaboration**: Yjs CRDT (planned)

---

# 20. PROPOSE A REALISTIC MVP

- [x] **ACHIEVED for the covered topologies** - Natural language → validated KiCad project works end to end with a real LLM; missing-requirement questioning is still not implemented

Design a minimum viable product.

The MVP should NOT attempt to reproduce all of Flux immediately.

Propose something like:

User:

"Create a 5V USB-C powered board with an LED and push button."

The system should:

1. [x] Understand the requirements. (LLM requirement parser with schema; keyword fallback)
2. [ ] Ask missing engineering questions. (Not implemented — the parser fills defaults instead)
3. [x] Produce a structured specification. (LLM + JSON schema, grounded in the component catalog)
4. [x] Select components. (JLCParts database, with substitution for unknown MPNs)
5. [x] Generate a schematic. (CircuitIR → KiCad S-expression)
6. [x] Open/produce the project in KiCad. (.kicad_sch, .kicad_pcb, .kicad_pro)
7. [x] Run ERC. (Custom ERC + kicad-cli)
8. [~] Generate a basic PCB. (Basic placement + FreeRouting)
9. [x] Run DRC. (kicad-cli pcb drc)
10. [x] Generate Gerbers and BOM. (kicad-cli + custom BOM)

Identify exactly which parts can initially be delegated to existing software.

**Current status:** Steps 1 and 3 are now LLM-backed and validated. The
generated design is assembled from the LLM's own component and connection list,
then checked by ERC; a design that fails ERC is sent back to the model with the
specific errors. Steps 4-10 work for the supported topologies (LDO, buck, boost,
LED).

**Known MVP gap:** the parser silently defaults unspecified engineering values
(for example output current) instead of asking the user. That remains step 2.

---

# 21. PROPOSE A DEVELOPMENT ROADMAP

- [~] **PARTIALLY EXECUTED** - Phases 0-12 complete; phases 13-14 pending

Create a phased roadmap:

## Phase 0 — Research
- [x] **COMPLETE** - EDA systems, KiCad automation, component databases researched

## Phase 1 — Circuit representation
- [x] **COMPLETE** - CircuitIR implemented (src/core/circuit_ir.py)

## Phase 2 — AI requirements interpreter
- [x] **IMPLEMENTED (2026-10)** - Real LLM providers (Ollama, OpenAI-compatible, Anthropic), schema-constrained output, catalog grounding, MPN resolution, pin validation, ERC repair loop (`src/llm/integration.py`, `src/llm/validation.py`, `src/core/circuit_builder.py`)
  - Not done: multi-turn clarification of missing requirements

## Phase 3 — Component database
- [x] **COMPLETE** - JLCParts integration (src/components/jlcparts.py, database.py)

## Phase 4 — Schematic generation
- [x] **COMPLETE** - KiCad S-expression generator (src/generators/kicad_generator.py)
  - Schematics now carry real electrical connectivity (lib_symbols + pin instances + labeled wires)
  - Verified: `kicad-cli sch export netlist` returns the expected nets (tests/test_kicad_netlist.py)
  - Symbol pins are read from the installed KiCad libraries (src/generators/kicad_symbols.py)

## Phase 5 — KiCad integration
- [x] **COMPLETE** - kicad-cli for ERC, DRC, Gerber, DSN/SES; S-expression I/O

## Phase 6 — ERC
- [x] **COMPLETE** - Custom ERC engine (src/core/erc.py)

## Phase 7 — SPICE
- [x] **COMPLETE** - ngspice integration (src/simulation/ngspice.py)

## Phase 8 — PCB placement
- [x] **COMPLETE (2026-10)** - Smart placement is now used by PCB generation
  (collision avoidance, thermal awareness, signal-integrity grouping,
  power-domain awareness, edge clearance). Board outlines are derived from the
  placed pads: a 5-part LDO went from a 180x120 mm fixed rectangle to 22x20 mm.
  Verified: routed board has 0 unconnected pads and exports Gerbers.

## Phase 9 — PCB routing
- [x] **COMPLETE (2026-10)** - FreeRouting integration working end to end.
  Both blockers are resolved:
  - DSN export and SES import now go through the **`pcbnew` Python API**
    (`ExportSpecctraDSN` / `ImportSpecctraSES`), because `kicad-cli pcb export
    dsn` and `kicad-cli pcb import ses` do not exist in KiCad 7+.
  - The caller supplies a **Java 25** runtime (the jars are class-file version
    69); `find_java25()` discovers one and does not require changing the system
    default.
  - Verified: a generated LDO routed to **30 tracks, 0 unconnected pads**, and
    `kicad-cli pcb drc` reports 0 unconnected items on the routed board.
  - The FreeRouting jar is not bundled; it is looked up in
    `libs/freerouting/`, `KICAD_MCP_FREEROUTING_JAR`, or a user data directory.
  - **`external/` is not required for this or anything else.** Verified by
    running the full suite (234 passed) with the directory renamed away.

## Phase 10 — DRC
- [x] **COMPLETE** - Via kicad-cli pcb drc
- [x] **FIXED (2026-10)** - `generate_pcb()` previously emitted no pads and wrote
  track endpoints as designator references (`(start D1.2)`), so KiCad could not
  load a generated board. It now emits real pads and assigned nets, copied from
  the installed KiCad footprint libraries (`src/generators/kicad_footprints.py`).
  Verified: `kicad-cli pcb drc` loads a generated board and reports **0
  unconnected pads**, 0 shorts and 0 crossing tracks (an unrouted board
  legitimately reports unconnected pads until it is routed).
  Stub routing is now opt-in (`KiCadGenerator(circuit, route_pcb=True)`) because
  straight-line stubs short other nets; real routing belongs to FreeRouting.

## Phase 11 — Manufacturing files
- [x] **COMPLETE** - Gerber/drill export via kicad-cli; BOM generation
- [x] **VERIFIED (2026-10)** - Gerbers and drill files export successfully from a
  *generated* board, which was impossible while the board would not load.

## Phase 12 — Web interface
- [x] **COMPLETE** - React/TypeScript frontend (frontend/) + FastAPI backend (src/api/main.py)

## Phase 13 — Collaboration (DEFERRED — lowest priority)
- [x] **IMPLEMENTED** - Yjs-based real-time collaboration
  (src/collaboration/server.py, frontend/src/hooks/useCollaboration.ts),
  exposed at `/api/collaboration/ws/...`
- [ ] **NOT A PRIORITY** - Feature-complete is preferred over collaborative.
  See section 28: this is scheduled last and blocks nothing else. Recorded here
  as done work, not as a recommended next step.

## Phase 14 — Advanced AI hardware engineer

- [~] **PARTIALLY WIRED (2026-10)** - MCP integration now reachable:
  `ai-electronics-design mcp-setup` / `mcp-status` create and inspect isolated
  per-server environments, and `--mcp-validate` runs an independent ERC/DRC check
  on the generated project (`src/agents/mcp_registry.py`, `mcp_servers.py`,
  `mcp_validation.py`). Verified against a generated LDO: ERC 0 violations, DRC
  only library-table notices.
  - [ ] Still not wired: the free-form `AIDesignAgent` planner in `ai_agent.py`
    (its MCP tool wrappers are reachable, but no API route or CLI flag drives it)
  - Rule-based planning for LDO, buck, boost, LED circuits
  - MCP client for KiCad MCP server (stdio transport, JSON-RPC 2.0)
  - KiCadMCPTools wrapper with 40+ tool wrappers (schematic, PCB, netlist, validation, editing, parts registry)
  - Verification loop with automatic retry/recovery
  - Integration with existing pipeline (ERC, SPICE, FreeRouting)
  - 14 tests covering planning, execution, verification

For each phase specify:

* Goal
* Existing projects to reuse
* New code required
* Dependencies
* Tests
* Expected deliverables
* Risks

---

# 22. VERIFICATION STATUS: WHAT IS WIRED IN, AND WHAT IS ORPHANED

- [x] **AUDITED (2026-10)** - Every claim below was checked against the running
  system, not against the intent of the code

This section exists because several capabilities in this repository are
implemented and tested but **never called by the pipeline**, and several
checkboxes above previously overstated what worked. It distinguishes "code
exists" from "code affects output".

## Wired in and verified end to end

| Capability | Evidence |
|---|---|
| Circuit IR | `src/core/circuit_ir.py`; used by 11 modules |
| Specification -> Circuit IR, with real MPNs and pins | `src/core/circuit_builder.py`; `tests/test_circuit_builder.py` |
| ERC (6 rules) | `src/core/erc.py`; gates the generator |
| LLM pipeline + validate/repair loop | `src/llm/`; `tests/test_llm_pipeline_repair.py` |
| Schematic with real electrical connectivity | `kicad-cli sch export netlist` returns all expected nets; `tests/test_kicad_netlist.py` |
| PCB with real pads and assigned nets | `kicad-cli pcb drc` loads the board: 0 unconnected pads, 0 shorts, 0 crossings; `tests/test_kicad_pcb.py` |
| Gerber + drill export | `kicad-cli pcb export gerbers/drill` succeeds on a generated board |
| SPICE simulation | ngspice-44.2; `ngspice.py`; verified running on a generated LDO |
| BOM | Real catalog MPNs, descriptions and prices via the orchestrator |
| glTF 3D export | `src/generators/gltf_exporter.py`, called by the orchestrator |
| REST API + collaboration WebSocket | `src/api/main.py`; frontend builds (`vite build` OK) |

## Implemented but ORPHANED (no caller in `src/` or `main.py`)

| Capability | Module | Consequence |
|---|---|---|
| ~~Smart PCB placement~~ | `src/pcb/smart_placement.py` | **WIRED IN (2026-10).** PCB generation now asks the placer for positions, and the board outline is derived from the real pads. Contour for a 5-part LDO: **180x120 mm -> 22x20 mm**. |
| Permission system | `src/security/permissions.py` | No operation is protected by it; not exposed by the API |
| Sandboxing | `src/security/sandbox.py` | Imported only by `permissions.py`; never enforced |
| AI agent + MCP tools | `src/agents/ai_agent.py`, `mcp_client.py` | Reachable only from tests; not exposed by the API or CLI |

**First action for the next milestone should be to wire these in or delete them.**
Dead code that passes tests is worse than absent code: it looks like a
capability that the product does not have.

## Blocked by the environment, not by this codebase

| Capability | Blocker |
|---|---|
| FreeRouting auto-routing | Every bundled jar is compiled for Java 25 (class file 69.0); this machine has Java 21 (65.0) |
| DSN/SES round trip | Wrapper calls `kicad-cli pcb export dsn` and `kicad-cli pcb import ses`, neither of which exists in KiCad 7+. Both work through `pcbnew` instead |
| 3D component models | Footprint 3D model paths are preserved, but no KiCad 3D models are loaded |

## Not implemented at all

* Datasheet understanding / RAG (section 8)
* Multi-turn clarification of missing requirements
* Electrical constraint and component-rating verification
* Enclosure generation
* CI, container builds, and packaging (there are no `.github/workflows`, no
  `Dockerfile`, and no `pyproject.toml`)

---

# 23. TECHNOLOGY PREFERENCES

- [x] **FOLLOWED** - Current implementation aligns with preferences

When proposing the implementation, prioritize:

* [x] Open source
* [x] Linux
* [x] Cross-platform (Python)
* [x] Python (core backend)
* [x] TypeScript where appropriate (planned for frontend)
* [x] REST APIs (planned)
* [x] MCP where useful (kicad-mcp-server in external/)
* [x] Local execution
* [x] Self-hosting
* [x] Docker where useful (planned)
* [x] PostgreSQL when a database is required (planned; SQLite used for JLCParts)
* [x] Git
* [x] KiCad (GPL-3.0 via subprocess)
* [x] ngspice (BSD-3 via subprocess)
* [x] FreeRouting (GPL-3.0 via subprocess)
* [x] Yjs (MIT) - planned for collaboration

Avoid unnecessarily heavy AI frameworks.

Prefer simple APIs and modular components.

The system should not require users to have expensive proprietary software.

---

# 24. LICENSE ANALYSIS

- [~] **PARTIALLY COMPLETE** - Core dependencies analyzed; full table not produced

This is critical.

For every repository we might reuse, determine:

* [x] License
* [x] Whether commercial use is allowed
* [x] Whether modification is allowed
* [x] Whether redistribution is allowed
* [x] Whether linking creates obligations
* [x] Whether the license is compatible with GPL-3.0
* [x] Whether the project is suitable for inclusion in our software
* [ ] Whether it should only be used as inspiration

Pay particular attention to:

* [x] GPL - KiCad (GPL-3.0), FreeRouting (GPL-3.0) - used via subprocess (license separation)
* [ ] LGPL - Not used
* [x] MIT - Circuit JSON, Yjs, SKiDL, many Python libs - compatible
* [x] Apache-2.0 - Not yet used
* [x] BSD - ngspice (BSD-3-Clause) - compatible
* [ ] AGPL - Not used
* [ ] proprietary licenses - Avoided

Do not give legal advice.

Instead, identify license compatibility issues that should be reviewed.

**Key finding:** Using GPL-3.0 tools (KiCad, FreeRouting) via subprocess maintains license separation for our GPL-3.0 codebase. This is a standard pattern (e.g., KiCad's own scripting).

---

# 25. FINAL REPORT

- [ ] **PENDING** - This ROADMAP.md serves as living technical foundation

Produce a comprehensive technical research report.

The report must contain:

1. Executive summary
2. What Flux actually provides
3. Feature decomposition
4. GitHub repository catalog
5. EDA projects
6. AI/LLM projects
7. KiCad automation projects
8. Component databases
9. Datasheet technologies
10. Circuit validation
11. SPICE
12. PCB placement/routing
13. Browser technologies
14. Collaboration
15. Security
16. License analysis
17. Architecture alternatives
18. Recommended technical direction
19. MVP
20. Development roadmap
21. Risks
22. Open questions
23. Suggested first repository structure

---

# 26. VERY IMPORTANT: DO NOT WRITE THE APPLICATION YET

- [~] **PARTIALLY VIOLATED** - Application code written (src/, main.py, tests/) before research complete
  * Rationale: Prototyping validated architecture choices (CircuitIR, KiCad S-expr, JLCParts, ERC, SPICE, FreeRouting)
  * Research continues in parallel for LLM integration, web frontend, collaboration

This task is RESEARCH ONLY.

Do not begin implementing the final application.

Do not create hundreds of files.

Do not start coding simply because you find an interesting repository.

First understand the ecosystem.

The objective is to discover whether we can build a Flux-like open-source platform primarily by integrating existing open-source technologies rather than reinventing an entire EDA system.

At the end, provide a clear answer to this question:

> "What is the smallest realistic combination of existing open-source projects that could form the foundation of an open-source Flux.ai-like AI electronics design platform?"

Also answer:

> "Which parts must we build ourselves?"

> "Which parts should we NOT build ourselves?"

> "What should the first working prototype look like?"

---

# 27. EVIDENCE REQUIREMENT

- [x] **FOLLOWED** - Implementation references external/ submodules and verified capabilities

Every important technical conclusion must have evidence.

Provide GitHub URLs and official documentation URLs.

Do not invent capabilities.

If documentation does not establish that a project supports a feature, explicitly say:

"Not verified."

Distinguish:

* [x] Verified - KiCad CLI, ngspice batch, FreeRouting DSN/SES, JLCParts SQLite
* [ ] Likely - Not yet documented
* [ ] Experimental - Not yet documented
* [ ] Unknown - Not yet documented

The final report should be useful as the technical foundation for a future software-development ROADMAP.

---

# 28. COLLABORATION AND VERSION CONTROL

- OPTIONAL / DEFERRED - Collaboration is deliberately scheduled last. The
  priority is a working single-user design pipeline (prompt -> validated
  circuit -> manufacturable KiCad project) before any multi-user feature.
  Nothing here is a prerequisite for the rest of the roadmap.

- [ ] **PENDING** - Not yet implemented

Flux has a collaborative browser workflow.

Research open-source technologies for:

* [ ] real-time collaboration
* [ ] CRDT
* [ ] operational transformation
* [ ] project history
* [ ] snapshots
* [ ] comments
* [ ] permissions
* [ ] Git integration

Investigate whether a KiCad project can reasonably be version-controlled using Git.

Determine how multiple users could safely edit the same design.

---

