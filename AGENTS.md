# AGENTS.md

Working guide for AI coding agents, and the non-negotiable policy for this
repository. The practical half is first because that is what you need before your
first edit; the policy half must be read before you touch dependencies, licensing
or anything inspired by a commercial product.

---

# Working in this repository

## Read this first

* **`docs/development.md`** — setup, commands, the module map, extension recipes
  and the pitfalls. It is the document to trust when this file is not specific
  enough.
* **`README.md`** — what the product does and, importantly, what it does not do
  yet. The "Known Limitations" section is honest by design.
* **`ROADMAP.md`** — what is finished (with the evidence) and what is open.

## The commands

```bash
make                    # list every target
make diagnose           # what this machine can actually do
make test               # the suite without the component catalog (~2-4 min)
make lint               # ruff: undefined names, unused imports, duplicated keys
make demo               # build a design into output_design/demo
make compile-check      # byte-compile everything, as CI does
```

Two rules about the environment, both of which have cost time:

* **Always use the venv**: `venv/bin/python`, not `python3`. The only exception
  is `pcbnew`, which exists only in the system interpreter; the code finds it
  itself and you do not need to.
* **Run the suite both ways.** Without the catalog some tests skip; with it they
  run. A change that only passes one way is broken.

```bash
venv/bin/python -m pytest tests/ -q                      # without the catalog
JLC_PARTS_CATALOG=/path/to/jlcparts.sqlite3 \
  venv/bin/python -m pytest tests/ -q                    # with it
```

`make test-catalog CATALOG=/path/to/catalog.sqlite3` does the second.

## What this codebase demands of a change

Almost every bug in this project came from a plausible value that nobody checked.
These rules are the defence, and a reviewer will ask for them:

1. **Never invent a value that can be looked up.** A KiCad symbol, a footprint, a
   part number, a price, a junction temperature, a pin number. Look it up, or say
   it is not known. Earlier versions invented 26 symbol names and 5 template
   symbols; every design using them looked complete and could not be built.
2. **A check you cannot complete is `[?]`, not `✅`.** The electrical review has
   three states: `ok`, `fail`, `unknown` with the reason. Do not assume a
   datasheet figure to keep the output uniform. Do not assume θJA.
3. **Report, never hide.** A narrowed trace, a substituted part number, an
   assumed voltage: warnings that stay warnings. Nothing reduces a real problem to
   a green tick.
4. **Prefer the real tool.** KiCad, `kicad-cli`, FreeRouting, ngspice. Do not
   reimplement a plotter.
5. **A test that reads reality beats a test that restates the code.** If a fact
   lives in an installed library or a downloaded file, the test opens it.
6. **Prove the claim you put in the docs**, or write "verified manually on
   <date>".

`docs/development.md` explains each of these with the bug that produced it.

## Before you finish

```bash
make lint && make compile-check && make test
```

Then update `README.md` (the feature and its honest limits) and `ROADMAP.md`
(what was done, with evidence, and what stays open). A `[ ] **OPEN**` item with
the reason is worth more than a feature claimed and not finished.

## Where to start reading

| You want to change… | Start at |
|---|---|
| how a prompt becomes a design | `src/llm/integration.py`, `src/agents/orchestrator.py` |
| what a design is | `src/core/circuit_ir.py` |
| which parts are available | `src/components/jlcparts.py`, `src/components/database.py` |
| the electrical rules | `src/core/erc.py`, `src/core/design_review.py` |
| symbols, footprints, placement | `src/core/component_resolver.py`, `src/generators/` |
| trace widths and routing | `src/pcb/netclasses.py`, `src/routing/freerouting.py` |
| what the user can order | `src/components/ordering.py`, `src/generators/fabrication.py` |

Three modules are implemented and tested but **not wired into the pipeline**:
`src/security/permissions.py`, `src/security/sandbox.py` and
`src/agents/ai_agent.py`. Do not assume they run.

---

# External Repositories Policy

## Purpose

This project was built by studying existing open-source EDA software. Those
projects are **technical references**, and they are listed in
`research/reference-repositories.md` with what each was used for.

