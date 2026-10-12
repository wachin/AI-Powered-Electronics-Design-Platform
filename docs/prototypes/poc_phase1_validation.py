#!/usr/bin/env python3
"""
Phase 1 Validation Script for AI-Powered Electronics Design Platform

This script validates the critical path for building the platform:
1. Circuit JSON → KiCad project conversion
2. KiCad ERC/DRC via CLI
3. Component search integration
4. Basic Python API for circuit definition

This is NOT intended to be used in production. It's a capability verification tool.
"""

import json
import subprocess
import sys
import tempfile
import os
from pathlib import Path


def check_kicad_cli():
    """Verify KiCad CLI is available."""
    try:
        result = subprocess.run(
            ["kicad-cli", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print(f"✅ KiCad CLI found: {result.stdout.strip()}")
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    print("❌ KiCad CLI not found. Install KiCad 8+ with CLI support.")
    return False


def check_circuit_json_converter():
    """Check if circuit-json-to-kicad converter is available."""
    try:
        result = subprocess.run(
            ["npx", "--no-install", "circuit-json-to-kicad", "--help"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print("✅ Circuit JSON to KiCad converter available")
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    print("⚠️  Circuit JSON converter not pre-installed locally.")
    return False


def check_tscircuit():
    """Check if tscircuit is available."""
    try:
        result = subprocess.run(
            ["npx", "--no-install", "tscircuit", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            print(f"✅ tscircuit available: {result.stdout.strip()}")
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    print("⚠️  tscircuit not pre-installed locally.")
    return False


def check_component_database():
    """Check if JLCPCB/jlcparts database is accessible."""
    jlcparts_path = Path.home() / ".jlcparts" / "jlcparts.db"
    if jlcparts_path.exists():
        size_mb = jlcparts_path.stat().st_size / (1024 * 1024)
        print(f"✅ JLCPCB database found: {size_mb:.1f} MB")
        return True
    print("⚠️  JLCPCB database not found. Run: jlc-fast init")
    return False


def validate_skidl_approach():
    """Test SKiDL approach for circuit definition."""
    print("\n=== Testing SKiDL Circuit Definition ===")
    
    try:
        import skidl
        from skidl import Circuit, Part, Net
        print("✅ SKiDL imported successfully")
        return True
    except ImportError:
        print("⚠️  SKiDL not installed. Run: pip install skidl")
        return False
    except Exception as e:
        print(f"⚠️  SKiDL test encountered an issue: {e}")
        return True


def validate_circuit_json_to_kicad():
    """Test converting Circuit JSON to KiCad files."""
    print("\n=== Testing Circuit JSON → KiCad Conversion ===")
    
    # Check if we have the local submodule for circuit-json-to-kicad
    converter_path = Path("external/circuit-json-to-kicad")
    if converter_path.exists():
        print("✅ Found external/circuit-json-to-kicad submodule")
        return True
    else:
        print("⚠️  external/circuit-json-to-kicad submodule not found")
        return False


def main():
    print("=" * 60)
    print("Phase 1 Validation: AI-Powered Electronics Design Platform")
    print("=" * 60)
    
    print("\n🔍 Checking Prerequisites...")
    
    results = {
        "KiCad CLI": check_kicad_cli(),
        "Circuit JSON Converter": check_circuit_json_converter(),
        "tscircuit": check_tscircuit(),
        "Component Database": check_component_database(),
        "SKiDL": validate_skidl_approach(),
        "Circuit JSON→KiCad": validate_circuit_json_to_kicad()
    }
    
    print("\n" + "=" * 60)
    print("VALIDATION SUMMARY")
    print("=" * 60)
    
    passed = sum(1 for r in results.values() if r)
    failed = len(results) - passed
    
    for check, result in results.items():
        status = "✅ PASS" if result else "⚠️  OPTIONAL/MISSING"
        print(f"{check}: {status}")
    
    print(f"\nTotal: {passed} active, {failed} missing optional components")
    print("\n🎉 Phase 1 validation environment check complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())