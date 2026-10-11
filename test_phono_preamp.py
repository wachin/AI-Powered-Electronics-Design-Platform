#!/usr/bin/env python3
import asyncio
import os
from src.llm.providers import create_llm_client
from src.llm.integration import NLToCircuitPipeline
from src.agents.orchestrator import AIDesignOrchestrator, DesignRequest
from pathlib import Path
import tempfile

async def test():
    print('Creating NVIDIA client...')
    client = create_llm_client(
        provider='openai',
        api_key=os.getenv('NVIDIA_API_KEY'),
        base_url='https://integrate.api.nvidia.com/v1',
        model='nvidia/nemotron-3-ultra-550b-a55b'
    )
    
    print('Health:', await client.health_check())
    
    # Create pipeline with NVIDIA client
    nl_pipeline = NLToCircuitPipeline(llm_client=client)
    
    # Test parsing first
    print('\n=== Parsing Requirements ===')
    spec_result = await nl_pipeline.nl_to_circuit_spec(
        'Design a stereo phono preamp for a turntable with moving magnet cartridge, RIAA equalization, RCA inputs and outputs, powered by 9V battery or 12V DC adapter'
    )
    
    print(f'Circuit Type: {spec_result.requirements.circuit_type}')
    print(f'Description: {spec_result.requirements.description}')
    print(f'Input Voltage: {spec_result.requirements.input_voltage}V')
    print(f'Features: {spec_result.requirements.features}')
    print(f'Topology: {spec_result.topology}')
    print(f'Components: {len(spec_result.components)}')
    print(f'Design Notes: {spec_result.design_notes[:2]}...')  # First 2
    print(f'Warnings: {spec_result.warnings[:2]}...')      # First 2
    
    # Now test full pipeline with orchestrator
    print('\n=== Full Pipeline Test (SPICE + KiCad) ===')
    orchestrator = AIDesignOrchestrator()
    orchestrator.nl_pipeline = nl_pipeline
    
    with tempfile.TemporaryDirectory() as tmpdir:
        out_dir = Path(tmpdir)
        request = DesignRequest(
            prompt='Design a stereo phono preamp for a turntable with moving magnet cartridge, RIAA equalization, RCA inputs and outputs, powered by 9V battery or 12V DC adapter',
            project_name='turntable_phono_preamp',
            run_spice=True,
            run_routing=False
        )
        
        print('Processing full design request...')
        summary = await orchestrator.process_request(request, out_dir)
        
        print(f'Project: {summary.project_name}')
        print(f'ERC: {"PASS" if summary.erc_report.passed else "FAIL"} ({len(summary.erc_report.issues)} issues)')
        print(f'Components in CircuitIR: {len(summary.circuit_ir.components)}')
        print(f'BOM items: {len(summary.bom)}')
        total_cost = sum(item.get('total_price', 0) for item in summary.bom)
        print(f'Estimated cost: ${total_cost:.2f}')
        print(f'Generated files: {list(summary.generated_files.keys())}')
        
        # Show a few components from the BOM
        print('\nSample BOM items:')
        for i, item in enumerate(summary.bom[:5]):
            print(f'  {i+1}. {item.get("description", "N/A")}: {item.get("quantity", 0)} x {item.get("unit_price", 0):.2f} = ${item.get("total_price", 0):.2f}')

if __name__ == '__main__':
    asyncio.run(test())