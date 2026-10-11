#!/usr/bin/env python3
"""Test buck converter generation end-to-end."""
import asyncio
from src.agents.orchestrator import AIDesignOrchestrator, DesignRequest
from pathlib import Path
import tempfile

async def test_buck():
    orchestrator = AIDesignOrchestrator()
    
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        request = DesignRequest(
            prompt="Design a 12V to 5V buck converter circuit for 3A output",
            project_name="test_buck",
            run_spice=True,
            run_routing=True
        )
        
        summary = await orchestrator.process_request(request, out_dir)
        
        print(f"Project: {summary.project_name}")
        print(f"ERC Passed: {summary.erc_report.passed}")
        print(f"Components: {len(summary.circuit_ir.components)}")
        for ref, comp in summary.circuit_ir.components.items():
            print(f"  {ref}: {comp.value} ({comp.component_type})")
        print(f"Nets: {len(summary.circuit_ir.nets)}")
        for name, net in summary.circuit_ir.nets.items():
            print(f"  {name}: {net.connected_pins}")
        print(f"BOM items: {len(summary.bom)}")
        print(f"Generated files: {list(summary.generated_files.keys())}")

if __name__ == "__main__":
    asyncio.run(test_buck())
