"""
Command-line interface for the AI-Powered Electronics Design Platform.

This lives inside the package (rather than only in a repository-root script) so
that an installed copy exposes a working console command:

    ai-electronics-design -p "Design a 5V to 3.3V LDO regulator with an LED"

    # Optional MCP servers (isolated environments, not required for design)
    ai-electronics-design mcp-status
    ai-electronics-design mcp-setup
    ai-electronics-design mcp-setup --server pcbparts

    # Component catalog (~180,000 in-stock parts, for real part selection)
    ai-electronics-design catalog-status
    ai-electronics-design catalog-setup

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



SUBCOMMANDS = ("mcp-status", "mcp-setup", "catalog-status", "catalog-setup")


def _run_mcp_status() -> int:
    """Report which optional MCP servers are available."""
    from src.agents.mcp_servers import MCPServerManager, render_status

    print(render_status(MCPServerManager().report()))
    return 0


def _run_mcp_setup(servers: list[str] | None, verbose: bool) -> int:
    """
    Create isolated environments for the optional MCP servers.

    Each server gets its own virtual environment, so their conflicting
    dependencies never meet. Nothing here is required to generate a design.
    """
    from src.agents.mcp_servers import MCPServerManager

    manager = MCPServerManager(verbose=verbose)
    print("Setting up optional MCP servers (isolated environments)...")
    results = manager.install_all(servers)

    failures = 0
    for result in results:
        if result.ok:
            note = "created environment, " if result.created_venv else ""
            print(f"  ✅ {result.key}: {note}installed {', '.join(result.installed)}")
            if result.command:
                print(f"     launch: {' '.join(result.command)}")
        else:
            failures += 1
            print(f"  ❌ {result.key}: {result.error}")
    print()
    if failures:
        print(f"{failures} server(s) could not be set up. See the messages above.")
        return 1
    print("All requested servers are ready. Check with: ai-electronics-design mcp-status")
    return 0



def _run_catalog_status() -> int:
    """Report whether the component catalog is available and how big it is."""
    from src.components.database import ComponentDatabase
    from src.components.jlcparts import default_catalog_path, JLCPartsDatabase

    db = ComponentDatabase()
    print("Component catalog:")
    print(f"  source : {db.data_source}")
    print(f"  parts  : {db.catalog_size:,}")
    if db.using_jlcparts:
        print(f"  path   : {JLCPartsDatabase().db_path}")
        print("  status : full offline catalog in use")
    else:
        print(f"  expected path: {default_catalog_path()}")
        print("  status : built-in fallback catalog only "
              "(common parts, no stock or price data)")
        print()
        print("Download the full catalog with: ai-electronics-design catalog-setup")
    return 0


def _run_catalog_setup(force: bool, verbose: bool, dest: str | None = None) -> int:
    """
    Download the offline component catalog.

    Roughly 145 MB, containing about 180,000 in-stock JLCPCB/LCSC parts with
    stock levels, tiered pricing, datasheets and parametric attributes. It is
    optional — the platform works without it — but part selection and
    substitution are far better with it.
    """
    from src.components.jlcparts import download_catalog, default_catalog_path

    try:
        from pathlib import Path as _Path

        path = download_catalog(
            dest=_Path(dest) if dest else None, force=force, progress=True
        )
    except RuntimeError as exc:
        print(f"❌ {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("\nInterrupted; the partial download was removed.", file=sys.stderr)
        return 130

    print()
    print(f"Installed at: {path}")
    print("Check it with: ai-electronics-design catalog-status")
    return 0


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
        "--mcp-validate",
        action="store_true",
        help=(
            "Also validate the generated project with an MCP server "
            "(needs: ai-electronics-design mcp-setup)"
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
        mcp_validate=args.mcp_validate,
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
        voltages = summary.spice_result.node_voltages
        if voltages:
            print("  DC operating point (check these before ordering parts):")
            for net, volts in voltages.items():
                print(f"    {net:<16} {volts:>8.3f} V")
        elif summary.spice_result.success:
            print("  Note: ngspice produced no operating point to report")
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
    argv = list(sys.argv[1:] if argv is None else argv)

    # Subcommands take precedence over the design-generation flags.
    if argv and argv[0] in SUBCOMMANDS:
        command, rest = argv[0], argv[1:]
        if command == "mcp-status":
            return _run_mcp_status()
        if command == "catalog-status":
            return _run_catalog_status()
        if command == "catalog-setup":
            catalog = argparse.ArgumentParser(prog="ai-electronics-design catalog-setup")
            catalog.add_argument(
                "--force",
                action="store_true",
                help="Download again even if a catalog is already installed",
            )
            catalog.add_argument(
                "--dest",
                default=None,
                help=(
                    "Where to install the catalog "
                    "(default: $XDG_CACHE_HOME/kicad-tools/jlcparts.sqlite3)"
                ),
            )
            catalog.add_argument("-v", "--verbose", action="store_true")
            c_args = catalog.parse_args(rest)
            return _run_catalog_setup(c_args.force, c_args.verbose, c_args.dest)

        sub = argparse.ArgumentParser(prog="ai-electronics-design mcp-setup")
        sub.add_argument(
            "--server",
            action="append",
            choices=["kicad", "pcbparts"],
            dest="servers",
            help="Only set up this server (repeatable). Default: all.",
        )
        sub.add_argument("-v", "--verbose", action="store_true")
        sub_args = sub.parse_args(rest)
        return _run_mcp_setup(sub_args.servers, sub_args.verbose)

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
