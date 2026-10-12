# FreeRouting (downloaded binary)

This directory holds the FreeRouting autorouter jar, which is **not** bundled
with any Python package and is **not** committed to this repository (see
`.gitignore`).

## Install

```bash
# Java 25 is required: the jars are compiled to class-file version 69.
sudo apt install -y openjdk-25-jdk

# Get the jar from the FreeRouting releases page
# https://github.com/freerouting/freerouting/releases
cp /path/to/freerouting.jar libs/freerouting/freerouting.jar
```

`src/routing/freerouting.py` looks for the jar in this order:

1. `$KICAD_MCP_FREEROUTING_JAR`
2. `libs/freerouting/freerouting.jar` (this directory)
3. `~/.local/share/freerouting/freerouting.jar`

Java is discovered separately (`JAVA_HOME`, then `/usr/lib/jvm/java-*`), and a
Java 25+ runtime is selected without changing your system default.

## Verify

```bash
python -m pytest tests/test_freerouting.py -q

python - <<'PY'
from pathlib import Path
from src.routing.freerouting import route_kicad_pcb
result = route_kicad_pcb(Path("output_design/<project>.kicad_pcb"))
print(result.success, result.routed_pcb_path, result.error)
PY
```

## License

FreeRouting is GPL-3.0. It is invoked as a separate process, which keeps license
separation from this project. See `CREDITS.md`.
