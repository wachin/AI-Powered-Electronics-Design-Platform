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

Investigate at minimum:

* KiCad
* LibrePCB
* gEDA
* PCB / pcb-rnd
* QUCS / Qucs-S
* ngspice
* LTspice alternatives
* SKiDL
* PySpice
* other relevant open-source EDA projects

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

# 4. INVESTIGATE KIcad AUTOMATION

This is one of the most important parts of the research.

Find existing projects that allow AI agents or programs to control KiCad.

Search for:

* KiCad MCP
* KiCad Copilot
* KiCad AI
* KiCad automation
* KiCad Python
* KiCad CLI
* KiCad schematic generation
* KiCad PCB generation
* KiCad programmatic routing
* KiCad project manipulation
* KiCad parsers
* KiCad file libraries

Investigate projects such as:

* kicad-mcp
* kicad-copilot
* pcb-creator

and discover additional projects.

For each project explain exactly what it can do.

Determine whether it can:

* Create a project
* Create a schematic
* Add components
* Connect components
* Modify existing circuits
* Select footprints
* Generate PCB layouts
* Place components
* Route traces
* Run ERC
* Run DRC
* Generate Gerbers
* Generate BOM
* Generate pick-and-place
* Inspect errors
* Read existing KiCad projects

Determine whether we could use these projects as dependencies, inspiration, or code.

---

# 5. INVESTIGATE AI/LLM ARCHITECTURES FOR ELECTRONICS

Research how an LLM can safely transform natural language into an electronic design.

Investigate:

* LLM agents
* MCP
* tool calling
* structured output
* JSON schemas
* function calling
* multi-agent architectures
* planning agents
* verification agents
* RAG
* datasheet RAG
* vector databases
* knowledge graphs
* constraint solving
* symbolic reasoning
* circuit graph representations

Find GitHub projects that demonstrate these techniques for electronics.

Do not assume that an LLM should directly generate KiCad files.

Determine whether a safer architecture would be:

Natural language
→ structured engineering specification
→ circuit intermediate representation
→ deterministic compiler
→ KiCad

Analyze this architecture carefully.

---

# 6. DESIGN AN INTERMEDIATE REPRESENTATION

Investigate whether we should create an internal representation of an electronic circuit.

For example:

Circuit
├── Components
├── Pins
├── Nets
├── Power domains
├── Signals
├── Constraints
├── Parameters
├── Physical requirements
└── Manufacturing requirements

Research existing representations such as:

* netlists
* SPICE netlists
* SKiDL
* KiCad schematic formats
* EDIF
* IPC formats
* other EDA interchange formats

Determine whether we should:

A. Directly manipulate KiCad files

B. Generate SKiDL and then KiCad

C. Create our own intermediate representation and compile it to KiCad

D. Use another architecture

Explain the advantages and disadvantages.

---

# 7. COMPONENT DATABASE

Research open-source and publicly accessible component databases.

We need to understand how an AI system could answer questions such as:

"Find a 3.3V LDO capable of 500mA, available in SOT-23, preferably from a common manufacturer."

Investigate:

* KiCad libraries
* SnapEDA
* Ultra Librarian
* Octopart
* DigiKey
* Mouser
* LCSC
* SamacSys
* parts databases
* open component databases
* manufacturer APIs
* distributor APIs

Clearly separate:

* Open-source data
* Free APIs
* Commercial APIs
* Scraping
* Data that cannot legally be redistributed

Investigate how to obtain:

* Manufacturer
* MPN
* Datasheet
* Symbol
* Footprint
* 3D model
* Electrical specifications
* Availability
* Price
* Alternatives

---

# 8. DATASHEET UNDERSTANDING

Research projects for extracting structured information from PDF datasheets.

Investigate:

* PDF extraction
* OCR
* table extraction
* document parsing
* RAG
* embeddings
* vector databases
* multimodal models
* local LLMs

The system should eventually be able to answer questions such as:

"What capacitor should I place near the VCC pin according to the manufacturer's datasheet?"

or:

"What are the absolute maximum ratings?"

or:

"What is the recommended application circuit?"

Find open-source projects that could help.

---

# 9. CIRCUIT VALIDATION

