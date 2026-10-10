# LLM Model Recommendations for AI Electronics Design Platform

## Hardware Specifications
- **OS**: Debian GNU/Linux 13 (trixie) x86_64
- **CPU**: Intel Core i3-7020U @ 2.30 GHz (4 cores)
- **GPU**: Intel HD Graphics 620 (Integrated)
- **RAM**: 5.7 GB available / 7.65 GB total (75% used)

## Model Testing Results

| Model | Size | RAM Required | Quality | Speed | Verdict |
|-------|------|--------------|---------|-------|---------|
| `qwen2.5:1.5b` | ~1.1 GB | ~1.5 GB | ❌ Poor | ~20 tok/s | ❌ Too small |
| **`qwen2.5:3b`** | **~2.2 GB** | **~2.8 GB** | ✅ **Good** | ~8-12 tok/s | ✅ **Recommended minimum** |
| `qwen2.5:7b` | ~4.7 GB | ~5.2 GB | ⭐⭐⭐⭐ | ~6-8 tok/s | If RAM allows |
| `phi3:mini` | ~2.3 GB | ~2.8 GB | ⭐⭐⭐⭐ Good reasoning | ~10-15 tok/s | Good alternative |
| `phi3:mini` | ~2.3 GB | ~2.8 GB | ⭐⭐⭐⭐ | ~10-15 tok/s | Good alternative |

## ✅ Recommended Configuration

### Minimum Viable (Recommended)
```bash
ollama pull qwen2.5:3b    # ~2.2 GB, ~2.8 GB RAM
```

### Better Quality (if RAM allows)
```bash
ollama pull qwen2.5:7b      # ~4.7 GB model, ~5.2 GB RAM
```

### Alternative Models
```bash
ollama pull phi3:mini       # Microsoft Phi-3, good reasoning
ollama pull phi3:mini       # Microsoft Phi-3 mini
```

## Hardware Utilization
- **Total RAM**: 7.65 GB
- **Available**: 5.7 GB
- **qwen2.5:3b**: ~2.8 GB used (leaves ~2.9 GB for OS/other apps)
- **Headroom**: ~2.9 GB for OS, browser, other apps

## Free OpenAI-Compatible API Providers

| Provider | API Base URL | Models | Free Tier |
|----------|--------------|--------|-----------|
| **Ollama (Local)** | `http://localhost:11434/v1` | qwen2.5, phi3, llama3, etc. | Free (local) |
| **NVIDIA NIM** | `https://integrate.api.nvidia.com/v1` | Nemotron, Nemotron-3-Ultra, Llama-3.1 | Free tier |
| **Hugging Face** | `https://router.huggingface.co/v1` | Zephyr, Mixtral, Llama, Qwen | Free tier |
| **OpenRouter** | `https://openrouter.ai/api/v1` | 100+ models | Free tier + pay |
| **Google Gemini** | `https://generativelanguage.googleapis.com/v1beta` | Gemini 1.5 Flash/Pro | Free tier |
| **Together AI** | `https://api.together.xyz/v1` | Llama, Mixtral, Qwen | Free tier |
| **Groq** | `https://api.groq.com/openai/v1` | Llama-3, Mixtral | Free tier (fast) |
| **Together AI** | `https://api.together.xyz/v1` | Many models | Free tier |
| **DeepInfra** | `https://api.deepinfra.com/v1/openai` | Many models | Free tier |
| **Anyscale** | `https://api.endpoints.anyscale.com/v1` | Llama, Mixtral | Free tier |

## Integration Example

```python
from src.llm.providers import create_llm_client, LLMProvider

# Local Ollama
client = create_llm_client(
    provider="ollama",
    model="qwen2.5:3b",
    base_url="http://localhost:11434/v1"
)

# NVIDIA NIM (Free tier)
client = create_llm_client(
    provider="openai",
    api_key="nvapi-xxx",
    base_url="https://integrate.api.nvidia.com/v1",
    model="nvidia/nemotron-3-ultra"
)

# Hugging Face (free tier)
client = create_llm_client(
    provider="openai",
    api_key="hf_xxx",
    base_url="https://router.huggingface.co/v1",
    model="Qwen/Qwen2.5-3B-Instruct"
)

# OpenRouter
client = create_llm_client(
    provider="openai",
    api_key="sk-or-xxx",
    base_url="https://openrouter.ai/api/v1",
    model="qwen/qwen-2.5-3b-instruct"
)

# Google Gemini
client = create_llm_client(
    provider="openai",
    api_key="AIzaSy...",
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
    model="gemini-1.5-flash"
)
```

## Hardware Requirements Summary

| Model | Disk | RAM Needed | Speed | Quality |
|-------|------|------------|-------|---------|
| qwen2.5:1.5b | 1.1 GB | 1.5 GB | Fast | ❌ Poor |
| **qwen2.5:3b** | **2.2 GB** | **2.8 GB** | **8-12 tok/s** | **Good** |
| qwen2.5:7b | 4.7 GB | 5.2 GB | Slow | Excellent |
| phi3:mini | 2.3 GB | 2.8 GB | Fast | Good |
| phi3:mini | 2.3 GB | 2.8 GB | Fast | Good reasoning |

## Recommendation

**For your hardware (5.7 GB available):**
```bash
# Minimum viable
ollama pull qwen2.5:3b      # ✅ Recommended (2.8 GB RAM)

# If you have headroom
ollama pull qwen2.5:7b      # Better quality (needs ~5.2 GB)
```

## Hardware Utilization
- **Total RAM**: 7.65 GB
- **Available**: 5.7 GB
- **qwen2.5:3b**: ~2.8 GB used (leaves ~2.9 GB for OS/other apps)
- **Headroom**: ~2.9 GB for OS, browser, other apps
EOF
cat docs/llm-model-recommendations.md