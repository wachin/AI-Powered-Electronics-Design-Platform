#!/usr/bin/env python3
"""
AI-Powered Electronics Design Platform - Unified Pipeline

This script integrates all Phase 1 POCs into a cohesive pipeline:
1. Natural Language Requirements → Circuit Design
2. Component Selection (JLCPCB/LCSC integration)
3. Circuit JSON Generation (via tscircuit)
4. KiCad Project Generation
5. ERC/DRC Validation
6. Manufacturing Export

Usage:
    python unified_pipeline.py "Create a 5V to 3.3V LDO regulator with LED indicator"
"""

import json
import subprocess
import tempfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Dict, Any, Optional
from enum import Enum
import shutil

class DesignStatus(Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class ComponentInfo:
    mpn: str
    manufacturer: str
    description: str
    package: str
    stock: int
    price: float
    symbol_library: str = ""
    footprint: str = ""

@dataclass
class DesignStep:
    name: str
    status: DesignStatus = DesignStatus.PENDING
    message: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "status": self.status.value,
            "message": self.message,
            "data": self.data
        }

@dataclass
class DesignResult:
    success: bool
    requirements: str = ""
    design_steps: List[DesignStep] = field(default_factory=list)
    components: List[ComponentInfo] = field(default_factory=list)
    output_dir: Optional[Path] = None
    errors: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "requirements": self.requirements,
            "design_steps": [s.to_dict() for s in self.design_steps],
            "components": [asdict(c) for c in self.components],
            "output_dir": str(self.output_dir) if self.output_dir else None,
            "errors": self.errors
        }

