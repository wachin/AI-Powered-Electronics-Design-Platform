# Circuit JSON → KiCad converter (abandoned prototype)

A `tscircuit`-based experiment that converted Circuit JSON into KiCad files.

**Superseded.** The project emits KiCad S-expressions directly from its own
Circuit IR (`src/generators/kicad_generator.py`), which avoids a second
intermediate format and keeps the toolchain in Python.

Kept as a record of the approach that was evaluated and rejected, not as a
working tool. Its `node_modules` was removed; the original experiment used `bun`.

Why it was abandoned:

* it required a JavaScript toolchain alongside the Python one;
* it introduced a second intermediate representation (Circuit JSON) on top of
  the project's own Circuit IR;
* reading KiCad's symbol and footprint libraries directly proved both simpler
  and more accurate — it guarantees pad numbers match the netlist, which is what
  makes a board fabricable.
