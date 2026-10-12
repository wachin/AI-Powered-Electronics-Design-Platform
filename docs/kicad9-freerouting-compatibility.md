# KiCad 9 / FreeRouting Compatibility

## Issue

KiCad 7.0 (released 2023) removed the DSN export functionality from `kicad-cli`. This breaks the FreeRouting integration which relies on:
1. Exporting KiCad PCB to DSN format (`kicad-cli pcb export dsn`)
2. Running FreeRouting on the DSN file
3. Importing the routed SES file back to KiCad

## Current Status

| KiCad Version | DSN Export | FreeRouting |
|---------------|------------|-------------|
| 6.0.x | ✅ Supported | ✅ Works |
| 7.0+ | ❌ Removed | ❌ Fails |
| 8.0+ | ❌ Removed | ❌ Fails |
| 9.0+ | ❌ Removed | ❌ Fails |

## Error Message

```
⚠️  PCB auto-routing failed: KiCad 9.0.2 detected: DSN export was removed in KiCad 7+.
FreeRouting requires DSN format which is no longer supported.
Workarounds:
  1. Use KiCad's built-in interactive router (Route -> Auto Route)
  2. Use an external DSN converter (e.g., kicad-dsn-exporter)
  3. Install KiCad 6.x alongside for DSN export
  4. Use pcbnew Python scripting for custom routing
```

## Workarounds

### 1. KiCad's Built-in Interactive Router (Recommended)

Open the generated `.kicad_pcb` file in KiCad PCB Editor:
1. Open PCB Editor
2. Route → Auto Route (or press `Ctrl+Shift+A`)
3. Configure routing parameters
4. Run autorouter
5. Save

### 2. External DSN Converter

Use `kicad-dsn-exporter` (community tool):
```bash
# Install
pip install kicad-dsn-exporter

# Export DSN from KiCad 9 PCB
kicad-dsn-exporter input.kicad_pcb output.dsn

# Run FreeRouting
java -jar freerouting.jar -d output.dsn -o routed.ses

# Import back (requires KiCad 6 or SES importer)
```

### 3. KiCad 6.x Alongside

Install KiCad 6.0.x in parallel:
```bash
# Debian/Ubuntu
apt install kicad=6.0.*

# Or download from kicad.org/download
```

Use `kicad-cli` from KiCad 6 for DSN export only:
```bash
/path/to/kicad6/bin/kicad-cli pcb export dsn design.kicad_pcb -o design.dsn
```

### 4. pcbnew Python Scripting

Use KiCad's Python API for custom routing:
```python
import pcbnew

board = pcbnew.LoadBoard("design.kicad_pcb")
# Custom routing logic using pcbnew API
# Note: Full autorouter API not exposed in Python
board.Save("design_routed.kicad_pcb")
```

## Implementation Details

The platform handles this gracefully in `src/routing/freerouting.py`:

```python
def _export_dsn(self, pcb_path: Path, dsn_path: Path) -> RoutingResult:
    # 1. Check KiCad version via `kicad-cli --version`
    # 2. If major >= 7, return informative error with workarounds
    # 3. Otherwise, attempt DSN export
```

The orchestrator continues the pipeline even if routing fails:
```python
routing_result = route_kicad_pcb(pcb_path)
if routing_result.success:
    generated_files["pcb_routed"] = routing_result.routed_ses_path
else:
    print(f"   ⚠️  PCB auto-routing failed: {routing_result.error}")
    # Pipeline continues: BOM, 3D export, etc.
```

## Future Solutions

### Option A: KiCad Built-in Router via pcbnew
- Track KiCad development for Python autorouter API
- Implement when available

### Option B: FreeRouting SES Import
- FreeRouting can read/write SES directly
- Need KiCad SES import (available in kicad-cli)

### Option C: Alternative Autorouters
- **TopoR** (commercial, has KiCad integration)
- **Allegro** (Cadence, commercial)
- **Custom router** using pcbnew + optimization algorithms

### Option D: SPECCTRA DSN Alternative
- KiCad 9 may add alternative export formats
- Monitor KiCad release notes

## Testing

```bash
# Test routing on KiCad 9 (expects graceful failure)
python scripts/test_buck.py

# Verify error message is informative
grep "DSN export was removed" test_output.log
```

## Related Files

- `src/routing/freerouting.py` - FreeRouting integration
- `src/agents/orchestrator.py` - Pipeline orchestration (handles routing failure)
- `src/generators/kicad_generator.py` - KiCad PCB generation
- `scripts/test_buck.py` - Test script demonstrating the issue