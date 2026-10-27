# Developing this platform

This is the guide for anyone — human or AI agent — making changes to this
repository. `AGENTS.md` holds the non-negotiable policy (reference repositories,
licensing, Flux.ai). This file holds the practical detail: how to set up, how to
run things, where the code lives, and what this codebase expects of a change.

If you are an AI agent, read this file and `AGENTS.md` before your first edit.
The section [The rules this codebase follows](#the-rules-this-codebase-follows)
matters more than the rest: almost every bug found in this project came from a
plausible value that nobody checked, and those rules exist to stop that.

---

## Setting up

### Prerequisites

| Tool | Why | Verified version |
|---|---|---|
| Python 3.10+ | The application | 3.13.5 |
| KiCad **9** | Symbols, footprints, ERC, DRC, Gerbers | 9.0.2 |
| ngspice | Simulation (`--no-spice` skips it) | 44.2 |
| Java 17+ | FreeRouting (`--no-routing` skips it) | OpenJDK 25 |
| Node 20+ | Only for the web frontend | — |

`ai-electronics-design --diagnose` prints what it found and what is missing.
Nothing below fails hard when an optional tool is absent: the corresponding stage
is skipped and says so.

**KiCad 9 specifically, not "a recent KiCad".** The generated board uses the 8/9
file format and the symbol and footprint readers target the 9 libraries; KiCad 7
rejects every board with `Unknown token 'generator_version'` and resolves no
symbols. On an older version the KiCad tests skip with the version in the message
rather than failing, and `--diagnose` flags it. On Debian or Ubuntu without 9:

```bash
sudo add-apt-repository --yes ppa:kicad/kicad-9.0-releases
sudo apt-get update && sudo apt-get install -y kicad
```

### Install

```bash
python3 -m venv venv
venv/bin/pip install -e ".[dev]"     # editable install, so src/ changes apply at once
venv/bin/ai-electronics-design --diagnose
```

Do not use the system Python. Use `venv/bin/python` for everything: `venv/bin/python -m pytest`,
`venv/bin/python -m src.cli ...`.

**Trap:** `pcbnew` (the KiCad Python module, used for DSN export and SES import in
routing) is **not** in the venv — the venv's Python cannot see the distribution's
modules. The code knows this and looks for a Python that has `pcbnew`
(`src/agents/mcp_registry.find_pcbnew_python`). Do not "fix" this by installing
`pcbnew` into the venv from PyPI; it is part of KiCad, not a separate package.

### The component catalog (optional, 146 MB)

The catalog is the single source of part numbers, prices and stock. It is never
versioned, and everything that needs it skips cleanly when it is absent.

```bash
venv/bin/ai-electronics-design catalog-setup     # downloads it
```

Discovery order: `$JLC_PARTS_CATALOG`, then a repository-relative path, then
`$XDG_CACHE_HOME/kicad-tools/jlcparts.sqlite3`. Point `JLC_PARTS_CATALOG` at a
catalog kept elsewhere:

```bash
JLC_PARTS_CATALOG=/path/to/catalog.sqlite3 venv/bin/ai-electronics-design --diagnose
```

Without a catalog the 36 component templates still work: they carry symbol,
footprint, package and value — but no part number, price or stock, and the output
says so rather than inventing them.

---

## Commands

`make help` lists these. Each one is also a plain command you can run directly.

| Command | What it does |
|---|---|
| `make test` | The full suite without the catalog (~2–4 min) |
| `make test-catalog` | The full suite against the real catalog |
| `make test-file F=tests/test_erc.py` | One file |
| `make demo` | Build a design into `output_design/demo` |
| `make diagnose` | What tooling is installed |
| `make compile-check` | Byte-compile everything (what CI does) |
| `make lint` | Ruff: undefined names, unused imports, shadowed definitions, duplicated dictionary keys |
| `make frontend` | Build the web frontend |
| `make clean` | Remove generated output and caches |

The runner is always the venv's Python:

```bash
make test                                                  # 911 passed, 15 skipped
make test-catalog CATALOG=/path/to/jlcparts.sqlite3        # 923 passed, 3 skipped
```

The difference is the tests that need real parts; they `pytest.skip` with
`JLC_PARTS_CATALOG is not set to a real catalog` when it is absent. **Both runs
must pass.** A change that only passes with a catalog is broken for CI, and a
change that only passes without one is lying about the catalog path.

---

## How a design is built

One pipeline, six stages. Each stage has one job and hands over a value the next
stage can check.

```
prompt
  │
  ├─ 1. parse ......... RequirementParser            src/llm/integration.py
  │        natural language → CircuitRequirement
  │        (rule-based when there is no model; asks about gaps when a
  │         terminal is attached — src/llm/clarification.py)
  │
  ├─ 2. specify ....... CircuitSpecificationGenerator  src/llm/integration.py
  │        requirement → roles, values, packages, connections
  │
  ├─ 3. build ......... CircuitBuilder                src/core/circuit_builder.py
  │        spec → CircuitIR (components, pins, nets)
  │        ComponentResolver: role → type → symbol, footprint, pinout
  │                          src/core/component_resolver.py
  │
  ├─ 4. validate ...... ERC                           src/core/erc.py
  │        + repair loop, bounded
  │
  ├─ 5. review ........ DesignReview                  src/core/design_review.py
  │        dissipation, dropout, voltage stress, LED point
  │        (computed against real catalog attributes)
  │
  └─ 6. emit .......... KiCadGenerator                src/generators/kicad_generator.py
           schematic, footprint assignment, placement (src/pcb/),
           net classes (src/pcb/netclasses.py), routing (src/routing/),
           BOM + purchase list (src/components/ordering.py),
           Gerbers + drill + position file (src/generators/fabrication.py)
```

`src/agents/orchestrator.py` runs the stages, and its step numbers (`Step 2b`,
`Step 7b`) are what you see on the console.

### Where things live

| Path | Responsibility | Notable entry points |
|---|---|---|
| `src/core/circuit_ir.py` | The data model everything else agrees on | `CircuitIR`, `Component`, `Net`, `Pin` |
| `src/core/circuit_builder.py` | Spec → IR | `CircuitBuilder.build` |
| `src/core/component_resolver.py` | Role → component type → symbol, footprint, **pinout** | `resolve_pins`, `_IC_PINOUTS`, `role_to_component_type` |
| `src/core/erc.py` | The electrical rules | `_check_unconnected_pins`, `_check_led_current_limiting`, … |
| `src/core/design_review.py` | Numbers, not adjectives | `review_circuit`, `review_linear_regulator_thermal` |
| `src/components/jlcparts.py` | The catalog: search, lookup, substitutes | `JLCPart`, `search_explained`, `_category_to_symbol` |
| `src/components/parameters.py` | Catalog attribute strings → values | `parse_value`, `parse_conditional`, `extract_parameters` |
| `src/components/parametric.py` | Numeric queries ("10k 1% 0805") | `parse_query`, `ParametricIndex` |
| `src/components/ordering.py` | Purchase list and `bom.csv` | `build_purchase_list`, `order_quantity_for` |
| `src/components/database.py` | Catalog + the 36 templates | `ComponentDatabase`, `_load_component_templates` |
| `src/llm/integration.py` | Parse, specify, repair | `RequirementParser`, `CircuitSpecificationGenerator` |
| `src/llm/clarification.py` | Ask instead of guessing | `clarifications_for`, `fill_defaults` |
| `src/generators/kicad_generator.py` | Writes `.kicad_sch`, `.kicad_pcb`, `.kicad_pro` | `generate_project_config` |
| `src/generators/kicad_symbols.py` | Reads the installed KiCad symbol libraries | `load_symbol` |
| `src/generators/kicad_footprints.py` | Reads footprints and their pads | `load_footprint` |
| `src/generators/fabrication.py` | Gerbers, drill, position file | `export_fabrication` |
| `src/pcb/netclasses.py` | Trace width from current (IPC-2221) | `trace_width_mm`, `build_net_settings` |
| `src/routing/freerouting.py` | Routing, and the widths it produced | `route_pcb`, `RoutingResult.routed_widths` |
| `src/agents/orchestrator.py` | Runs the pipeline, writes the BOM and purchase list | `process_request`, `board_to_manufacture` |

The `src/models`, `src/services` and `src/schemas` packages are empty placeholders.
`src/security/permissions.py`, `src/security/sandbox.py` and
`src/agents/ai_agent.py` are implemented and tested but **not wired into the
pipeline**; do not assume they run.

---

## The rules this codebase follows

These are not style preferences. Each one exists because the opposite was tried
and produced a bug that looked fine.

### 1. Never invent a value that can be looked up

A symbol name, a footprint name, a part number, a price, a junction temperature,
a pin number — if the answer is knowable, look it up; if it is not, say it is not
known.

*This rule has a body count.* An earlier version invented 26 KiCad symbol names
(`Regulator_Linear:LDO_Generic` and friends), 5 of the 36 templates pointed at
symbols that do not exist, and 7 part numbers that were not in the catalog. Each
one produced a design that looked complete and could not be built. The tests in
`tests/test_kicad_names.py` now read the installed libraries, because an internal
table can only be checked against reality.

### 2. A check you cannot complete is `[?]`, not `✅`

The electrical review reports three states: `ok`, `fail`, and `unknown` with the
reason. It does not assume a datasheet figure to keep the output uniform. When
the part in the catalog did not state a junction temperature limit, the review
said so and named the value the design would need — it did not pick one.

Corollary: **do not assume θJA.** It depends on package, copper area, layer count
and airflow. The review reports the thermal path the design *requires*, and only
gives a verdict outside plausible ranges, saying it is a heuristic.

### 3. Report, never hide

If a router narrows a trace below its net class, that is a warning, not a silent
adjustment. If a purchase line matches a different part number than the design
names, the line is flagged with the two part numbers. If a value was assumed,
the console prints `Assumed: no input voltage was stated; assumed 5 V`.

Nothing in this project is allowed to reduce a real problem to a green tick.

### 4. Prefer the real tool to a reimplementation

KiCad for symbols, footprints, ERC, Gerbers; `kicad-cli` for plotting; FreeRouting
for routing; ngspice for simulation. This project writes its own KiCad files, its
own circuit model and its own analysis, and shells out to `kicad-cli` for
plotting — it does not reimplement a plotter.

### 5. A test that reads reality beats a test that restates the code

`assert db.lookup("C4001").symbol == "Regulator_Linear:LDO_Generic"` passed for
weeks while the symbol did not exist. A test that opens the KiCad library cannot
pass like that. When a fact lives in an external tool or file, the test should
read that tool or file.

### 6. Prove the claim you put in the docs

The README once said Gerber export was done. It had been *run by hand once*;
there was no code producing Gerbers and no position file. If you document a
capability, either there is a test that fails without it, or the docs say
"verified manually on <date>".

---

## Testing

31 files under `tests/`. They are organised by subsystem, and a few read the
outside world:

| File | What it pins |
|---|---|
| `test_erc.py` | Every electrical rule, and that a valid design passes |
| `test_topologies.py` | **Each offered topology builds and validates** |
| `test_kicad_names.py` | Every symbol and footprint exists in the installed KiCad |
| `test_design_review.py` | Thermal, dropout, stress arithmetic |
| `test_ordering.py` | Order quantities, price tiers, substitution warnings |
| `test_fabrication.py` | Gerbers, drill, position file, BOM↔CPL consistency |
| `test_parametric_search.py` | Numeric queries and their explanations |
| `test_prompt_parsing.py`, `test_clarification.py` | What is read, what is asked, what is assumed |
| `test_netclasses.py` | Width from current, and that widths reach the board |
| `test_api_components.py` | The HTTP surface |

Patterns used throughout, and worth copying:

* **Skip cleanly when the outside world is absent.** `pytest.skip("JLC_PARTS_CATALOG
  is not set to a real catalog")`, `shutil.which("kicad-cli") is None`. CI runs
  both ways.
* **Compare against the real artifact.** Open the Gerber and look for draw
  operations; open the symbol and read its pins; run the router and compare the
  widths it produced.
* **Test the failure path.** A nonexistent board must produce an error message,
  not a traceback. A part missing from the position file must be reported.
* **Pin a defect by name once it is fixed**, so it cannot come back unnoticed
  (`tests/test_prompt_parsing.py::TestDeterministicMode`).

Run one file while iterating:

```bash
venv/bin/python -m pytest tests/test_fabrication.py -q
```

Some tests take 20–60 s (anything invoking `kicad-cli` or the full pipeline).
That is normal.

---

## Recipes

### Add a topology

1. `src/llm/integration.py`: write `_spec_<name>(self, req) -> Dict[str, Any]`
   returning `topology`, `components` (with `role`, `value`, `package`,
   `reasoning`), `connections`, `design_notes`, `warnings`.
2. Name the topology in the controller's role — `buck_controller`, not
   `controller`. A bare `controller` resolves to a generic chip with no category,
   therefore no symbol and no pins, and every connection to it is dropped.
3. Add the dispatch in `CircuitSpecificationGenerator.generate`.
4. Map the topology to the `CircuitIR` topology in `_spec_to_circuit_ir`.
5. Add the prompt to `PROMPTS` in `tests/test_topologies.py`. It must build,
   validate, and leave no component without pins or symbol.

### Add or change a component template

`src/components/database.py`, `_load_component_templates()`. A template carries
`mpn=""` and no manufacturer, price or stock — those come from the catalog only.
The symbol and footprint must exist in KiCad; `tests/test_kicad_names.py` fails
otherwise. A template that has no resolvable pinout is allowed only for parts the
platform genuinely does not know (the three MCUs) and is listed by name in that
test.

### Fix or add a pinout

`src/core/component_resolver.py`, `_IC_PINOUTS`. Read the pin numbers **from the
symbol**:

```bash
venv/bin/python -c "
from src.generators.kicad_symbols import load_symbol
for pin in load_symbol('Regulator_Linear:LD1117S33TR_SOT223').pins:
    print(pin.number, pin.name)"
```

Keys are matched as substrings against the symbol lib_id or the MPN. Pin *names*
matter: KiCad resolves by name, so a made-up name on a real symbol produces a
broken schematic. Aliases live in `_PIN_ALIAS_GROUPS`.

### Add a catalog category

1. `src/components/jlcparts.py`: the category has to survive
   `_CATALOG_CATEGORY_MAP` / `_INTERNAL_TO_CATALOG`, and pass through the PMIC
   refinement if it is a power part.
2. `_category_to_symbol` needs a **real** KiCad symbol; add the category to
   `CATEGORIES` in `tests/test_kicad_names.py` and it will be checked.
3. If a design will connect to it by role name, add its pins to `_IC_PINOUTS`.
4. Add its searchable attributes in `src/components/parameters.py` and its
   `primary_field` in `src/components/parametric.py`.

### Add an electrical review rule

`src/core/design_review.py`: write `review_<thing>()` returning `Finding`s, and
call it from `review_circuit`. Attributes come from `_review_attributes`, which
resolves the catalog part and reports where each figure came from — an assumption
you add there shows up in the console, so make it a true statement. Severity
`UNKNOWN` is a first-class answer; use it when the data is not there.

### Add an ERC rule

`src/core/erc.py`: a `_check_<name>() -> List[ERCIssue]` method, called from
`validate`. Error means the design must not be built; warning means it can be,
with a caveat. The repair loop uses these messages, so write them as instructions.

### Add a CLI flag

`src/cli.py`, then pass it through `DesignRequest` in
`src/agents/orchestrator.py`. Update `make help` if it is a common one, and the
CLI section of `README.md`.

---

## Pitfalls

Each of these has cost someone an afternoon.

| Symptom | Cause |
|---|---|
| `symbol library not found for: U1 (...)` | The symbol name is not in the installed KiCad libraries. KiCad has **no generic IC symbols**; use a real part's symbol as an archetype and read its pins. |
| `U1 has no pin 'VIN' (available: [])` | The component resolved no pinout: check its component type (a bare `controller` role does not resolve) and that its symbol has a `_IC_PINOUTS` key. |
| A design with 10+ `CONNECTION_INVALID` errors | A component with no pins. Find it with `[ref for ref, c in ir.components.items() if not c.pins]`. |
| The 12 V prompt produces a 5 V design | The mock provider returns canned requirements. `deterministic=True` is what makes it read the prompt. |
| `ModuleNotFoundError: pcbnew` | Expected in the venv. Routing uses the system Python that has `pcbnew`. |
| Catalog tests skip | `JLC_PARTS_CATALOG` is unset or points at a nonexistent file. |
| `LIKE '%10k%'` matching 110k | Numeric values must go through `parametric.py`, not SQL text search. |
| Gerbers with pads and no tracks | The unrouted board was plotted. Use `board_to_manufacture`, which prefers the routed board. |
| `Assumed: ...` appears when you wanted a question | There is no terminal: `--ask` forces it, and the default is to ask only when stdin is a TTY. |

---

## Before you commit

```bash
make compile-check
make test                       # without the catalog
make test-catalog               # with it
```

Then, for anything user-visible:

* `README.md` — the feature, and its honest limitations;
* `ROADMAP.md` — what was done, with the evidence, and what is still open;
* a test that fails without your change.

Two documentation habits this project keeps, and reviewers ask for:

* **Say what was measured.** "The routed board's copper Gerber contains 25 draw
  operations and the unrouted one contains none" is a reason; "prefer the routed
  board" is an opinion.
* **Keep the open items open.** A `[ ] **OPEN**` in `ROADMAP.md` with the reason
  is worth more than a feature claimed and not finished.
