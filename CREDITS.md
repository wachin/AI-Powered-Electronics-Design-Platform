# Credits and Third-Party Licensing

This project is licensed under **GNU GPL-3.0** (see `LICENSE`). It builds on the
work of others, and this file records those dependencies, what they are used
for, and the licensing terms that apply.

**This is not legal advice.** Verify licenses against upstream sources before
any commercial distribution.

---

## 1. KiCad symbol and footprint libraries

**Most important dependency for generated output.** The schematic and PCB
generators read symbol and footprint definitions from the locally installed
KiCad libraries in order to emit files that KiCad can actually open, netlist
and fabricate.

| Field | Value |
|---|---|
| Project | KiCad E.D.A. symbol and footprint libraries |
| Upstream | https://gitlab.com/kicad/libraries/kicad-symbols, https://gitlab.com/kicad/libraries/kicad-footprints |
| Documentation | https://kicad.github.io/symbols/, https://kicad.github.io/footprints/ |
| Copyright | 2025 KiCad Community |
| License | **CC-BY-SA-4.0 with an exception** |
| How used | Read at runtime from the installed KiCad libraries |
| Files | `/usr/share/kicad/symbols/*.kicad_sym`, `/usr/share/kicad/footprints/*.pretty/*.kicad_mod` |
| Modules | `src/generators/kicad_symbols.py`, `src/generators/kicad_footprints.py` |

### Why this is used at runtime and not vendored

The library data is **not copied into this repository**. The generators locate
the libraries on the host system, parse them, and re-emit the relevant symbol
or footprint into a generated `.kicad_sch` / `.kicad_pcb` file. This keeps the
repository free of third-party library data and means the project produces
output matching whatever KiCad version the user has installed.

### The exception matters for your designs

KiCad library files are CC-BY-SA-4.0, which normally imposes a share-alike
obligation. KiCad ships an explicit exception (quoted from the Debian
`copyright` file for `kicad-footprints` and `kicad-symbols`):

> "To the extent that the creation of electronic designs that use 'Licensed
> Material' can be considered to be 'Adapted Material', then the copyright
> holder waives article 3 of the license with respect to these designs and
> any generated files which use data provided as part of the 'Licensed
> Material'."

**What this means in practice:**

* A circuit board you generate with this tool — including its schematics,
  PCB files, Gerbers and other fabrication output — is **not** placed under
  CC-BY-SA by using the KiCad libraries, thanks to this exception.
* The KiCad library files themselves remain CC-BY-SA-4.0. If you redistribute
  the libraries (or modified copies of them), that license applies.
* This project does not redistribute them, which is why the runtime-read
  approach was chosen.

**Attribution:** KiCad and its libraries are the work of the KiCad Community,
licensed under CC-BY-SA-4.0 with the exception above. This project gratefully
acknowledges that work.

**Requirement:** a working KiCad installation (with its symbol and footprint
libraries) must be present for schematic and PCB generation. Without it, the
generators report the affected components and emit incomplete output rather
than silently producing files KiCad cannot use.

---

## 2. KiCad application and `kicad-cli`

| Field | Value |
|---|---|
| Project | KiCad E.D.A. (application, `kicad-cli`) |
| Upstream | https://gitlab.com/kicad/code/kicad |
| Copyright | (C) 2015-2025 KiCad Developers |
| License | GPL-3.0-or-later |
| How used | Invoked as a **subprocess** for netlist export, ERC, DRC, Gerber/drill export |

Invoked as an external executable only. No KiCad source code is copied,
linked, imported or modified by this project. License separation is maintained
by the process boundary.

---

## 3. Python dependencies

Declared in `requirements.txt`. These are linked/imported libraries, so their
licenses apply to the combined work.

| Package | Purpose | License |
|---|---|---|
| `httpx` | HTTP client for LLM providers | BSD-3-Clause |
| `pytest`, `pytest-cov` | Test suite | MIT |
| `pydantic` | Data validation (API) | MIT |
| `fastapi` | REST API backend | MIT |
| `uvicorn` | ASGI server | BSD-3-Clause |
| `requests` | HTTP client | Apache-2.0 |
| `skidl` | Reference for netlist concepts (not imported by core code) | MIT |

The license column reflects the upstream project's usual terms; confirm against
the installed package metadata (`pip show <pkg>` or the package's `LICENSE`
file) before distribution.

---

## 4. Reference repositories under `external/`

The repositories in `external/` are **Git submodules used as technical
references only** and are never imported, linked, or added to the import path.
See `AGENTS.md` for the full policy. Each remains under its own license; study
of a reference repository does not make it a dependency of this project.

---

## 5. Component and distributor data

| Field | Value |
|---|---|
| Project | jlcparts — JLCPCB/LCSC component catalog (upstream data) |
| Upstream | https://github.com/yaqwsx/jlcparts |
| License | MIT (the jlcparts tooling) |
| How used | Optional offline SQLite catalog, read at runtime when present |

| Field | Value |
|---|---|
| Project | jlcpcb-parts-database — republished SQLite build |
| Source | https://github.com/CDFER/jlcpcb-parts-database |
| How used | The download target of `catalog-setup`; the single-file SQLite build this project actually reads |

The upstream jlcparts dataset is published as a ~10 GB multi-volume archive that
most zip libraries cannot open, so this project fetches CDFER's single-file
SQLite rebuild of the same JLCPCB data. The file is **not** redistributed here:
it is downloaded by the user into their own cache directory, and it is not
covered by this project's license. Check the distributor's terms before
redistributing the catalog itself.

When the catalog is absent, the platform falls back to a small built-in catalog
of common parts defined in `src/components/database.py`. Part numbers, prices and
stock figures are indicative and must be verified with the distributor before
ordering.

---

## 6. Trademarks

KiCad is a trademark of the KiCad project. Flux, Flux.ai and related marks are
trademarks of Flux Lab Inc. This project is an independent implementation
**inspired by** commercial EDA platforms; it is not affiliated with, endorsed
by, or a copy of Flux.ai. See `LEGAL_NOTICE.md` for details.

---

## 7. Summary for users

If you generate a design with this tool:

* **Your generated design is yours** to use, manufacture and sell — the KiCad
  library exception above is what makes that true.
* **Keep KiCad installed**, since generation depends on its libraries.
* **Verify part numbers, footprints and prices** before ordering; the automatic
  part substitution in this project is a convenience, not a guarantee.
* **Do not assume** this file is a substitute for legal review. It is a record
  of dependencies and their stated terms.