Research how we can prevent an LLM from producing invalid electronics.

Investigate:

* ERC
* DRC
* SPICE
* symbolic circuit analysis
* electrical constraint checking
* netlist validation
* power-domain validation
* pin compatibility
* voltage compatibility
* current requirements
* decoupling verification
* pull-up/pull-down verification
* component rating verification

Determine which checks should be performed by deterministic software rather than by the LLM.

This is extremely important.

The AI should propose designs, but deterministic engineering tools should verify them whenever possible.

---

# 10. PCB PLACEMENT AND ROUTING

Research open-source PCB routing algorithms and projects.

Investigate:

* autorouters
* global routing
* detailed routing
* pathfinding
* A*
* Lee algorithm
* maze routing
* optimization
* reinforcement learning
* machine learning for PCB placement
* machine learning for PCB routing
* differential pair routing
* impedance-aware routing
* thermal considerations
* power distribution
* ground planes

Find GitHub repositories implementing these technologies.

Determine whether we should:

1. Use KiCad's existing routing infrastructure.
2. Integrate an external autorouter.
3. Develop our own routing engine.
4. Use AI only for high-level placement/routing decisions and deterministic algorithms for final routing.

---

# 11. SPICE SIMULATION

Investigate open-source simulation systems.

At minimum investigate:

* ngspice
* Qucs-S
* PySpice
* other relevant projects

Determine how a generated circuit could automatically become a simulation.

Example:

User:

"Build a 5V to 3.3V regulator circuit."

System:

1. Generates schematic.
2. Selects components.
3. Generates SPICE model.
4. Runs simulation.
5. Checks voltage/current.
6. Reports problems.
7. Modifies design if necessary.

Investigate how feasible this workflow is.

---

# 12. WEB APPLICATION ARCHITECTURE

Research open-source technologies for building a browser-based EDA interface.

Investigate:

* React
* Vue
* Svelte
* TypeScript
* WebAssembly
* SVG
* Canvas
* WebGL
* Three.js
* Monaco Editor
* WebSockets
* collaborative editing
* CRDT
* Yjs
* real-time synchronization

Find GitHub projects that implement browser-based schematic or PCB editors.

Determine whether we should:

A. Build a completely new browser EDA editor.

B. Use KiCad as the backend and create a web frontend.

C. Create a hybrid architecture.

---

# 13. 3D PCB VISUALIZATION

Investigate open-source projects for:

* PCB 3D visualization
* STEP
* VRML
* glTF
* WebGL
* Three.js
* KiCad 3D models

Determine how the browser could show:

* PCB
* components
* copper
* layers
* traces
* 3D components
* board enclosure

---

# 14. COLLABORATION AND VERSION CONTROL

Flux has a collaborative browser workflow.

Research open-source technologies for:

* real-time collaboration
* CRDT
* operational transformation
* project history
* snapshots
* comments
* permissions
* Git integration

Investigate whether a KiCad project can reasonably be version-controlled using Git.

Determine how multiple users could safely edit the same design.

---

# 15. AI AGENT TOOL ARCHITECTURE

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

# 16. SECURITY

This system will eventually be capable of modifying engineering files.

Research security risks.

Investigate:

* malicious component data
* prompt injection in datasheets
* malicious project files
* arbitrary code execution
* unsafe Python execution
* MCP security
* tool permissions
* sandboxing
* supply-chain attacks
* untrusted KiCad files
* LLM hallucinations

Propose a permission architecture.

For example:

READ
WRITE
SIMULATE
EXPORT
MANUFACTURING

The AI should not automatically perform dangerous or irreversible operations without explicit approval.

---

# 17. FIND EXISTING PROJECTS WE CAN LEARN FROM

Search GitHub extensively.

Search terms should include combinations such as:

"AI PCB"

"AI EDA"

"AI schematic"

"LLM PCB"

"LLM electronics"

"PCB agent"

"EDA agent"

"KiCad AI"

"KiCad MCP"

"KiCad copilot"

"schematic generation LLM"

"PCB generation LLM"

"natural language PCB"

"natural language circuit"

"AI circuit design"

"AI circuit schematic"

"SPICE LLM"

"PCB autorouter"

"PCB placement AI"

