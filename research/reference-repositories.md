# Reference Repositories

This project was built by studying existing open-source EDA software. Those
repositories are **technical references, not dependencies**, and **none of them
are required** to build, test or run the platform.

They are deliberately **not** Git submodules. A submodule would force everyone
who clones this repository to download several gigabytes of research material
they do not need. Instead, they are listed here with their purpose, and you can
clone the one or two you actually want to read.

```bash
# Nothing to configure: cloning this project downloads only this project.
git clone https://github.com/wachin/AI-Powered-Electronics-Design-Platform
```

If you want a reference repository locally, fetch it yourself:

```bash
git clone --depth 1 https://github.com/yaqwsx/jlcparts /tmp/refs/jlcparts
```

`--depth 1` skips the full history, which is most of the size.

---

## What is installed vs. what is browsed

This distinction is the whole point of this file:

| Kind | Where it goes | How it arrives |
|---|---|---|
| **Python dependencies** | the project's `venv/` | `pip install -e ".[dev]"` — declared in `pyproject.toml` |
| **MCP servers** | `.mcp_envs/<name>/` (isolated, `mcp-setup`) | from PyPI or a git URL — declared in `pyproject.toml` |
| **Non-Python binaries** | `libs/` (for example the FreeRouting jar) | downloaded by you — see `libs/freerouting/README.md` |
| **Reference repositories** | wherever you like, e.g. `/tmp/refs/` | `git clone` — **optional, never required** |

Nothing installable is ever cloned into this repository's source tree.

---

## The reference repositories

Grouped by what they were studied for. Sizes are approximate and assume a full
clone; `--depth 1` is far smaller.

### Already used by the project

| Repository | URL | License | Studied for |
|---|---|---|---|
| `jlcparts` | https://github.com/yaqwsx/jlcparts | MIT | Component catalog format and the offline JLCPCB/LCSC dataset |
| `kicad` | https://gitlab.com/kicad/code/kicad | GPL-3.0 | S-expression file formats, ERC/DRC rules, `pcbnew` API |
| `freerouting` | https://github.com/freerouting/freerouting | GPL-3.0 | Specctra DSN/SES interface used by the autorouter |
| `pcbparts-mcp` | https://github.com/Averyy/pcbparts-mcp | MIT | Part search, design rules, reference boards (usable as an MCP server) |
| `kicad-mcp-server` | https://github.com/Seeed-Studio/kicad-mcp-server | MIT | MCP tool surface for KiCad analysis and validation |
| `kicad-tools` | https://github.com/rjwalters/kicad-tools | MIT | Programmatic KiCad parsing/editing from Python |
| `ngspice` | https://git.code.sf.net/p/ngspice/ngspice | BSD-3-Clause | SPICE netlist semantics and batch invocation |

### Interchange formats

| Repository | URL | License | Studied for |
|---|---|---|---|
| `circuit-json` | https://github.com/tscircuit/circuit-json | MIT | Circuit JSON element model |
| `circuit-json-to-kicad` | https://github.com/tscircuit/circuit-json-to-kicad | MIT | Circuit JSON → KiCad conversion approach |
| `kicad-to-circuit-json` | https://github.com/tscircuit/kicad-to-circuit-json | MIT | KiCad → Circuit JSON parsing |
| `kicad-converter` | https://github.com/tscircuit/kicad-converter | MIT | Format conversion patterns |

### Circuit description frameworks

| Repository | URL | License | Studied for |
|---|---|---|---|
| `skidl` | https://github.com/devbisme/skidl | MIT | Python netlist description and ERC concepts |
| `atopile` | https://github.com/atopile/atopile | MIT | Hardware description language and constraints |
| `circuit-synth` | https://github.com/circuit-synth/circuit-synth | MIT | Python-first circuit definition |
| `tscircuit` / `tscircuit-core` | https://github.com/tscircuit/tscircuit | MIT | React-based schematic authoring |

### Collaboration and visualisation

| Repository | URL | License | Studied for |
|---|---|---|---|
| `yjs` | https://github.com/yjs/yjs | MIT | CRDT used by the collaboration server |
| `automerge` | https://github.com/automerge/automerge | MIT | Alternative CRDT approach (not adopted) |
| `kicanvas` | https://github.com/theacodes/kicanvas | MIT | Browser-based KiCad viewing |
| `ecad-viewer` | https://github.com/openscopeproject/InteractiveHtmlBom | MIT | Interactive assembly/BOM views |

### Alternative EDA tools (for comparison)

| Repository | URL | License | Studied for |
|---|---|---|---|
| `librepcb` | https://github.com/LibrePCB/LibrePCB | GPL-3.0 | Alternative EDA data model |
| `qucs-s` | https://github.com/ra3xdh/qucs_s | GPL-2.0 | Schematic capture + simulation integration |
| `pyspice` | https://github.com/PySpice-org/PySpice | GPL-3.0 | Python SPICE front-end |

### Hosted workflow references

These websites were studied but are not open source; they are listed for
completeness because architectural lessons were drawn from their public
documentation. No code was taken from them.

| Product | Studied for |
|---|---|
| Flux.ai | Product concept and workflow (see `flux-ai-patent-search.md`) |
| EasyEDA | Browser-based EDA UX |
| Horizon EDA | Open-source EDA data model |

---

## Full catalogue

`research/repository_catalog.md` contains the complete evaluation: repositories
considered, licenses, maintenance status and the conclusion reached for each.
That document is the record of the research; this file is just the practical
list of where to get them if you want to read the code.

## Why not Git submodules?

Three reasons, in order of importance:

1. **A clone should download what is needed.** Submodules make every developer
   pay for research material they will never open.
2. **A submodule pinned in a repository is a dependency in practice.**
   `AGENTS.md` requires references and dependencies to stay clearly separated;
   removing the submodule mechanism makes that separation structural rather than
   a matter of discipline.
3. **Reference commits should be recorded deliberately.** Research notes state
   what was evaluated; a floating submodule pointer does not.

See `AGENTS.md` for the reference-versus-dependency policy, and `CREDITS.md` for
licensing.
