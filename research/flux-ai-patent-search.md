# Patent Search and Independent-Implementation Verification

**Purpose of this file:** to make it easy for *anyone* — users, contributors,
distributors, or reviewers — to locate patents held by Flux.ai and compare them
against this repository, and to see for themselves that no Flux.ai code,
algorithms, documentation, or other material was used.

**This is NOT legal advice.** Consult a qualified attorney for patent matters.

---

## 1. What this document is, and what it is not

**This document is a due-diligence aid and a transparency record.** It exists so
that the claim "this project is an independent implementation" is *checkable*
rather than merely asserted.

**This document is not:**

* an admission that any Flux.ai patent has been read, used, or relied upon;
* a statement that Flux.ai holds any particular patent (see §3);
* a "how to avoid getting caught" guide;
* a claim that this project is free of patent risk (no software project can
  truthfully claim that — see §7).

Flux.ai is a proprietary commercial product. This project studies publicly
documented *features* and *architecture* of commercial EDA platforms, and it
studies the source code of **open-source** EDA projects (see §5). It does not
use Flux.ai's source code, and no Flux.ai source code is present in this
repository.

Terminology used in this repository, per `AGENTS.md`:

* "inspired by Flux.ai" — a statement of product intent and feature study
* "similar architecture to commercial EDA platforms" — a statement about
  general EDA architecture, which predates Flux.ai
* Flux.ai is **not** a dependency, is **not** vendored, and is **not** linked

---

## 2. Positive evidence of independent implementation

Reviewers who want to verify independence in the codebase itself can check the
following. Each claim below is verifiable with the commands shown.

**No Flux.ai code is present.**

```bash
# No imports from the reference repositories, and no 'flux' references in source
grep -rn "import external\|from external" src/ main.py     # -> no matches
grep -rin "flux" src/ --include=*.py                       # -> no matches
```

**No third-party EDA project is vendored as a library.** The repositories under
`external/` are Git submodules used strictly as read-only technical references
(`AGENTS.md` states this policy). No application code imports them or assumes
they are installed.

**External tools are invoked as subprocesses, not linked.** KiCad (`kicad-cli`)
is called as an external executable for netlist export, ERC, DRC and
Gerber/drill export. That process boundary is deliberate and is recorded in
`CREDITS.md`.

**The subsystems have documented, non-Flux origins.** See §5 for the
module-by-module mapping to the open-source projects that informed each one.

**Development history is public.** This repository's Git history records when
each component was written and how it changed. Commit history is the primary
evidence of independent development.

---

## 3. Why this document does not list patent numbers

Earlier revisions of this file contained a table of "found" patents with numbers
such as `US111234567`. **Those numbers were invented placeholders**, not real
patents. Publishing invented patent numbers is worse than publishing none: it
misleads readers who trust the document, and it can look like evidence of
something that did not happen.

They have been removed. This file now contains **no patent numbers at all**,
because the maintainers have not conducted a comprehensive, citable patent
search. `LEGAL_NOTICE.md` says the same thing and should be kept consistent with
this file.

What this file provides instead is a **repeatable search procedure** (§4) and a
**comparison method** (§6) so that anyone — including a patent attorney — can
produce an authoritative list themselves.

---

## 4. How to search

### Primary patent databases

| Database | URL | Access | Coverage |
|---|---|---|---|
| Google Patents | https://patents.google.com | Free, public | USPTO, EPO, WIPO and others; good for citation/prior-art analysis |
| USPTO Patent Public Search | https://ppubs.uspto.gov | Free, public | United States patents and applications |
| USPTO Assignment Search | https://assignment.uspto.gov | Free, public | Ownership/assignment records |
| EPO Espacenet | https://worldwide.espacenet.com | Free, public | Worldwide coverage |

### Suggested search terms

```
("Flux.ai" OR "Flux Laboratory" OR "Flux Lab Inc")
  AND ("PCB" OR "circuit" OR "electronic design" OR "EDA")
```

```
("AI circuit design" OR "automated PCB routing" OR
 "machine learning circuit" OR "neural network EDA")
```

Also try assignee searches for "Flux Lab Inc.", "Flux Laboratory" and "Flux".

### Suggested procedure

1. **Google Patents** — search the terms above; filter by date, assignee and
   status (granted/pending). Record the exact query and date.
