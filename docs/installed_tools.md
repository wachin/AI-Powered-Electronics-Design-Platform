# Installed EDA Tools Documentation

## Currently Installed (via apt)

| Tool | Version | Status | Purpose |
|------|---------|--------|---------|
| **KiCad** | 9.0.2+dfsg-1 | ✅ Installed | Primary EDA engine (schematic, PCB, ERC, DRC, Gerber) |
| **LibrePCB** | 1.2.0 | ✅ Installed | Alternative EDA engine |
| **Horizon EDA** | 2.6.0 | ✅ Installed | Alternative EDA engine |
| **libngspice0** | 44.2+ds-1 | ✅ Installed (library) | SPICE simulation library |
| **ngspice** | 44.2+ds-1 | ✅ Installed | SPICE simulation CLI |
| **ngspice-dev** | 44.2+ds-1 | ✅ Installed | SPICE development headers |
| **ngspice-doc** | 44.2+ds-1 | ✅ Installed | SPICE documentation |
| **sch-rnd-sim** | 1.0.0+git | ✅ Installed | High-level circuit simulation |
| **kicad-libraries** | 9.0.2+dfsg-1 | ✅ Installed | KiCad libraries meta-package |
| **kicad-footprints** | 9.0.2+dfsg-1 | ✅ Installed | KiCad footprint libraries |
| **kicad-symbols** | 9.0.2+dfsg-1 | ✅ Installed | KiCad symbol libraries |
| **kicad-templates** | 9.0.2+dfsg-1 | ✅ Installed | KiCad project templates |
| **pcb-rnd** | 3.0.0+dfsg | ✅ Installed | Alternative PCB tool |
| **LibrePCB** | 1.2.0 | ✅ Installed | Alternative EDA engine |
| **Horizon EDA** | 2.6.0 | ✅ Installed | Alternative EDA engine |
| **libngspice0** | 44.2+ds-1 | ✅ Installed (library) | SPICE simulation library |

## Not Yet Installed (Needed)

| Tool | Status | Installation Method |
|------|--------|---------------------|
| **freerouting** | ❌ Not in apt | Build from source: `cd external/freerouting && ./gradlew build -x test` |

## Available in external/ submodules

| Tool | Location | Build Method |
|------|----------|--------------|
| **freerouting** | `external/freerouting/` | `./gradlew build -x test` (produces freerouting.jar) |
| **ngspice** | `external/ngspice/` | `./autogen.sh && ./configure && make` |
| **kicad-mcp-server** | `external/kicad-mcp-server/` | `pip install -e .` |
| **kicad-tools** | `external/kicad-tools/` | `pip install -e .` |
| **pcbparts-mcp** | `external/pcbparts-mcp/` | `pip install -e .` |
| **circuit-json-to-kicad** | `external/circuit-json-to-kicad/` | `npm install` |

## KiCad Installation

**Current Installation**: KiCad 9.0.2 installed via apt (`kicad` package)

### KiCad Installation Methods

| Method | Command | Notes |
|--------|---------|-------|
| **apt (current)** | `sudo apt-get install kicad` | Version 9.0.2 (Debian Trixie) |
| **Flatpak** | `flatpak install flathub org.kicad.KiCad` | Often newer version |
| **Snap** | `snap install kicad` | Alternative |
| **AppImage** | Download from kicad.org | Manual |

### Verification

```bash
# Check KiCad version
kicad --version

# Check KiCad CLI
kicad-cli --version

# Check if all modules available
kicad-cli sch --help
kicad-cli pcb --help
```

## Recommended Additional Installations

```bash
# Install ngspice CLI (for SPICE simulation)
sudo apt-get install ngspice

# Build freerouting from source (required for PCB auto-routing)
cd external/freerouting && ./gradlew build -x test

# Install Python MCP tools
pip install -e external/kicad-mcp-server
pip install -e external/kicad-tools
pip install -e external/pcbparts-mcp

# Install circuit-json-to-kicad converter
cd external/circuit-json-to-kicad && npm install
```

## Python Dependencies (for AI agent)

```bash
pip install -r requirements.txt
```

## Summary of Current State

✅ **Installed & Working:**
- KiCad 9.0.2 (primary EDA engine)
- LibrePCB 1.2.0 (alternative)
- Horizon EDA 2.6.0 (alternative)
- libngspice0 (SPICE library)

⚠️ **Needs Installation:**
- ngspice CLI (`sudo apt-get install ngspice`)
- freerouting (build from `external/freerouting/`)

📦 **Available in external/ (need build/install):**
- freerouting (Gradle build)
- ngspice (autotools build)
- kicad-mcp-server (pip install -e)
- kicad-tools (pip install -e)
- pcbparts-mcp (pip install -e)
- circuit-json-to-kicad (npm install)

## Python Dependencies (for AI agent)

```bash
pip install -r requirements.txt
```