"PCB routing machine learning"

"EDA automation"

"electronic design automation Python"

"browser PCB editor"

"web schematic editor"

"open source EDA"

Do not stop after finding the first few repositories.

---

# 18. CREATE A REPOSITORY CATALOG

Create a table containing at least 30 potentially relevant GitHub repositories if enough quality projects exist.

Columns:

| Project | URL | License | Language | Purpose | AI | EDA | API | Local | Web | Activity | Potential usefulness |

Then classify each project:

* CORE
* VERY USEFUL
* USEFUL
* REFERENCE
* EXPERIMENTAL
* NOT RECOMMENDED

Explain the classification.

Do not rank projects simply by popularity.

---

# 19. IDENTIFY THE MOST IMPORTANT BUILDING BLOCKS

After the research, identify the components we could realistically reuse.

Produce a table:

| Subsystem | Recommended open-source project | Why | License | Reuse strategy |
| --------- | ------------------------------- | --- | ------- | -------------- |

Subsystems should include:

* Schematic
* PCB
* Component library
* Datasheets
* Component search
* Netlist
* Simulation
* ERC
* DRC
* Placement
* Routing
* 3D
* AI agent
* MCP
* Web frontend
* Collaboration
* Database
* Version control
* Manufacturing output

---

# 20. PROPOSE AN ARCHITECTURE

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

---

# 21. PROPOSE A REALISTIC MVP

Design a minimum viable product.

The MVP should NOT attempt to reproduce all of Flux immediately.

Propose something like:

User:

"Create a 5V USB-C powered board with an LED and push button."

The system should:

1. Understand the requirements.
2. Ask missing engineering questions.
3. Produce a structured specification.
4. Select components.
5. Generate a schematic.
6. Open/produce the project in KiCad.
7. Run ERC.
8. Generate a basic PCB.
9. Run DRC.
10. Generate Gerbers and BOM.

Identify exactly which parts can initially be delegated to existing software.

---

# 22. PROPOSE A DEVELOPMENT ROADMAP

Create a phased roadmap:

## Phase 0 — Research

## Phase 1 — Circuit representation

## Phase 2 — AI requirements interpreter

## Phase 3 — Component database

## Phase 4 — Schematic generation

## Phase 5 — KiCad integration

## Phase 6 — ERC

## Phase 7 — SPICE

## Phase 8 — PCB placement

## Phase 9 — PCB routing

## Phase 10 — DRC

## Phase 11 — Manufacturing files

## Phase 12 — Web interface

## Phase 13 — Collaboration

## Phase 14 — Advanced AI hardware engineer

For each phase specify:

* Goal
* Existing projects to reuse
* New code required
* Dependencies
* Tests
* Expected deliverables
* Risks

---

# 23. TECHNOLOGY PREFERENCES

When proposing the implementation, prioritize:

* Open source
* Linux
* Cross-platform
* Python
* TypeScript where appropriate
* REST APIs
* MCP where useful
* Local execution
* Self-hosting
* Docker where useful
* PostgreSQL when a database is required
* Git
* KiCad
* ngspice

Avoid unnecessarily heavy AI frameworks.

Prefer simple APIs and modular components.

The system should not require users to have expensive proprietary software.

---

# 24. LICENSE ANALYSIS

This is critical.

For every repository we might reuse, determine:

* License
* Whether commercial use is allowed
* Whether modification is allowed
* Whether redistribution is allowed
* Whether linking creates obligations
* Whether the license is compatible with GPL-3.0
* Whether the project is suitable for inclusion in our software
* Whether it should only be used as inspiration

Pay particular attention to:

* GPL
* LGPL
* MIT
* Apache-2.0
* BSD
* AGPL
* proprietary licenses

Do not give legal advice.

Instead, identify license compatibility issues that should be reviewed.

---

# 25. FINAL REPORT

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

Every important technical conclusion must have evidence.

Provide GitHub URLs and official documentation URLs.

Do not invent capabilities.

If documentation does not establish that a project supports a feature, explicitly say:

"Not verified."

Distinguish:

* Verified
* Likely
* Experimental
* Unknown

The final report should be useful as the technical foundation for a future software-development ROADMAP.
