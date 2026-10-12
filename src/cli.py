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

    # Part selection against that catalog
    ai-electronics-design parts-search "10k 0603"
    ai-electronics-design parts-search "100nF 50V 0805" --min-stock 5000
    ai-electronics-design parts-substitute C18212698

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



SUBCOMMANDS = (
    "mcp-status",
    "mcp-setup",
    "catalog-status",
    "catalog-setup",
    "parts-search",
    "parts-substitute",
)


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
        print("  status : component templates only "
              "(symbols and footprints; no part numbers, prices or stock)")
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


def _run_parts_search(
    query: str,
    package: str | None,
    category: str | None,
    min_stock: int,
    limit: int,
    sort: str,
) -> int:
    """
    Search the component catalog from the terminal.

    Values are matched numerically, so ``10k 0603`` returns 10 kΩ parts and not
    110 kΩ ones. The interpretation is printed above the results, so what the
    search understood is always visible.
    """
    from src.components.database import ComponentDatabase

    db = ComponentDatabase()
    if not db.using_jlcparts:
        print(
            "The full component catalog is not installed, so this search would\n"
            "only cover the component templates: values and footprints, with no\n"
            "part numbers, prices or stock.\n"
            "Download it with: ai-electronics-design catalog-setup",
            file=sys.stderr,
        )

    outcome = db.search_explained(
        query=query, category=category, package=package,
        min_stock=min_stock, limit=limit, sort=sort,
    )

    print(f"Query      : {query!r}")
    print(f"Understood : {outcome['interpretation']}")
    for note in outcome["notes"]:
        print(f"Note       : {note}")
    print(f"Source     : {outcome['source']}")
    print()

    components = outcome["components"]
    if not components:
        print("No matching parts.")
        return 0

    print(
        f"{'':>3} {'LCSC':<10} {'MPN':<26} {'Package':<14} "
        f"{'Specification':<30} {'Stock':>9}  {'Unit':>8}"
    )
    for index, entry in enumerate(components, start=1):
        flags = []
        if entry.get("is_preferred"):
            flags.append("preferred")
        if entry.get("is_basic"):
            flags.append("basic")
        flag_text = f"  [{', '.join(flags)}]" if flags else ""
        price = entry.get("price") or 0
        print(
            f"{index:>3}. {entry['lcsc_part'] or '-':<10} "
            f"{(entry['mpn'] or '-')[:26]:<26} "
            f"{(entry['package'] or '-')[:14]:<14} "
            f"{(entry['value'] or '-')[:30]:<30} "
            f"{entry['stock']:>9,}  "
            f"{(f'{price:.4f}' if price else '-'):>8}{flag_text}"
        )

    print()
    if db.using_jlcparts:
        print("Prices are JLCPCB quantity-tier prices and exclude assembly fees.")
    else:
        print("These are component templates: there are no part numbers, prices")
        print("or stock without the catalog.")
    print("Verify stock and specifications before ordering.")
    return 0


