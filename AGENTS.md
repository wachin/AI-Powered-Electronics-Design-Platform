# AGENTS.md

# External Repositories Policy

## Purpose

The `external/` directory contains Git submodules with open-source projects that are being studied as **technical references** for the development of this project.

These repositories are included so that AI agents and developers can inspect their:

* source code
* architecture
* algorithms
* APIs
* data structures
* file formats
* protocols
* integration techniques
* tests
* documentation
* build systems
* implementation approaches

The purpose is to learn from existing open-source projects and avoid unnecessarily reinventing functionality that already exists in the ecosystem.

---

## IMPORTANT: `external/` is NOT a library directory

The `external/` directory must **not** be treated as the project's library, dependency, vendor, or source-code directory.

Do not:

* copy source files from `external/` into the main project
* import Python/TypeScript/C++/Java/etc. modules directly from `external/`
* add `external/` directories to application import paths
* modify external repositories to implement project functionality
* build the application by depending directly on arbitrary files inside `external/`
* create application code that assumes a particular external repository is present
* silently convert an external repository into a runtime dependency
* copy-paste large portions of external source code
* mix project source code with external repository source code

The presence of a repository inside `external/` does not mean that the project has adopted that repository as a dependency.

---

## LEGAL CONSIDERATIONS FOR FLUX.AI

**IMPORTANT: This project builds an AI Electronics Design Platform inspired by Flux.ai, but IS NOT a copy of it.**

### Patent Considerations

Flux.ai is a proprietary commercial product. Before any commercial distribution:

1. **SEARCH FOR PATENTS** - Refer to `research/flux-ai-patent-search.md`
2. **DO NOT COPY** - Never implement Flux.ai's specific algorithms or methods
3. **INDEPENDENT IMPLEMENTATION** - Write your own code from scratch

### Trademark Considerations

**DO NOT USE:**
- "Flux" in project name, domain, or branding
- Flux.ai logos, UI designs, or trademarks
- Claims like "Flux.ai clone" or "open-source Flux"

**SAFE REFENCES:**
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

## External repositories are references only

Every repository under `external/` should initially be considered:

> **REFERENCE ONLY**

An agent may inspect the repository to understand how a problem has been solved elsewhere.

For example, an agent may study:

* how KiCad represents a schematic
* how Circuit JSON represents a circuit
* how tscircuit converts Circuit JSON to KiCad
* how SKiDL generates netlists
* how atopile represents hardware constraints
* how kicad-tools parses KiCad files
* how KiCad MCP servers expose tools to AI agents
* how FreeRouting performs PCB routing
* how ngspice performs simulation
* how Yjs implements collaborative editing
* how component databases model electronic parts

The agent must not assume that the external implementation should be copied or directly integrated.

---

## No modifications to external repositories

Do not make changes inside a submodule under `external/` unless the user explicitly requests a separate experiment involving that repository.

In particular:

* do not edit files inside `external/`
* do not commit changes to an external repository
* do not create project-specific patches inside external repositories
* do not change their dependencies
* do not change their build configuration

If an experiment requires modifying an external project, create a separate experimental branch, fork, patch, or temporary working copy outside the normal project workflow.

---

## Do not depend on external repositories accidentally

Before introducing functionality into the main project, determine whether it should be:

1. implemented independently;
2. integrated through a documented public API;
3. invoked as an external executable;
4. used through a standard file format;
5. used through MCP;
6. used through a subprocess;
7. adopted as a formal project dependency.

Do not make this decision merely because a repository exists under `external/`.

The architecture must remain understandable and reproducible without requiring every research repository to be present.

---

## Research before integration

Before proposing an external repository as a real dependency, investigate:

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

Do not infer capabilities solely from the repository name, README title, GitHub stars, or marketing claims.

When possible, verify important capabilities by inspecting:

* source code
* tests
* examples
* official documentation
* releases
* issue tracker
* API definitions

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

This project must not incorporate code from an external repository merely because the repository is publicly available.

---

## Reference versus dependency

There is a strict distinction between:

### Reference

The project is studied to understand an implementation.

Example:

```text
external/kicad-tools/
```

An agent can inspect its parser, routing algorithms, DRC implementation, etc.

This does NOT make `kicad-tools` a project dependency.

### Dependency

The project is deliberately selected as part of the application's architecture.

A dependency must be explicitly documented in the project's dependency configuration and architecture documentation.

For example:

```text
pyproject.toml
package.json
Dockerfile
requirements.txt
```

or another appropriate dependency mechanism.

Moving a project from "reference" to "dependency" requires an explicit architectural decision.

---

## Do not duplicate existing functionality without research

Before implementing a significant subsystem, search the repositories under `external/` and the project's research documentation.

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

If an existing open-source implementation appears relevant, document it before writing a new implementation.

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

external/
    Reference repositories only

tests/
    Project tests

docs/
    Project documentation
```

An agent must never assume that code found under `external/` is part of the project's source tree.

---

## Git submodules

Repositories in `external/` are managed as Git submodules.

Do not:

* delete `.gitmodules`
* replace submodules with copied source trees
* commit modifications to submodule contents
* change a submodule's remote without explicit authorization
* recursively initialize unrelated repositories

To initialize the research repositories:

```bash
git submodule update --init --recursive
```

To update them intentionally:

```bash
git submodule update --remote --merge
```

Updates should be deliberate because research results may depend on a specific version or commit.

When a research report depends on a particular version, record the evaluated commit or version in the research documentation.

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

---

## Security

External repositories are untrusted until reviewed.

Do not automatically execute:

* installation scripts
* arbitrary shell scripts
* downloaded binaries
* unknown build scripts
* MCP servers
* Python programs
* package lifecycle scripts

simply because they exist in an external repository.

AI agents must inspect code and documentation before executing unfamiliar external software.

Particular care is required for repositories that process:

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

The `external/` directory exists to make that research practical.

It does not exist to become a dumping ground for libraries.

It does not exist to become a vendor directory.

It does not exist to become an alternative package manager.

It exists strictly as a **reference library for technical research**.

---

## Final rule

If there is uncertainty about whether an external repository should become a dependency, **do not integrate it automatically**.

Document the repository and the uncertainty in `research/`, then make an explicit architectural decision.