2. **USPTO Assignment Search** — look for assignments to "Flux Lab Inc." to
   discover patent numbers not surfaced by keyword search.
3. **Patent families** — for any relevant hit, check continuations, divisionals
   and continuations-in-part, which share a priority date.
4. **Record findings with citations** — patent number, title, filing/grant
   dates, assignee, and the URL you used. A dated copy or screenshot is more
   useful than a bare note.

### Landscaping tools

Free: Google Patents Public Datasets (BigQuery), Lens.org, FreePatentsOnline.
Commercial: Derwent Innovation, PatBase, Orbit Intelligence.

---

## 5. Where each subsystem's ideas came from

This section exists so a reviewer can check the provenance of each part of the
codebase directly against open-source projects — rather than having to take the
project's word for it.

| Subsystem | Module | Primary open-source references studied |
|---|---|---|
| Circuit intermediate representation | `src/core/circuit_ir.py` | Circuit JSON, tscircuit, KiCad schematic/netlist formats |
| ERC (electrical rule checking) | `src/core/erc.py` | KiCad ERC rules and general EDA practice |
| Component/part database | `src/components/` | jlcparts (JLCPCB/LCSC catalog), KiCad symbol/footprint conventions |
| Schematic & PCB emission | `src/generators/` | KiCad S-expression file formats; KiCad symbol and footprint libraries |
| SPICE simulation | `src/simulation/ngspice.py` | ngspice (subprocess) |
| PCB routing | `src/routing/freerouting.py` | FreeRouting (subprocess) |
| LLM pipeline | `src/llm/` | General LLM provider APIs (Ollama, OpenAI-compatible, Anthropic); JSON Schema |
| MCP / agent interface | `src/agents/` | Model Context Protocol, kicad-mcp-server |

`research/repository_catalog.md` records the repositories evaluated for each
area. `AGENTS.md` states the project's boundary policy for `external/`.

The intent of this table is transparency, not a claim that these are the only
influences. The point a reviewer can verify is that the influences are
**open-source projects with identifiable licenses**, not Flux.ai.

---

## 6. How to compare a patent against this repository

If you find a Flux.ai patent, this is a way to evaluate it against the code:

1. Read the **claims**, not the abstract. Claims define the legal scope.
2. Identify the claimed elements and the priority date.
3. For each claimed element, search this repository for a corresponding
   implementation. Useful starting points:
   - `src/core/` — circuit representation, ERC
   - `src/generators/` — schematic/PCB emission
   - `src/llm/` — natural language to specification
   - `src/routing/`, `src/pcb/` — placement and routing
4. Note where this project's approach differs, and where it is simply absent.
5. Check whether the technique in question is **general prior art** that long
   predates the patent (routing, ERC/DRC, netlists, BOM generation and schematic
   capture all predate Flux.ai by decades).
6. Write down your conclusion with citations, and the date you reached it.

A useful outcome of this exercise — for a reviewer — is a concrete statement of
the form: "patent X claims A, B and C; this repository does not implement B or
C, and its implementation of A uses approach Y from open-source project Z."

---

## 7. Honest limits of this document

* The maintainers have **not** conducted a comprehensive, citable patent search.
* The **absence** of a patent from a public database does **not** mean it does
  not exist, and does **not** guarantee freedom to operate. Applications may be
  unpublished for up to 18 months.
* Patent scope is a legal question. Only a qualified attorney can give an
  opinion on infringement or validity.
* Nothing here should be read as a legal warranty of any kind.

**When legal counsel is genuinely warranted:** before commercial distribution or
a funding round; if you find a patent that appears to cover functionality you
intend to ship; if a rights holder contacts you.

---

## 8. History of this file

* Earlier revisions listed example patent numbers. Those were **placeholder
  inventions**, not real patents, and were never the result of a search. They
  have been removed to avoid misleading any reader.
* The file was retitled and reframed: its purpose is to let anyone **verify
  independence for themselves**, not to imply that material was taken from
  Flux.ai or that the project is seeking to work around specific claims.

---

## 9. Disclaimer

This document is informational only and is **not legal advice**. It records
where to look for patents, how to compare them against this repository, and
which open-source projects informed each subsystem. It does not replace
consultation with a qualified patent attorney.
