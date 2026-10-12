#!/usr/bin/env python3
"""
Test script to demonstrate using real LLM providers with the AI Electronics Design Platform.

This script shows how to use various free OpenAI-compatible APIs:
- NVIDIA NIM (free tier)
- Hugging Face (free tier) 
- OpenRouter (free tier)
- Google Gemini (free tier)
- Together AI (free tier)
- Groq (free tier)
- Local Ollama (qwen2.5:3b)

Requirements:
- Set API keys as environment variables
- For local Ollama: ollama pull qwen2.5:3b
"""

import asyncio
import os
from src.llm.providers import create_llm_client, LLMProvider
from src.llm.integration import create_nl_pipeline, NLToCircuitPipeline, CircuitRequirement


async def test_provider(name: str, client_factory, prompt: str):
    """Test a single LLM provider."""
    print(f"\n{'='*60}")
    print(f"Testing: {name}")
    print(f"{'='*60}")
    
    try:
        client = client_factory()
        
        # Check health
        healthy = await client.health_check()
        print(f"Health check: {'✅ PASS' if healthy else '❌ FAIL'}")
        
        if not healthy:
            print("Skipping generation (health check failed)")
            return
        
        # Create pipeline with this client
        pipeline = NLToCircuitPipeline(llm_client=client)
        
        # Process the prompt
        print(f"Prompt: {prompt}")
        print("Processing...")
        
        result = await pipeline.nl_to_circuit_spec(prompt)
        
        print(f"✅ Circuit Type: {result.requirements.circuit_type}")
        print(f"✅ Description: {result.requirements.description}")
        print(f"✅ Input Voltage: {result.requirements.input_voltage}V")
        print(f"✅ Output Voltage: {result.requirements.output_voltage}V")
        print(f"✅ Output Current: {result.requirements.output_current}A")
        print(f"✅ Features: {result.requirements.features}")
        
    except Exception as e:
        print(f"❌ Error: {e}")


async def main():
    """Test various LLM providers."""
    
    # Example prompt
    prompt = "Design a 5V to 3.3V LDO regulator circuit with 500mA output current and LED power indicator"
    
    # Provider configurations - UPDATE THESE WITH YOUR API KEYS
    providers = []
    
    # 1. Local Ollama (qwen2.5:3b) - RECOMMENDED for your hardware
    if os.getenv("USE_OLLAMA", "true").lower() == "true":
        providers.append((
            "Ollama (qwen2.5:3b - Local, Native API)",
            lambda: create_llm_client(
                provider="ollama",
                model="qwen2.5:3b",
                base_url="http://localhost:11434"
            )
        ))
    
    # 1b. Local Ollama via OpenAI-compatible API
    providers.append((
        "Ollama (qwen2.5:3b - Local, OpenAI API)",
        lambda: create_llm_client(
            provider="openai",
            api_key="ollama",  # Not used but required
            base_url="http://localhost:11434/v1",
            model="qwen2.5:3b"
        )
    ))
    
    # 2. NVIDIA NIM (Free tier)
    nvidia_key = os.getenv("NVIDIA_API_KEY")
    if nvidia_key:
        providers.append((
            "NVIDIA NIM (Nemotron-3-Ultra)",
            lambda: create_llm_client(
                provider="openai",
                api_key=nvidia_key,
                base_url="https://integrate.api.nvidia.com/v1",
                model="nvidia/nemotron-3-ultra-550b-a55b"
            )
        ))
    
    # 3. Hugging Face (Free tier)
    hf_key = os.getenv("HUGGINGFACE_API_KEY")
    if hf_key:
        providers.append((
            "Hugging Face (Qwen2.5-3B)",
            lambda: create_llm_client(
                provider="openai",
                api_key=hf_key,
                base_url="https://router.huggingface.co/v1",
                model="Qwen/Qwen2.5-3B-Instruct"
            )
        ))
    
    # 4. OpenRouter (Free tier)
    openrouter_key = os.getenv("OPENROUTER_API_KEY")
    if openrouter_key:
        providers.append((
            "OpenRouter (Qwen2.5-3B)",
            lambda: create_llm_client(
                provider="openai",
                api_key=openrouter_key,
                base_url="https://openrouter.ai/api/v1",
                model="qwen/qwen-2.5-3b-instruct"
            )
        ))
    
    # 5. Google Gemini (Free tier)
    gemini_key = os.getenv("GEMINI_API_KEY")
    if gemini_key:
        providers.append((
            "Google Gemini (gemini-1.5-flash)",
            lambda: create_llm_client(
                provider="openai",
                api_key=gemini_key,
                base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                model="gemini-1.5-flash"
            )
        ))
    
    # 6. Together AI (Free tier)
    together_key = os.getenv("TOGETHER_API_KEY")
    if together_key:
        providers.append((
            "Together AI (Qwen2.5-3B)",
            lambda: create_llm_client(
                provider="openai",
                api_key=together_key,
                base_url="https://api.together.xyz/v1",
                model="Qwen/Qwen2.5-3B-Instruct"
            )
        ))
    
    # 7. Groq (Free tier - very fast)
    groq_key = os.getenv("GROQ_API_KEY")
    if groq_key:
        providers.append((
            "Groq (Llama-3.1-8B - Fast)",
            lambda: create_llm_client(
                provider="openai",
                api_key=groq_key,
                base_url="https://api.groq.com/openai/v1",
                model="llama-3.1-8b-instant"
            )
        ))
    
    # 8. Mock (always works for testing)
    providers.append((
        "Mock Client (Testing)",
        lambda: create_llm_client("mock")
    ))
    
    if len(providers) == 1:
        print("⚠️  No API keys found. Only Mock client will be tested.")
        print("\nSet these environment variables to test real providers:")
        print("  export NVIDIA_API_KEY=your_key")
        print("  export HUGGINGFACE_API_KEY=your_key")
        print("  export OPENROUTER_API_KEY=your_key")
        print("  export GEMINI_API_KEY=your_key")
        print("  export TOGETHER_API_KEY=your_key")
        print("  export GROQ_API_KEY=your_key")
        print("  export USE_OLLAMA=true  # For local Ollama")
    
    # Test each provider
    for name, factory in providers:
        await test_provider(name, factory, prompt)
    
    print(f"\n{'='*60}")
    print("All provider tests completed!")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
