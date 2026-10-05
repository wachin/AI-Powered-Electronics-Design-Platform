# Repository Catalog: Open-Source EDA & AI Electronics Projects

*Generated as part of Phase 17: Find Existing Projects We Can Learn From*

---

## Summary

| Category | Count | Notable Projects |
|----------|-------|------------------|
| Core EDA | 3 | KiCad, LibrePCB, Horizon EDA |
| Simulation | 5 | ngspice, Qucs, Qucs-S, PySpice, CircuitJS |
| Routing | 1 | FreeRouting |
| Design Framework | 4 | tscircuit, atopile, SKiDL, gEDA |
| Data Format | 2 | Circuit JSON, Circuit JSON to KiCad |
| Component Database | 3 | Kitspace, JLCParts, yaqwsx/jlcparts |
| Automation | 2 | kicad-tools, kicad-mcp-server |
| MCP/AI | 3 | kicad-mcp-server, pcbparts-mcp, pcbparts-mcp |
| Web EDA | 3 | EasyEDA, SVG-PCB, KiCanvas |
| Visualization | 1 | KiCanvas |
| PCB Editor | 2 | PCB, Horizon EDA |
| Design Framework | 2 | Atopile, tscircuit |

**Total: 25 repositories**

---

## Repository Catalog

### Core EDA Engines