def _run_parts_substitute(
    lcsc_part: str,
    limit: int,
    min_stock: int | None,
    same_package: bool,
) -> int:
    """
    Find parts that can replace a given part, with the evidence for each.

    Every candidate is listed with what was checked and matched (``+``) and with
    what differs or could not be verified (``!``). A candidate is never silently
    presented as equivalent.
    """
    from src.components.database import ComponentDatabase

    db = ComponentDatabase()
    if not db.using_jlcparts:
        print(
            "Substitute lookup needs the full component catalog, because it\n"
            "compares parsed specifications. Download it with:\n"
            "  ai-electronics-design catalog-setup",
            file=sys.stderr,
        )
        return 1

    original = db.get_by_lcsc(lcsc_part)
    if original is None:
        print(f"{lcsc_part} is not in the component catalog.", file=sys.stderr)
        return 1

    print(f"Replacing: {original.lcsc_part} {original.mpn}")
    print(f"  category : {original.category}")
    print(f"  package  : {original.package}")
    print(f"  value    : {original.value}")
    print(f"  stock    : {original.stock:,}")
    print()

    substitutes = db.find_substitutes(
        lcsc_part, limit=limit, min_stock=min_stock, same_package=same_package
    )
    if not substitutes:
        print(
            "No comparable part was found.\n"
            "\n"
            "This happens when the part has no numeric specification to match\n"
            "on — a part identified only by a part number cannot be compared by\n"
            "value. Check the part's datasheet and compare candidates by hand."
        )
        return 0

    for index, substitute in enumerate(substitutes, start=1):
        status = "all checks passed" if substitute["verified"] else "review caveats"
        print(
            f"{index}. {substitute['lcsc_part']} {substitute['mpn']} "
            f"({substitute['package']}) — {status}"
        )
        print(f"   value : {substitute['value']}")
        print(f"   stock : {substitute['stock']:,}  unit price: {substitute['price']:.4f}")
        for reason in substitute["reasons"]:
            print(f"   + {reason}")
        for caveat in substitute["caveats"]:
            print(f"   ! {caveat}")
        print()

    print("A substitute is a candidate, not a guarantee. Check the datasheet —")
    print("in particular the pinout — before ordering.")
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
            "LLM provider. 'mock' (the default) uses no model at all: your prompt "
            "is parsed with rules and the design comes from the built-in "
            "templates. 'ollama' uses a local model; 'openai' covers any "
            "OpenAI-compatible endpoint via --base-url."
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
        "--boards",
        type=int,
        default=1,
        metavar="N",
        help=(
            "How many boards you are building (default 1). Quantities in the "
            "purchase list scale with this."
        ),
    )
    parser.add_argument(
        "--ambient",
        type=float,
        default=25.0,
        metavar="C",
        help=(
            "Ambient temperature the design must work in, for the thermal "
            "budget (default 25). An enclosure is much worse than a bench."
        ),
    )
    parser.add_argument(
        "--spares",
        type=float,
        default=0.0,
        metavar="FRACTION",
        help=(
            "Extra parts allowance as a fraction, e.g. 0.1 for 10%% spares for "
            "hand assembly (default 0)."
        ),
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

    provider_is_mock = args.provider == "mock"

    request = DesignRequest(
        prompt=args.prompt,
        project_name=args.project_name,
        run_spice=not args.no_spice,
        run_routing=not args.no_routing,
        mcp_validate=args.mcp_validate,
        boards=args.boards,
        spare_fraction=args.spares,
        ambient_c=args.ambient,
    )
    summary = await orchestrator.process_request(request, output_dir)

    print("\n🧾 Design Provenance:")
    print(f"  Topology: {summary.topology or 'n/a'}")
    if summary.used_llm:
        print("  Source:   LLM-generated specification")
    elif provider_is_mock:
        print(
            "  Source:   rule-based (no model configured; your prompt was parsed "
            "with rules)"
        )
    else:
        print(
            "  Source:   ⚠️  rule-based template "
            "(the model was unavailable and fallback was allowed)"
        )
    for note in summary.design_notes[:6]:
        print(f"  Note:     {note}")

    # What the parser filled in rather than read. A guessed rail decides whether
    # the design works, so it is stated rather than left in the finished design.
    assumptions = (summary.requirements or {}).get("assumptions") or []
    for assumption in assumptions:
        print(f"  Assumed:  {assumption}")

    print("\n🔍 ERC Report Summary:")
    print(f"  Status: {'✅ PASSED' if summary.erc_report.passed else '❌ FAILED'}")
    for key, value in summary.erc_report.summary.items():
        print(f"  - {key.capitalize()}: {value}")

    review = summary.design_review
    if review is not None and review.findings:
        print("\n📐 Electrical Review:")
        print(
            f"  Status: {'❌ PROBLEMS FOUND' if review.failures else '✅ NO PROBLEMS'}"
            f" ({review.summary()})"
        )
        for finding in review.sorted_findings():
            print(f"  {finding.render()}")
        # Where the ratings came from, and what was assumed to get them. Without
        # this the reader cannot tell which part was checked.
        for assumption in review.assumptions:
            print(f"  · {assumption}")
        if review.failures:
            print(
                "  Build this only after fixing the failures above: they are "
                "design errors, not opinions."
            )

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

    # The purchase list is what the design is turned into an order from, so it is
    # what gets printed. The raw BOM stays in design_summary.json.
    purchase = summary.purchase_list
    if purchase is not None and purchase.lines:
        boards = purchase.boards
        print(
            f"\n🛒 Purchase list ({boards} board{'s' if boards != 1 else ''}, "
            f"JLCPCB):"
        )
        print(
            f"  {'Refs':<10} {'Value':<9} {'Order':>6}  {'LCSC':<10} "
            f"{'Part':<24} {'Unit':>8} {'Line':>8}"
        )
        for line in purchase.lines:
            refs = ", ".join(line.designators)
            lcsc = line.lcsc_part or "—"
            part = (line.order_mpn or line.mpn or "—")[:24]
            if line.price_source == "unknown":
                unit = line_total = "—"
            else:
                unit = f"${line.unit_price:.4f}"
                line_total = f"${line.line_total:.2f}"
            print(
                f"  {refs:<10} {line.value[:9]:<9} {line.order_quantity:>6}  "
                f"{lcsc:<10} {part:<24} {unit:>8} {line_total:>8}"
            )
        if purchase.has_placeholder_prices:
            print(f"\n  Estimated total: ${purchase.total_cost:.2f} (includes placeholder prices)")
        else:
            print(f"\n  Estimated total: ${purchase.total_cost:.2f}")
        print("  Prices exclude assembly, stencil and shipping.")
        for warning in purchase.warnings():
            print(f"  ⚠️  {warning}")
    else:
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

        if command == "parts-search":
            parts = argparse.ArgumentParser(
                prog="ai-electronics-design parts-search",
                description=(
                    "Search the component catalog. Values are matched "
                    "numerically, so '10k 0603' does not return 110k parts."
                ),
            )
            parts.add_argument("query", help='For example "10k 0603" or "100nF 50V 0805"')
            parts.add_argument("--package", default=None, help="Package filter")
            parts.add_argument("--category", default=None, help="Category filter")
            parts.add_argument(
                "--min-stock", type=int, default=0, help="Minimum stock (default 0)"
            )
            parts.add_argument("-n", "--limit", type=int, default=15)
            parts.add_argument(
                "--sort",
                choices=["stock", "price", "value"],
                default="stock",
            )
            p_args = parts.parse_args(rest)
            return _run_parts_search(
                p_args.query, p_args.package, p_args.category,
                p_args.min_stock, p_args.limit, p_args.sort,
            )

        if command == "parts-substitute":
            substitute = argparse.ArgumentParser(
                prog="ai-electronics-design parts-substitute",
                description=(
                    "Find parts that can replace a given part, listing what was "
                    "verified and what was not."
                ),
            )
            substitute.add_argument("lcsc_part", help="LCSC number, e.g. C18212698")
            substitute.add_argument("-n", "--limit", type=int, default=10)
            substitute.add_argument(
                "--min-stock",
                type=int,
                default=None,
                help="Minimum stock (default: the original part's minimum order)",
            )
            substitute.add_argument(
                "--any-package",
                action="store_true",
                help="Allow a different package (the footprint will not fit)",
            )
            s_args = substitute.parse_args(rest)
            return _run_parts_substitute(
                s_args.lcsc_part, s_args.limit, s_args.min_stock,
                not s_args.any_package,
            )

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
