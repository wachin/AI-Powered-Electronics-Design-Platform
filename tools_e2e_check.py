#!/usr/bin/env python3
"""
End-to-end check with a real LLM: natural language -> validated KiCad project.

This is the acceptance test the project was missing: it exercises a real
provider (not the mock), builds the Circuit IR from the LLM's own component
list, runs ERC, and reports whether the result is physically usable.

Usage:
    python tools_e2e_check.py                       # Ollama qwen2.5:3b
    python tools_e2e_check.py --model qwen2.5:7b
    python tools_e2e_check.py --provider openai --model gpt-4o-mini
"""

import argparse
import asyncio
import json
import logging
import time
from pathlib import Path

from src.llm.integration import NLToCircuitPipeline
from src.llm.providers import create_llm_client


async def run_check(args, prompt: str) -> int:
    client = create_llm_client(
        provider=args.provider,
        model=args.model,
        base_url=args.base_url,
        timeout=args.timeout,
    )

    print(f"Provider : {args.provider} ({args.model})")
    healthy = await client.health_check()
    print(f"Health   : {'OK' if healthy else 'UNAVAILABLE'}")
    if not healthy:
        print("Provider is not reachable; aborting.")
        return 2

    pipeline = NLToCircuitPipeline(
        llm_client=client,
        allow_fallback=not args.no_fallback,
        max_repairs=args.max_repairs,
    )
    if args.max_tokens:
        pipeline.spec_generator.default_max_tokens = args.max_tokens

    print(f"Prompt   : {prompt}")
    print("Generating (this can take a while on CPU-only models)...")
    started = time.time()

    try:
        # Use a real (gitignored) directory so the generated files can be
        # inspected after the run, rather than a temp dir that is deleted.
        out_dir = Path(args.output_dir)
        result = await pipeline.process(
            prompt, project_name="e2e_design", output_dir=out_dir
        )
    except Exception as exc:  # noqa: BLE001 - we want the failure reported
        print(f"\nFAILED: {type(exc).__name__}: {exc}")
        return 1

    elapsed = time.time() - started
    spec = result["specification"]
    circuit = result["circuit_ir"]
    report = result["validation"]

    print(f"\nGenerated in {elapsed:.1f}s")
    print(f"Topology     : {spec.topology}")
    print(f"Used LLM     : {spec.used_llm}")
    print(f"Repairs      : {spec.repair_attempts}")
    print(f"Components   : {len(circuit.components)}")
    for ref, comp in circuit.components.items():
        print(
            f"  {ref:4} {comp.component_type.value:16} {comp.value:8} "
            f"{comp.mpn or '-':22} {comp.symbol or '-':32} "
            f"pins={[p.number for p in comp.pins]}"
        )

    print("Nets:")
    for net_name, net in circuit.nets.items():
        pins = ", ".join(f"{p['ref']}.{p['pin']}" for p in net.connected_pins)
        print(f"  {net_name:12} -> {pins}")

    print(f"\nValidation   : {'PASS' if report.valid else 'FAIL'}")
    print(f"ERC          : {report.erc.summary if report.erc else 'n/a'}")
    for issue in report.errors:
        print(f"  ERROR   [{issue.code}] {issue.message}")
    for issue in report.warnings[:8]:
        print(f"  WARNING [{issue.code}] {issue.message}")

    print("\nGenerated files:")
    for kind, path in result.get("files", {}).items():
        exists = path.exists() if hasattr(path, "exists") else False
        print(f"  {kind:5} {path} {'(ok)' if exists else '(MISSING)'}")

    print("\nBuild report:")
    print(json.dumps(report.build_report.to_dict(), indent=2))

    if not report.valid:
        return 1
    if not circuit.components:
        print("\nNo components were produced.")
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--provider", default="ollama")
    parser.add_argument("--model", default="qwen2.5:3b")
    parser.add_argument("--base-url", default="http://localhost:11434")
    parser.add_argument("--timeout", type=float, default=600.0)
    parser.add_argument("--max-repairs", type=int, default=2)
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=1200,
        help="Cap on generated tokens per request (bounds wall-clock time)",
    )
    parser.add_argument("--no-fallback", action="store_true")
    parser.add_argument(
        "--prompt",
        default=(
            "Design a 5V to 3.3V LDO regulator circuit with 500mA output "
            "current and an LED power indicator"
        ),
    )
    parser.add_argument("--output-dir", default="output_design/e2e")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return asyncio.run(run_check(args, args.prompt))


if __name__ == "__main__":
    raise SystemExit(main())
