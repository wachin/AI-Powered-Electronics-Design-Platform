#!/usr/bin/env python3
"""
Main CLI entry point for AI-Powered Electronics Design Platform.
"""

import argparse
import sys
import json
from pathlib import Path

from src.agents.orchestrator import AIDesignOrchestrator, DesignRequest
from src.components.database import ComponentDatabase


def main():
    parser = argparse.ArgumentParser(
        description="AI-Powered Electronics Design Platform CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s -p "Design a 5V to 3.3V LDO regulator with LED indicator"
  %(prog)s -p "Create a buck converter 12V to 5V" --no-spice --no-routing
  %(prog)s -p "Simple LED blinker with 555 timer" -o ./my_project -n timer_555
"""
    )
    parser.add_argument(
        "--prompt",
        "-p",
        type=str,
        default="Design a 5V to 3.3V LDO regulator circuit with green LED indicator and decoupling capacitors",
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
        "--no-spice",
        action="store_true",
        help="Disable SPICE simulation (ngspice)",
    )
    parser.add_argument(
        "--no-routing",
        action="store_true",
        help="Disable PCB auto-routing (FreeRouting)",
    )

    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    print("=" * 60)
    print("🤖 AI-Powered Electronics Design Platform")
    print("=" * 60)
    print(f"📝 Prompt: {args.prompt}")
    print(f"📁 Target Output: {output_dir.resolve()}")
    print(f"🔬 SPICE Simulation: {'Disabled' if args.no_spice else 'Enabled'}")
    print(f"🛣️  PCB Auto-routing: {'Disabled' if args.no_routing else 'Enabled'}")
    print("-" * 60)

    db = ComponentDatabase()
    orchestrator = AIDesignOrchestrator(db=db)

    request = DesignRequest(
        prompt=args.prompt,
        project_name=args.project_name,
        run_spice=not args.no_spice,
        run_routing=not args.no_routing,
    )
    summary = orchestrator.process_request(request, output_dir)

    print("\n🔍 ERC Report Summary:")
    print(f"  Status: {'✅ PASSED' if summary.erc_report.passed else '❌ FAILED'}")
    for k, v in summary.erc_report.summary.items():
        print(f"  - {k.capitalize()}: {v}")

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
        designators_str = ", ".join(item["designators"])
        print(
            f"  - [{designators_str}] {item['mpn']} ({item['value']}) - Qty: {item['quantity']} - Est: ${item['total_price']:.2f}"
        )

    # Save summary report as JSON
    summary_json_path = output_dir / "design_summary.json"
    summary_json_path.write_text(json.dumps(summary.to_dict(), indent=2))
    print(f"\n📄 Saved design summary JSON to: {summary_json_path}")

    print("\n🎉 Circuit design synthesis complete!")
    return 0


if __name__ == "__main__":
    sys.exit(main())