They are **not part of this repository and are not submodules**. Cloning this
project downloads only this project. That is deliberate: a developer should not
have to fetch gigabytes of research material to build, test or run the platform.

An agent may inspect a reference repository to understand how a problem has been
solved elsewhere. To read one:

```bash
git clone --depth 1 https://github.com/yaqwsx/jlcparts /tmp/refs/jlcparts
```

`research/repository_catalog.md` records the full evaluation: repositories
considered, licences, maintenance status and the conclusion reached for each.

---

## IMPORTANT: a reference repository is NOT a library directory

Do not:

* copy source files from a reference repository into this project
* import modules directly from a reference checkout
* add a reference checkout to application import paths
* modify a reference repository to implement project functionality
* build the application by depending on files inside a reference checkout
* create application code that assumes a particular reference repository is
  present
* silently convert a reference repository into a runtime dependency
* copy-paste large portions of reference source code
* mix project source code with reference source code

The presence of a project in `research/reference-repositories.md` does **not**
mean this project has adopted it as a dependency.

---

## Where third-party code is allowed to live

| Kind | Location | How it arrives |
|---|---|---|
| Python dependencies | `venv/` | `pip install -e ".[dev]"` — declared in `pyproject.toml` |
| MCP servers | `.mcp_envs/<name>/` | `mcp-setup` — declared in `pyproject.toml` (PyPI or `git+https://`) |
| Non-Python binaries | `libs/` | downloaded by the user, e.g. the FreeRouting jar |
| Reference repositories | anywhere outside the tree, e.g. `/tmp/refs/` | `git clone` — optional, never required |

**Rules:**

* never check an installable dependency into the source tree — declare it in
  `pyproject.toml`, on PyPI or as a `git+https://` URL;
* never require a research repository to be present for the build, tests or
  runtime;
* `libs/` is only for binary artifacts that genuinely cannot be installed.
  Vendored source belongs there only if the code is modified and cannot be
  published upstream — and that decision must be documented.

`tests/test_mcp_integration.py` enforces the first rule for the MCP servers: no
installable component may point at a local checkout.

---

## LEGAL CONSIDERATIONS FOR FLUX.AI

**IMPORTANT: This project builds an AI Electronics Design Platform inspired by Flux.ai, but IS NOT a copy of it.**

### Patent Considerations

Flux.ai is a proprietary commercial product. Before any commercial distribution:

1. **SEARCH FOR PATENTS** - Refer to `research/flux-ai-patent-search.md` for how to search and how to compare any patent found against this repository. This is a due-diligence and transparency aid; searching is not an admission that any patent was used.
2. **DO NOT COPY** - Never implement Flux.ai's specific algorithms or methods
3. **INDEPENDENT IMPLEMENTATION** - Write your own code from scratch

### Trademark Considerations

**DO NOT USE:**
- "Flux" in project name, domain, or branding
- Flux.ai logos, UI designs, or trademarks
- Claims like "Flux.ai clone" or "open-source Flux"

**SAFE REFERENCES:**
- "inspired by Flux.ai"
- "similar architecture to commercial EDA platforms"
- Pure technical analysis

### Code Implementation Rules

When implementing features similar to Flux.ai:

❌ **NEVER:**
- Copy existing Flux.ai source code
- Reproduce proprietary algorithms
- Use protected intellectual property

✅ **ALWAYS:**
- Study Flux.ai's features for understanding
- Write independent implementations
- Use only open-source dependencies via subprocess

---

## Do not depend on a reference project accidentally

Before introducing functionality into the main project, determine whether it should be:

1. implemented independently;
2. integrated through a documented public API;
3. invoked as an external executable;
4. used through a standard file format;
5. used through MCP;
6. used through a subprocess;
7. adopted as a formal project dependency.

Do not make this decision merely because a repository appears in the reference
list.

The architecture must remain understandable and reproducible without requiring
any research repository to be present.

---

## Research before integration

Before proposing an external project as a real dependency, investigate:

* current maintenance status
* license
* compatibility with this project's license
* supported platforms
* programming language
* dependencies
* API stability
* documentation
* test coverage
* release history
* security considerations
* whether the repository is archived
* whether development has moved to another repository
* whether the project is experimental or production-ready
* whether the required functionality is actually implemented

Do not infer capabilities solely from the repository name, README title, GitHub
stars, or marketing claims.

When possible, verify important capabilities by inspecting source code, tests,
examples, official documentation, releases, the issue tracker and API
definitions.

---

## License requirements

Every external project considered for integration must have its license identified.

Record at minimum:

* project
* repository URL
* license
* version/commit evaluated
* intended use
* whether it can legally be used as a dependency under this project's license
* whether linking, subprocess execution, API usage, or source reuse changes the licensing implications

Do not assume that two open-source licenses are automatically compatible.

This project must not incorporate code from another repository merely because
the repository is publicly available. See `CREDITS.md` for the current inventory.

---

## Reference versus dependency

There is a strict distinction between:

### Reference

The project is studied to understand an implementation. For example, studying
how `kicad-tools` parses a schematic does **not** make it a dependency.

### Dependency

The project is deliberately selected as part of the application's architecture.

A dependency must be explicitly documented in the project's dependency
configuration and architecture documentation:

```text
pyproject.toml
package.json
Dockerfile
requirements.txt
```

Moving a project from "reference" to "dependency" requires an explicit
architectural decision.

---

## Do not duplicate existing functionality without research

Before implementing a significant subsystem, search the project's research
documentation and the reference repositories list.

Examples:

* schematic parsing
* PCB parsing
* PCB routing
* ERC
* DRC
* SPICE integration
* component search
* KiCad automation
* Circuit IR
* 3D visualization
* collaboration
* MCP integration

If an existing open-source implementation appears relevant, document it before
writing a new implementation.

The goal is not to avoid writing code.

The goal is to avoid writing code that already exists, is inferior to an existing solution, or unnecessarily duplicates a mature open-source implementation.

---

## AI agents must preserve project boundaries

AI coding agents must treat the following directories differently:

```text
src/
    Project source code

research/
    Research reports, comparisons, experiments, technical notes

libs/
    Third-party binaries only (e.g. the FreeRouting jar); never project code

tests/
    Project tests

docs/
    Project documentation

external/  (does not exist)
    Was a submodule checkout of reference projects. Removed; do not recreate it
    as a dependency mechanism.
```

An agent must never treat code from a reference checkout as part of this
project's source tree.

---

## Reproducibility

Research conclusions should be reproducible.

When a significant conclusion depends on an external repository, record:

* repository
* URL
* commit or release
* date evaluated
* relevant file/path
* capability being evaluated
* evidence
* conclusion

Example:

```text
Project: kicad-tools
Repository: https://github.com/rjwalters/kicad-tools
Commit: <commit>
Evaluated: YYYY-MM-DD
Feature: Python DRC
Evidence: <file/path>
Status: Verified
```

When a research report depends on a particular version, record the evaluated
commit or version in the research documentation.

---

## Security

Reference repositories are untrusted until reviewed.

Do not automatically execute:

* installation scripts
* arbitrary shell scripts
* downloaded binaries
* unknown build scripts
* MCP servers
* Python programs
* package lifecycle scripts

merely because they are listed as references or exist locally.

AI agents must inspect code and documentation before executing unfamiliar external software.

Particular care is required for software that processes:

* KiCad project files
* datasheets
* PDFs
* downloaded component data
* MCP requests
* AI-generated code
* Python scripts
* shell commands

---

## Architectural principle

The project should follow this principle:

> Study existing open-source software first. Reuse mature capabilities where appropriate. Build only what is genuinely missing.

Installing a published package is preferred over vendoring.

Vendoring is preferred over reimplementing.

Reimplementing is a last resort, and must be justified in `research/`.

---

## Final rule

If there is uncertainty about whether an external project should become a dependency, **do not integrate it automatically**.

Document the project and the uncertainty in `research/`, then make an explicit architectural decision.
