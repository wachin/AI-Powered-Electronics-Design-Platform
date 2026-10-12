#!/usr/bin/env python3
"""Test requirement parsing for buck converter."""
import asyncio
from src.llm.integration import create_nl_pipeline
from src.llm.providers import create_llm_client

async def test():
    client = create_llm_client("mock")
    pipeline = create_nl_pipeline("mock")
    
    prompt = "Design a 12V to 5V buck converter circuit for 3A output"
    print(f"Prompt: {prompt}")
    
    result = await pipeline.nl_to_circuit_spec(prompt)
    print(f"Circuit type: {result.requirements.circuit_type}")
    print(f"Description: {result.requirements.description}")
    print(f"Input V: {result.requirements.input_voltage}")
    print(f"Output V: {result.requirements.output_voltage}")
    print(f"Output I: {result.requirements.output_current}")
    print(f"Topology: {result.topology}")
    print(f"Components: {len(result.components)}")
    for c in result.components:
        print(f"  {c.role}: {c.mpn} ({c.value})")

if __name__ == "__main__":
    asyncio.run(test())
