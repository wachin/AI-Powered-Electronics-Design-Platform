# Contributing

Short version: read **[`docs/development.md`](docs/development.md)** — it has the
setup, the commands, the module map, the extension recipes and the pitfalls. If
you are an AI agent, [`AGENTS.md`](AGENTS.md) also applies, and it is loaded
automatically by most tools.

## Getting set up

```bash
python3 -m venv venv
venv/bin/pip install -e ".[dev]"
venv/bin/ai-electronics-design --diagnose     # what this machine can do
make test                                     # the suite, without the catalog
```

Optional but needed for the full picture:

| What | Why | How |
|---|---|---|
| KiCad 9 | Symbols, footprints, ERC, Gerbers | your package manager |
| ngspice | Simulation | your package manager |
| Java 25 + FreeRouting jar | Routing | see `docs/installed_tools.md` |
| The component catalog (146 MB) | Real part numbers, prices, stock | `make catalog` |

## Before you open a pull request

```bash
make lint && make compile-check && make test
make test-catalog CATALOG=/path/to/jlcparts.sqlite3   # if you have the catalog
```

Both test runs matter: without the catalog some tests skip, and a change that
only passes one way is broken.

## What a change is expected to include

* **A test that fails without the change.** Prefer one that reads the real
  artifact — the installed KiCad library, the generated Gerber, the catalog — over
  one that restates an internal table.
* **`README.md`** updated for anything user-visible, including the limitations it
  does not solve.
* **`ROADMAP.md`** updated with what was done, the evidence, and what stays open.
  An `[ ] **OPEN**` item with a reason is worth more than a feature claimed and
  not finished.

## The rules that get a change rejected

Six of them, in [`AGENTS.md`](AGENTS.md#what-this-codebase-demands-of-a-change).
The short reason: almost every bug in this project came from a plausible value
that nobody checked — 26 invented KiCad symbol names, 5 template symbols that do
not exist, 7 part numbers that were never in the catalog. Each produced a design
that looked complete and could not be built.

If you cannot check something, say you cannot check it. `[?]` with a reason is a
correct answer; `✅` you did not earn is not.

## Licences

This project is GPLv3. It studies other open-source EDA projects as references;
they are **not** dependencies and are never vendored. `CREDITS.md` has the
inventory, and `AGENTS.md` has the rules — including why no code from a reference
checkout may enter `src/`.
