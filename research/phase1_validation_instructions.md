# Phase 1 Validation Instructions

## What This Is

This document provides instructions to validate the core technical capabilities for building an AI-Powered Electronics Design Platform.

**⚠️ IMPORTANT: This is proof-of-concept validation, NOT production code.**

## Prerequisites

Before running validation, ensure you have:

1. **Python 3.10+** - For Python automation
2. **Node.js 18+** - For Circuit JSON converters
3. **KiCad 8+** - With CLI enabled (usually installed by default)
4. **Git** - To manage submodules

### Quick Setup

```bash
# Clone and initialize
git clone <repo-url>
cd AI-Powered-Electronics-Design-Platform

# Initialize submodules
git submodule update --init --recursive

# Install KiCad CLI tools
# KiCad 8+ includes kicad-cli by default

# Install Python automation
pip install pyknod

# Install component database (optional but recommended)
pip install jlcparts-fast
```

## Validation Script

The `poc_phase1_validation.py` script tests:

### 1. KiCad CLI Available
- Verifies `kicad-cli` command is accessible
- Checks version compatibility

### 2. Circuit JSON Converter
- Tests `circuit-json-to-kicad` via npx
- Validates basic conversion pipeline

### 3. tscircuit Tools
- Verifies Circuit JSON ecosystem
- Checks type definitions and schemas

### 4. Component Database
- Validates JLCPCB/CheapParts database
- Checks for local SQLite cache

### 5. SKiDL Integration
- Tests basic circuit definition in Python
- Validates component creation and connection

### 6. Circuit JSON to KiCad Conversion
- Creates a test circuit in Circuit JSON format
- Converts to KiCad project files
- Runs ERC to validate generated files

## Running the Validation

```bash
# Make executable
chmod +x poc_phase1_validation.py

# Run validation
python poc_phase1_validation.py
```

## Expected Output

```
============================================================
Phase 1 Validation: AI-Powered Electronics Design Platform
============================================================

🔍 Checking Prerequisites...
✅ KiCad CLI found: kicad-cli 9.0.0
✅ Circuit JSON to KiCad converter available (via npx)
✅ tscircuit available: 0.1.0
✅ JLCPCB database found: 2.5 MB
✅ SKiDL imported successfully
✅ Circuit JSON conversion succeeded

============================================================
VALIDATION SUMMARY
============================================================
KiCad CLI: ✅ PASS
Circuit JSON Converter: ✅ PASS
tscircuit: ✅ PASS
Component Database: ✅ PASS
SKiDL: ✅ PASS
Circuit JSON->KiCad: ✅ PASS

Total: 6 passed, 0 failed

🎉 All critical components are working!
The foundation for the AI-Powered Electronics Design Platform is ready.
```

## Troubleshooting

### KiCad CLI Not Found
```bash
# Install KiCad
# Ubuntu/Debian
sudo apt install kicad

# macOS
brew install kicad

# Verify
kicad-cli --version
```

### Circuit JSON Converter Fails
```bash
# Install Node.js if not present
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt-get install -y nodejs

# Test npx
npx circuit-json-to-kicad --help
```

### SKiDL Import Error
```bash
pip install skidl

# Verify
python -c "import skidl; print(skidl.__version__)"
```

### Component Database Missing
```bash
# Initialize jlcparts database
python -m jlcparts.init

# Or download manually
# See: https://github.com/yaqwsx/jlcparts
```

## What This Validates

### ✅ Critical Path Components

| Component | Why Critical | Status |
|-----------|--------------|--------|
| KiCad CLI | EDA engine backend | Validated |
| Circuit JSON | Canonical IR format | Validated |
| SKiDL | Circuit-as-code layer | Validated |
| Node.js | TypeScript ecosystem | Validated |
| jlcparts | Component database | Validated |

### ⚠️ Dependencies That Need Work

| Dependency | Status | Next Steps |
|------------|--------|------------|
| MCP servers | Available in external/ | Test integration |
| FreeRouting | Available | Test headless mode |
| ngspice | Bundled with KiCad | Test SPICE flow |
| Yjs | JS/TS only | Consider Python CRDT |

## Next Steps After Validation

1. **Create Integration Tests** - Write tests for circuit creation → KiCad → ERC flow
2. **Build MCP Wrapper** - Create Python wrapper for desired MCP functionality
3. **Design IR Layer** - Define Canonical IR schema for the platform
4. **Implement Validators** - Create deterministic validation after AI generation

## Technical References

- **Circuit JSON Schema**: `external/circuit-json/schema.ts`
- **KiCad CLI Docs**: KiCad documentation
- **SKiDL Documentation**: https://skidl.org
- **tscircuit**: https://tscircuit.com
- **jlcparts**: https://github.com/yaqwsx/jlcparts

## License Notes

All validated components are open-source:
- KiCad: GPL-3.0
- Circuit JSON: MIT
- SKiDL: MIT
- tscircuit: MIT

See `LEGAL_NOTICE.md` and `LEGAL_DISCLAIMER.md` for detailed licensing information.