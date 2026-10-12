"""
Command-line interface for the AI-Powered Electronics Design Platform.

This lives inside the package (rather than only in a repository-root script) so
that an installed copy exposes a working console command:

    ai-electronics-design -p "Design a 5V to 3.3V LDO regulator with an LED"

The root-level `main.py` is a thin shim that calls :func:`main` here, so both
invocation styles behave identically.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from src.agents.orchestrator import AIDesignOrchestrator, DesignRequest
from src.components.database import ComponentDatabase


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ai-electronics-design",
        description=(
            "Generate a validated KiCad project from a natural-language circuit "
            "request."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
Examples:
  %(prog)s -p "Design a 5V to 3.3V LDO regulator with LED indicator"
  %(prog)s -p "Create a buck converter 12V to 5V" --no-spice --no-routing
  %(prog)s -p "Design a 5V to 3.3V LDO" --provider ollama --model qwen2.5:3b
  %(prog)s -p "Simple LED circuit" --no-spice --no-routing -o ./my_project
""",
    )
    parser.add_argument(
        "--prompt",
        "-p",
        type=str,
        default=(
            "Design a 5V to 3.3V LDO regulator circuit with green LED indicator "
            "and decoupling capacitors"
        ),
        help="Natural language prompt describing the circuit requirements",
    )
    parser.add_argument(
        "--output-dir",
        "-o",
        type=str,
        default="./output_design",
        help="Target output directory for KiCad project files and BOM",
    )
    parser.add_argument(
        "--project-name",
        "-n",
        type=str,
        default="ldo_regulator",
        help="Name of the output project",
    )
    parser.add_argument(
        "--provider",
        type=str,
        default="mock",
        choices=["mock", "ollama", "openai", "anthropic"],
        help=(
            "LLM provider. 'mock' uses the deterministic rule-based generator; "
            "'ollama' uses a local model; 'openai' covers any OpenAI-compatible "
            "endpoint via --base-url."
        ),
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model name for the selected provider (e.g. qwen2.5:3b)",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=None,
        help="Base URL for the provider (e.g. http://localhost:11434)",
    )
    parser.add_argument(
        "--max-repairs",
        type=int,
        default=2,
        help="How many times an invalid design is sent back to the model",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help=(
            "Fail instead of falling back to the rule-based template generator "
            "when the LLM is unavailable"
        ),
    )
    parser.add_argument(
        "--no-spice",
        action="store_true",
        help="Disable SPICE simulation (ngspice)",
    )
    parser.add_argument(
        "--no-routing",
        action="store_true",
        help="Disable PCB auto-routing (FreeRouting)",
    )
    return parser


async def _run(args: argparse.Namespace) -> int:
    output_dir = Path(args.output_dir)
    print("=" * 60)
    print("🤖 AI-Powered Electronics Design Platform")
    print("=" * 60)
    print(f"📝 Prompt: {args.prompt}")
    print(f"🧠 Provider: {args.provider}" + (f" ({args.model})" if args.model else ""))
    print(f"📁 Target Output: {output_dir.resolve()}")
    print(f"🔬 SPICE Simulation: {'Disabled' if args.no_spice else 'Enabled'}")
    print(f"🛣️  PCB Auto-routing: {'Disabled' if args.no_routing else 'Enabled'}")
    print("-" * 60)

    db = ComponentDatabase()
    orchestrator = AIDesignOrchestrator(
        db=db,
        llm_provider=args.provider,
        llm_model=args.model,
        llm_base_url=args.base_url,
        allow_fallback=not args.strict,
        max_repairs=args.max_repairs,
    )

    request = DesignRequest(
        prompt=args.prompt,
        project_name=args.project_name,
        run_spice=not args.no_spice,
        run_routing=not args.no_routing,
    )
    summary = await orchestrator.process_request(request, output_dir)

    print("\n🧾 Design Provenance:")
    print(f"  Topology: {summary.topology or 'n/a'}")
    if summary.used_llm:
        print("  Source:   LLM-generated specification")
    else:
        print(
            "  Source:   ⚠️  rule-based template "
            "(the LLM was unavailable and fallback was allowed)"
        )
    for note in summary.design_notes[:6]:
        print(f"  Note:     {note}")

    print("\n🔍 ERC Report Summary:")
    print(f"  Status: {'✅ PASSED' if summary.erc_report.passed else '❌ FAILED'}")
    for key, value in summary.erc_report.summary.items():
        print(f"  - {key.capitalize()}: {value}")

    if summary.spice_result:
        print("\n⚡ SPICE Simulation:")
        print(f"  Status: {'✅ SUCCESS' if summary.spice_result.success else '❌ FAILED'}")
        if not summary.spice_result.success and summary.spice_result.error:
            print(f"  Error: {summary.spice_result.error}")

    if summary.routing_result:
        print("\n🛣️  PCB Auto-routing:")
        print(f"  Status: {'✅ SUCCESS' if summary.routing_result.success else '❌ FAILED'}")
        if not summary.routing_result.success and summary.routing_result.error:
            print(f"  Error: {summary.routing_result.error}")

    print("\n📦 Generated KiCad Files:")
    for file_type, file_path in summary.generated_files.items():
        print(f"  - {file_type.upper()}: {file_path}")

    print("\n📊 Bill of Materials (BOM):")
    for item in summary.bom:
        designators = ", ".join(item["designators"])
        print(
            f"  - [{designators}] {item['mpn']} ({item['value']}) - "
            f"Qty: {item['quantity']} - Est: ${item['total_price']:.2f}"
        )

    summary_json_path = output_dir / "design_summary.json"
    summary_json_path.write_text(json.dumps(summary.to_dict(), indent=2))
    print(f"\n📄 Saved design summary JSON to: {summary_json_path}")

    print("\n🎉 Circuit design synthesis complete!")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Entry point. Returns a process exit code."""
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return asyncio.run(_run(args))
    except RuntimeError as exc:
        # Validation failures are expected user-facing outcomes, not crashes.
        print(f"\n❌ Design failed: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