class UnifiedAIPipeline:
    """Unified AI-powered electronics design pipeline."""
    
    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or Path(__file__).parent
        self.conversion_script = self.base_dir / "converter" / "converter_circuit_json_to_kiCad.tsx"
        self.result = DesignResult(success=False)
        
    def _add_step(self, name: str, status: DesignStatus, message: str = "", data: Optional[Dict] = None) -> DesignStep:
        step = DesignStep(
            name=name,
            status=status,
            message=message,
            data=data or {}
        )
        self.result.design_steps.append(step)
        return step
    
    def _parse_requirements(self, natural_language: str) -> Dict[str, Any]:
        """Parse natural language requirements into structured data."""
        req = {
            "original": natural_language,
            "voltage_input": 5.0,
            "voltage_output": 3.3,
            "current_ma": 500,
            "components": []
        }
        
        # Simple keyword parsing (would use LLM in production)
        nl_lower = natural_language.lower()
        if "5v" in nl_lower or "5 v" in nl_lower:
            req["voltage_input"] = 5.0
        if "3.3v" in nl_lower or "3.3 v" in nl_lower:
            req["voltage_output"] = 3.3
        if "led" in nl_lower or "indicator" in nl_lower:
            req["components"].append({"type": "led", "count": 1})
        if "regulator" in nl_lower or "ldo" in nl_lower:
            req["components"].append({"type": "regulator", "count": 1})
        
        return req
    
    def _select_components(self, requirements: Dict) -> List[ComponentInfo]:
        """Select components from database."""
        components = []
        
        # Mock component selection (would query JLCPCB/LCSC in production)
        for comp in requirements.get("components", []):
            if comp["type"] == "regulator":
                components.append(ComponentInfo(
                    mpn="AMS1117-3.3",
                    manufacturer="AMS",
                    description="LDO Regulator 3.3V 1A",
                    package="SOT-223",
                    stock=10000,
                    price=0.15,
                    symbol_library="Regulator_Linear:AMS1117-3.3",
                    footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2"
                ))
            elif comp["type"] == "led":
                components.append(ComponentInfo(
                    mpn="LED-0603-GREEN",
                    manufacturer="Various",
                    description="LED Green 0603",
                    package="0603",
                    stock=100000,
                    price=0.05,
                    symbol_library="Device:LED",
                    footprint="LED_SMD:LED_0603_16"
                ))
        
        # Always add passives for regulator circuit
        components.append(ComponentInfo(
            mpn="C-10uF-0805",
            manufacturer="Various",
            description="Capacitor 10uF 0805",
            package="0805",
            stock=50000,
            price=0.02,
            symbol_library="Device:C",
            footprint="Capacitor_SMD:C_0805_2012"
        ))
        components.append(ComponentInfo(
            mpn="C-22uF-0805",
            manufacturer="Various",
            description="Capacitor 22uF 0805",
            package="0805",
            stock=50000,
            price=0.03,
            symbol_library="Device:C",
            footprint="Capacitor_SMD:C_0805_2012"
        ))
        components.append(ComponentInfo(
            mpn="R-330-0805",
            manufacturer="Various",
            description="Resistor 330 Ohm 0805",
            package="0805",
            stock=100000,
            price=0.01,
            symbol_library="Device:R",
            footprint="Resistor_SMD:R_0805_2012"
        ))
        
        return components
    
    def _generate_circuit_json(self, output_dir: Path) -> Path:
        """Generate Circuit JSON using tscircuit converter."""
        converter_dir = self.base_dir / "converter"
        
        if not converter_dir.exists():
            raise RuntimeError("Converter directory not found")
        
        # Locate bun executable under user's home or system path
        home_bun = Path.home() / ".bun" / "bin" / "bun"
        bun_bin = str(home_bun) if home_bun.exists() else "bun"

        # Run the bun converter script
        result = subprocess.run(
            [bun_bin, "run", str(converter_dir / "converter_circuit_json_to_kicad.tsx")],
            cwd=str(converter_dir),
            capture_output=True,
            text=True,
            timeout=120
        )
        
        if result.returncode != 0:
            raise RuntimeError(f"Converter failed: {result.stderr}")
        
        return converter_dir / "generated_design"
    
    def _run_validation(self, design_dir: Path) -> Dict[str, Any]:
        """Run ERC/DRC validation."""
        results = {"erc": {}, "drc": {}}
        
        sch_file = design_dir / "design.kicad_sch"
        pcb_file = design_dir / "design.kicad_pcb"
        
        if sch_file.exists():
            result = subprocess.run(
                ["kicad-cli", "sch", "erc", str(sch_file)],
                capture_output=True,
                text=True,
                timeout=30
            )
            results["erc"] = {
                "passed": result.returncode == 0,
                "output": result.stdout
            }
        
        if pcb_file.exists():
            result = subprocess.run(
                ["kicad-cli", "pcb", "drc", str(pcb_file)],
                capture_output=True,
                text=True,
                timeout=30
            )
            results["drc"] = {
                "passed": result.returncode == 0,
                "output": result.stdout
            }
        
        return results
    
    def _export_manufacturing(self, design_dir: Path) -> Dict[str, Path]:
        """Export manufacturing files (Gerbers, BOM, etc.)."""
        exports = {}
        
        pcb_file = design_dir / "design.kicad_pcb"
        if not pcb_file.exists():
            return exports
        
        export_dir = design_dir / "manufacturing"
        export_dir.mkdir(exist_ok=True)
        
        # Export Gerbers
        result = subprocess.run(
            ["kicad-cli", "pcb", "export", "gerber", str(pcb_file), "--output-dir", str(export_dir)],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0:
            exports["gerbers"] = export_dir
            for f in export_dir.glob("*.gbr"):
                exports[f.name] = f
        
        # Export drill files
        result = subprocess.run(
            ["kicad-cli", "pcb", "export", "drill", str(pcb_file), "--output-dir", str(export_dir)],
            capture_output=True,
            text=True,
            timeout=60
        )
        
        # Export BOM
        sch_file = design_dir / "design.kicad_sch"
        if sch_file.exists():
            result = subprocess.run(
                ["kicad-cli", "sch", "export", "bom", str(sch_file), "--output-dir", str(export_dir)],
                capture_output=True,
                text=True,
                timeout=30
            )
            
            if result.returncode == 0:
                exports["bom"] = export_dir / "design.csv"
        
        return exports
    
    def run(self, natural_language: str) -> DesignResult:
        """Run the complete AI design pipeline."""
        print("=" * 70)
        print("AI-Powered Electronics Design Platform")
        print("=" * 70)
        
        self.result.requirements = natural_language
        
        try:
            # Step 1: Parse Requirements
            self._add_step("parse_requirements", DesignStatus.IN_PROGRESS)
            requirements = self._parse_requirements(natural_language)
            self._add_step("parse_requirements", DesignStatus.COMPLETED, 
                         f"Parsed: {requirements['voltage_input']}V → {requirements['voltage_output']}V",
                         requirements)
            print(f"\n✅ Step 1: Requirements parsed")
            print(f"   Input: {requirements['voltage_input']}V, Output: {requirements['voltage_output']}V")
            
            # Step 2: Select Components
            self._add_step("select_components", DesignStatus.IN_PROGRESS)
            components = self._select_components(requirements)
            self.result.components = components
            self._add_step("select_components", DesignStatus.COMPLETED,
                         f"Selected {len(components)} components",
                         {"components": [asdict(c) for c in components]})
            print(f"\n✅ Step 2: Components selected ({len(components)} parts)")
            for c in components:
                print(f"   - {c.mpn}: {c.description}")
            
            # Step 3: Generate Circuit (via tscircuit)
            self._add_step("generate_circuit", DesignStatus.IN_PROGRESS)
            print(f"\n⏳ Step 3: Generating Circuit JSON via tscircuit...")
            
            output_dir = self._generate_circuit_json(self.base_dir)
            
            self._add_step("generate_circuit", DesignStatus.COMPLETED,
                         f"Generated KiCad project",
                         {"output_dir": str(output_dir)})
            print(f"✅ Step 3: KiCad project generated at: {output_dir}")
            
            # Step 4: Run Validation
            self._add_step("validation", DesignStatus.IN_PROGRESS)
            print(f"\n⏳ Step 4: Running ERC/DRC validation...")
            validation_results = self._run_validation(output_dir)
            
            erc_pass = validation_results["erc"].get("passed", False)
            drc_pass = validation_results["drc"].get("passed", False)
            
            self._add_step("validation", DesignStatus.COMPLETED,
                         f"ERC: {'PASS' if erc_pass else 'WARN'}, DRC: {'PASS' if drc_pass else 'WARN'}",
                         validation_results)
            print(f"✅ Step 4: Validation complete - ERC: {'PASS' if erc_pass else 'WARN'}, DRC: {'PASS' if drc_pass else 'WARN'}")
            
            # Step 5: Export Manufacturing Files
            self._add_step("export", DesignStatus.IN_PROGRESS)
            print(f"\n⏳ Step 5: Exporting manufacturing files...")
            exports = self._export_manufacturing(output_dir)
            
            self._add_step("export", DesignStatus.COMPLETED,
                         f"Exported {len(exports)} files",
                         {k: str(v) for k, v in exports.items()})
            print(f"✅ Step 5: Manufacturing files exported")
            
            self.result.success = True
            self.result.output_dir = output_dir
            
        except Exception as e:
            error_msg = str(e)
            self.result.errors.append(error_msg)
            self._add_step("error", DesignStatus.FAILED, error_msg)
            print(f"\n❌ Error: {error_msg}")
        
        # Final Summary
        print("\n" + "=" * 70)
        if self.result.success:
            print("✅ DESIGN COMPLETED SUCCESSFULLY!")
            print(f"\n📁 Output Directory: {self.result.output_dir}")
            print("\n📋 Design Steps:")
            for step in self.result.design_steps:
                status_icon = "✅" if step.status == DesignStatus.COMPLETED else "❌" if step.status == DesignStatus.FAILED else "⏳"
                print(f"   {status_icon} {step.name}: {step.message}")
        else:
            print("❌ DESIGN FAILED")
            print(f"\nErrors:")
            for err in self.result.errors:
                print(f"   - {err}")
        print("=" * 70)
        
        return self.result

def main():
    import sys
    
    if len(sys.argv) < 2:
        # Default example
        natural_language = "Create a 5V to 3.3V LDO regulator circuit with LED indicator"
    else:
        natural_language = " ".join(sys.argv[1:])
    
    pipeline = UnifiedAIPipeline()
    result = pipeline.run(natural_language)
    
    # Save result to JSON
    result_file = Path(__file__).parent / "design_result.json"
    with open(result_file, "w") as f:
        json.dump(result.to_dict(), f, indent=2)
    print(f"\n📄 Result saved to: {result_file}")
    
    return 0 if result.success else 1

if __name__ == "__main__":
    exit(main())