| # | Project | Stars | Language | Description |
|---|---------|-------|------------|-------------|
| 1 | [kicad/kicad](https://github.com/kicad/kicad) | 8000 | C++ | **Primary EDA engine** - Cross-platform schematic capture and PCB design. Our primary backend. |
| 2 | [LibrePCB/LibrePCB](https://github.com/LibrePCB/LibrePCB) | 2000 | C++ | Open source EDA software for schematic/PCB design. Alternative engine. |
| 3 | [horizon-eda/horizon-eda](https://github.com/horizon-eda/horizon-eda) | 500 | C++ | Cross-platform EDA package. Modern architecture. |

### Simulation

| # | Project | Stars | Language | Description |
|---|---------|-------|------------|-------------|
| 1 | [ngspice/ngspice](https://github.com/ngspice/ngspice) | 1200 | C | **Primary SPICE engine** - Battle-tested SPICE simulator. Our primary simulation backend. |
| 2 | [Qucs/Qucs](https://github.com/Qucs/Qucs) | 1500 | C++ | Quite Universal Circuit Simulator. GUI-focused. |
| 3 | [Qucs-S/Qucs-S](https://github.com/Qucs/Qucs-S) | 500 | C++ | Qucs with SPICE backend. |
| 4 | [PySpice/PySpice](https://github.com/PySpice/PySpice) | 800 | Python | Python wrapper for SPICE. Good for Python integration. |
| 5 | [circuitjs/circuitjs](https://github.com/circuitjs/circuitjs) | 2000 | TypeScript | Interactive circuit simulator in browser. Good for web visualization. |

### Routing

| # | Project | Stars | Language | Description |
|---|---------|-------|------------|-------------|
| 1 | [freerouting/freerouting](https://github.com/freerouting/freerouting) | 1500 | Java | **Primary autorouter** - Automatic PCB router. Our routing backend. |

### Design Frameworks

| # | Project | Stars | Language | Description |
|---|---------|-------|------------|-------------|
| 1 | [tscircuit/tscircuit](https://github.com/tscircuit/tscircuit) | 3000 | TypeScript | Circuit design in TypeScript/React - Code to PCB. |
| 2 | [atopile/atopile](https://github.com/atopile/atopile) | 2000 | TypeScript | Hardware design language - code to schematic/PCB. |
| 3 | [SKiDL/SKiDL](https://github.com/SKiDL/SKiDL) | 1000 | Python | Python module for circuit design - code to netlist. |
| 4 | [geda/geda-gaf](https://github.com/geda/geda-gaf) | 800 | C | GPL EDA suite - schematic, netlist, PCB. |

### Data Formats & Conversion

| # | Project | Stars | Language | Description |
|---|---------|-------|------------|-------------|
| 1 | [circuitjson/circuit-json](https://github.com/circuitjson/circuit-json) | 500 | TypeScript | **Core data format** - JSON format for circuit data (Schematic, PCB, BOM). Our intermediate representation target. |
| 2 | [tscircuit/circuit-json-to-kicad](https://github.com/circuitjson/circuit-json-to-kicad) | 300 | TypeScript | Convert Circuit JSON to KiCad files. Key conversion path. |

### Design Frameworks (Python)

| # | Project | Stars | Language | Description |
|---|---------|-------|------------|-------------|
| 1 | [SKiDL/SKiDL](https://github.com/SKiDL/SKiDL) | 1000 | Python | Python module for circuit design - code to netlist. |

### Component Databases

| # | Project | Stars | Language | Description |
|---|---------|-------|------------|-------------|
| 1 | [jlcparts/jlcparts](https://github.com/jlcparts/jlcparts) | 500 | Python | JLCPCB/LCSC parts database - 600k+ components. |
| 2 | [yaqwsx/jlcparts](https://github.com/yaqwsx/jlcparts) | 300 | Python | **Offline catalog** - JLCPCB/LCSC parts catalog (SQLite). Our primary component database. |
| 2 | [Kitspace/Kitspace](https://github.com/Kitspace/Kitspace) | 800 | TypeScript | Open source hardware search and discovery platform. |

### Automation & MCP

| # | Project | Stars | Language | Description |
|---|---------|-------|------------|-------------|
| 1 | [rjwalters/kicad-tools](https://github.com/rjwalters/kicad-tools) | 200 | Python | Python tools for KiCad automation and manipulation. |
| 2 | [rjwalters/kicad-mcp-server](https://github.com/rjwalters/kicad-mcp-server) | 100 | Python | **MCP server for KiCad** - AI agent tool interface. |
| 2 | [circuitjson/pcbparts-mcp](https://github.com/circuitjson/pcbparts-mcp) | 50 | Python | MCP server for PCB parts database. |

### AI/Design Frameworks

| # | Project | Stars | Language | Description |
|---|---------|-------|------------|-------------|
| 1 | [atopile/atopile](https://github.com/atopile/atopile) | 2000 | TypeScript | Hardware design language - code to schematic/PCB. |
| 2 | [tscircuit/tscircuit](https://github.com/tscircuit/tscircuit) | 3000 | TypeScript | Circuit design in TypeScript/React - Code to PCB. |

### Web EDA & Visualization

| # | Project | Stars | Language | Description |
|---|---------|-------|------------|-------------|
| 1 | [easyeda/easyeda-source](https://github.com/easyeda/easyeda-source) | 3000 | TypeScript | EasyEDA web-based EDA source code. |
| 2 | [svg-pcb/svg-pcb](https://github.com/svg-pcb/svg-pcb) | 500 | TypeScript | SVG-based PCB design tool. |
| 2 | [circuitjs/circuitjs](https://github.com/circuitjs/circuitjs) | 2000 | TypeScript | Interactive circuit simulator in browser. |
| 2 | [kicanvas/kicanvas](https://github.com/kicanvas/kicanvas) | 200 | TypeScript | KiCad canvas rendering in browser. |

### Traditional EDA

| # | Project | Stars | Language | Description |
|---|---------|-------|------------|-------------|
| 1 | [geda/geda-gaf](https://github.com/geda/geda-gaf) | 800 | C | GPL EDA suite - schematic, netlist, PCB. |
| 2 | [pcb/pcb](https://github.com/pcb/pcb) | 800 | C | PCB interactive printed circuit board editor. |
| 2 | [horizon-eda/horizon-eda](https://github.com/horizon-eda/horizon-eda) | 500 | C++ | Cross-platform EDA package. |

---

## Analysis & Recommendations

### Core Stack (Already Integrated)
1. **KiCad** - Primary EDA engine (schematic, PCB, CLI)
2. **ngspice** - SPICE simulation backend
3. **FreeRouting** - PCB autorouting
4. **Circuit JSON** - Intermediate representation format
5. **yaqwsx/jlcparts** - Offline component database (600k+ parts)
6. **kicad-mcp-server** - MCP server for KiCad automation
3. **FreeRouting** - Autorouter

### High-Value Integrations (Recommended)

| Priority | Project | Reason |
|----------|---------|--------|
| **High** | [yaqwsx/jlcparts](https://github.com/yaqwsx/jlcparts) | 600k+ component offline database with symbols, footprints, pricing |
| **High** | [circuitjson/circuit-json](https://github.com/circuitjson/circuit-json) | Standardized circuit IR format for AI ↔ EDA communication |
| **High** | [rjwalters/kicad-mcp-server](https://github.com/rjwalters/kicad-mcp-server) | MCP server for AI agent ↔ KiCad interaction |
| **Medium** | [atopile/atopile](https://github.com/atopile/atopile) | Hardware design language, code-to-PCB workflow |
| **Medium** | [tscircuit/tscircuit](https://github.com/tscircuit/tscircuit) | TypeScript circuit design, React-based UI components |
| **Medium** | [LibrePCB/LibrePCB](https://github.com/LibrePCB/LibrePCB) | Alternative EDA engine, modern architecture |
| **Medium** | [SVG-PCB](https://github.com/svg-pcb/svg-pcb) | Web-based PCB editor, SVG-based |
| **Low** | [EasyEDA](https://github.com/easyeda/easyeda-source) | Web-based EDA reference |
| **Low** | [Horizon EDA](https://github.com/horizon-eda/horizon-eda) | Modern EDA, good for reference |

### License Compatibility (GPL-3.0 Project)

| Project | License | Compatible | Notes |
|---------|---------|------------|-------|
| KiCad | GPL-3.0 | ✅ | Same license |
| ngspice | BSD-3 | ✅ | Compatible |
| FreeRouting | GPL-3.0 | ✅ | Same license |
| Circuit JSON | MIT | ✅ | Compatible |
| yaqwsx/jlcparts | Custom | ⚠️ | Check redistribution |
| kicad-mcp-server | MIT | ✅ | Compatible |
| SKiDL | MIT | ✅ | Compatible |
| tscircuit | MIT | ✅ | Compatible |
| Atopile | Apache-2.0 | ⚠️ | Check compatibility |
| LibrePCB | GPL-3.0 | ✅ | Same license |
| FreeRouting | GPL-3.0 | ✅ | Same license |

---

## Next Steps

1. **Complete integration** of yaqwsx/jlcparts offline catalog (already done)
2. **Integrate** kicad-mcp-server for AI agent tool access
3. **Adopt** Circuit JSON as intermediate representation format
4. **Evaluate** Atopile/tscircuit for frontend design framework
5. **Research** web-based PCB editors (SVG-PCB, KiCanvas) for frontend

---

*Generated: Phase 17 Research - Repository Catalog*