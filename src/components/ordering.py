"""
Turning a design into something that can actually be bought.

Why this exists
---------------
A design that generates a correct schematic, a routed board and a list of parts
is not yet useful if you cannot order the parts. The bill of materials this
platform produced named parts like ``CC0805KRX7R9BB106`` — plausible-looking
manufacturer part numbers that **do not exist in the JLCPCB catalogue**, priced
from a hardcoded placeholder table. An AMS1117 module was quoted at $0.15 when
the catalogue price is $0.0181.

This module closes that gap. For every part in the design it finds the real,
in-stock catalogue entry for the same value and package, and reports:

* the **LCSC part number** — the only identifier JLCPCB's order form accepts;
* **stock**, so a design cannot quietly depend on a part nobody has;
* the **unit price at the quantity being ordered**, from the catalogue's tier
  table: the price at 10 pieces is not the price at 10,000;
* an **order quantity** rounded up to what the distributor actually sells, plus
  the spare allowance JLCPCB consumes per board.

What it deliberately does not do
--------------------------------
It does not change the design. The schematic keeps the symbol and pinout it was
built and validated against. When the orderable part is a *different*
manufacturer's part with the same value and package, that is stated in plain
words on the line, because two parts that share a value and a package do not
always share a pinout. A silent swap here would be the most expensive kind of
bug: it survives every automated check and fails on the bench.
"""

from __future__ import annotations

import csv
import io
import math
import re
from difflib import SequenceMatcher
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

# Where a bill-of-materials line's price came from. Reported so that a total is
# never presented as a distributor quote when it is a placeholder.
PRICE_CATALOG = "catalog"
PRICE_PLACEHOLDER = "placeholder"
PRICE_UNKNOWN = "unknown"


def package_from_footprint(footprint: str) -> str:
    """
    Best-effort package name from a KiCad footprint identifier.

    Used only when a component does not state its package. The KiCad footprint
    ``Resistor_SMD:R_0805_2012Metric`` and the catalogue package ``0805`` are the
    same thing written two ways, and a design from the LLM path may only have the
    former.

    Returns an empty string when nothing can be read, rather than guessing: a
    wrong package finds a wrong part.
    """
    if not footprint:
        return ""

    name = footprint.split(":")[-1]

    # Chip packages: R_0805_2012Metric, C_0603_1608Metric, LED_0805_2012Metric.
    chip = re.search(r"(?:^|_)(\d{4})_\d{4}Metric", name)
    if chip:
        return chip.group(1)

    # SOT-223-3_TabPin2, SOT-23-3, SOP-8, QFN-32, DIP-8, DPAK...
    family = re.match(
        r"(SOT|SOD|SOIC|SOP|SSOP|TSSOP|MSOP|QFN|DFN|LQFP|TQFP|DIP|TO|DO|DPAK|D2PAK)"
        r"[-_]?(\d+)",
        name,
        re.IGNORECASE,
    )
    if family:
        return f"{family.group(1).upper()}-{family.group(2)}"

    return ""


def unit_price_at(prices: Sequence[Dict[str, Any]], quantity: int) -> Optional[float]:
    """
    The unit price for a given order quantity, from a tier table.

    Tiers are ``[{"quantity": 1, "unit_price": 0.04}, {"quantity": 200, ...}]``
    with the quantity ascending. The applicable tier is the highest one whose
    threshold the order reaches; below the first threshold the first tier applies,
    because that is the smallest quantity the distributor will sell.

    Returns ``None`` for an empty or unusable table, so callers can fall back to
    a single price or report the price as unknown.
    """
    usable: List[Tuple[int, float]] = []
    for tier in prices or ():
        try:
            threshold = int(tier.get("quantity") or 0)
            price = float(tier.get("unit_price") or 0)
        except (TypeError, ValueError, AttributeError):
            continue
        if price > 0:
            usable.append((max(threshold, 1), price))
    if not usable:
        return None

    usable.sort()
    applicable = usable[0][1]
    for threshold, price in usable:
        if quantity >= threshold:
            applicable = price
        else:
            break
    return applicable


def minimum_order_quantity(attrition: Optional[Dict[str, Any]], fallback: int = 1) -> int:
    """
    The smallest quantity JLCPCB will accept for a part.

    JLCPCB publishes three numbers per part inside a JSON blob rather than in
    columns, and two of them are minimums: ``minPurchaseNum`` (the purchase
    minimum) and ``leastNumber`` / ``leastPatchNumber`` (the smallest quantity it
    will place). The larger of the two is what an order form will actually
    accept. The CDFER CSV calls ``leastNumber`` "Min Order Qty", which is the
    reading used here.
    """
    values = [max(int(fallback or 1), 1)]
    for key in ("minPurchaseNum", "leastNumber", "leastPatchNumber"):
        if not attrition:
            continue
        try:
            candidate = int(attrition.get(key) or 0)
        except (TypeError, ValueError):
            continue
        if candidate > 0:
            values.append(candidate)
    return max(values)


def attrition_allowance(attrition: Optional[Dict[str, Any]]) -> int:
    """
    The extra pieces JLCPCB reports consuming, per board.

    ``lossNumber`` is the attrition figure — parts lost in handling and
    placement. JLCPCB does not document whether it applies per board or per
    order, so the arithmetic is written into the purchase line where the buyer
    can see and adjust it. It is charged per board here, because running short on
    the last board is the failure that costs a second order.
    """
    if not attrition:
        return 0
    try:
        return max(int(attrition.get("lossNumber") or 0), 0)
    except (TypeError, ValueError):
        return 0


def order_quantity_for(
    needed: int,
    min_order: int = 1,
    attrition: Optional[Dict[str, Any]] = None,
    boards: int = 1,
    spare_fraction: float = 0.0,
) -> int:
    """
    How many pieces to actually order for a given number of boards.

    Four things push the order above the raw designator count:

    1. **The number of boards.** Five boards need five of the part.
    2. **The distributor's minimum order quantity.** A part JLCPCB will not sell
       in fewer than 20 pieces is ordered in 20, however few are needed.
    3. **Attrition.** The extra pieces JLCPCB reports consuming.
    4. **A spare allowance** the caller asks for, for hand assembly.

    ``PurchaseLine.notes`` records the arithmetic, so the number is never
    unexplained.
    """
    needed = max(int(needed), 0)
    boards = max(int(boards), 1)
    required = needed * boards

    required += attrition_allowance(attrition) * boards
    if spare_fraction > 0:
        required += int(math.ceil(required * spare_fraction))

    return max(required, minimum_order_quantity(attrition, min_order), 1)


@dataclass
class PurchaseLine:
    """One line of a purchase list: what to buy, how many, and why."""

    mpn: str                     # the part as designed
    value: str
    footprint: str
    designators: List[str] = field(default_factory=list)
    quantity: int = 0            # pieces the boards need
    order_quantity: int = 0      # pieces to actually order
    lcsc_part: Optional[str] = None
    order_mpn: Optional[str] = None       # the orderable part's MPN
    manufacturer: str = ""
    package: str = ""
    stock: Optional[int] = None
    unit_price: float = 0.0
    price_source: str = PRICE_UNKNOWN
    prices: List[Dict[str, Any]] = field(default_factory=list)
    min_order: int = 1
    attrition: Dict[str, Any] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    datasheet_url: str = ""
    product_url: str = ""
    # True when the orderable part is a different part number *and* has a pinout
    # that could differ. Kept as its own field so the summary warning and the
    # per-line notes cannot disagree.
    pinout_check_required: bool = False

    @property
    def line_total(self) -> float:
        if self.price_source == PRICE_UNKNOWN:
            return 0.0
        return self.unit_price * self.order_quantity

    @property
    def orderable(self) -> bool:
        """Whether there is a real catalogue part to order."""
        return bool(self.lcsc_part)

    @property
    def in_stock(self) -> bool:
        """Whether stock covers the order. Unknown stock counts as not in stock."""
        if not self.orderable or self.stock is None:
            return False
        return self.stock >= self.order_quantity

    @property
    def needs_review(self) -> bool:
        """Whether a human has to look at this line before ordering."""
        return bool(self.notes)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mpn": self.mpn,
            "value": self.value,
            "footprint": self.footprint,
            "designators": list(self.designators),
            "quantity": self.quantity,
            "order_quantity": self.order_quantity,
            "lcsc_part": self.lcsc_part,
            "order_mpn": self.order_mpn,
            "manufacturer": self.manufacturer,
            "package": self.package,
            "stock": self.stock,
            "unit_price": self.unit_price,
            "price_source": self.price_source,
            "line_total": round(self.line_total, 4),
            "min_order": self.min_order,
            "attrition": self.attrition,
            "orderable": self.orderable,
            "in_stock": self.in_stock,
            "pinout_check_required": self.pinout_check_required,
            "notes": list(self.notes),
            "datasheet_url": self.datasheet_url,
            "product_url": self.product_url,
        }


@dataclass
class PurchaseList:
    """A bill of materials that can be ordered, with its own caveats."""

    lines: List[PurchaseLine] = field(default_factory=list)
    boards: int = 1
    source: str = ""

    @property
    def total_cost(self) -> float:
        return sum(line.line_total for line in self.lines)

    @property
    def orderable_lines(self) -> List[PurchaseLine]:
        return [line for line in self.lines if line.orderable]

    @property
    def unorderable_lines(self) -> List[PurchaseLine]:
        return [line for line in self.lines if not line.orderable]

    @property
    def out_of_stock_lines(self) -> List[PurchaseLine]:
        return [line for line in self.lines if line.orderable and not line.in_stock]

    @property
    def total_parts(self) -> int:
        return sum(line.order_quantity for line in self.lines)

    @property
    def has_placeholder_prices(self) -> bool:
        return any(line.price_source == PRICE_PLACEHOLDER for line in self.lines)

    def warnings(self) -> List[str]:
        """
        Everything a buyer should know before placing the order.

        Deliberately explicit: a total that mixes catalogue prices with
        placeholders, or an order that cannot be filled, has to say so.
        """
        warnings: List[str] = []

        unorderable = self.unorderable_lines
        if unorderable:
            warnings.append(
                f"{len(unorderable)} line(s) have no catalog part and cannot be "
                "ordered from JLCPCB: "
                + ", ".join(f"{line.mpn} ({line.value})" for line in unorderable)
            )

        short = self.out_of_stock_lines
        if short:
            warnings.append(
                f"{len(short)} line(s) do not have enough stock for "
                f"{self.boards} board(s): "
                + ", ".join(
                    f"{line.lcsc_part} has {line.stock:,} but "
                    f"{line.order_quantity:,} are needed"
                    for line in short
                )
            )

        if self.has_placeholder_prices:
            warnings.append(
                "Some prices are placeholders from the built-in catalog, not "
                "distributor prices. Install the full catalog with "
                "'ai-electronics-design catalog-setup' for real prices and stock."
            )

        pinout_risk = [line for line in self.lines if line.pinout_check_required]
        if pinout_risk:
            warnings.append(
                f"{len(pinout_risk)} line(s) would be ordered as a different part "
                "number than the design names. The value and package match, but "
                "verify the pinout against the datasheet before ordering: "
                + ", ".join(
                    f"{line.designators[0]} ({line.mpn} -> {line.order_mpn})"
                    for line in pinout_risk
                )
            )

        return warnings

    # -- output ------------------------------------------------------------

    def to_jlcpcb_csv(self) -> str:
        """
        The CSV JLCPCB's assembly order form accepts.

        Columns: Comment, Designator, Footprint, LCSC Part #. One row per part
        with every designator that uses it, which is the format the uploader
        expects — one row per designator is rejected.
        """
        out = io.StringIO()
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
        for line in self.lines:
            if not line.orderable:
                continue
            writer.writerow(
                [
                    line.value or line.mpn,
                    ",".join(line.designators),
                    line.footprint,
                    line.lcsc_part,
                ]
            )
        return out.getvalue()

    def to_markdown(self) -> str:
        """A readable purchase list, with the caveats attached to the lines."""
        lines: List[str] = []
        lines.append("# Purchase list")
        lines.append("")
        if self.boards == 1:
            lines.append("Quantities are for **1 board**.")
        else:
            lines.append(f"Quantities are for **{self.boards} boards**.")
        lines.append("")
        lines.append(f"Source: {self.source or 'unknown'}")
        lines.append("")

        for warning in self.warnings():
            lines.append(f"> **Warning** — {warning}")
        if self.warnings():
            lines.append("")

        lines.append(
            "| Designators | Value | Order | LCSC | Part | Unit | Line | Stock |"
        )
        lines.append("|---|---|---:|---|---|---:|---:|---:|")
        for line in self.lines:
            if line.lcsc_part:
                url = line.product_url or f"https://jlcpcb.com/partdetail/{line.lcsc_part}"
                lcsc = f"[{line.lcsc_part}]({url})"
            else:
                lcsc = "—"
            part = line.order_mpn or line.mpn
            price = "—" if line.price_source == PRICE_UNKNOWN else f"${line.unit_price:.4f}"
            total = "—" if line.price_source == PRICE_UNKNOWN else f"${line.line_total:.2f}"
            stock = f"{line.stock:,}" if line.stock is not None else "unknown"
            if line.orderable and not line.in_stock:
                stock = f"**{stock}**"
            lines.append(
                f"| {', '.join(line.designators)} | {line.value} | "
                f"{line.order_quantity} | {lcsc} | {part} | {price} | {total} | {stock} |"
            )

        lines.append("")
        if self.has_placeholder_prices:
            lines.append(f"**Estimated total: ${self.total_cost:.2f}** (includes placeholder prices)")
        else:
            lines.append(f"**Estimated total: ${self.total_cost:.2f}**")
        lines.append("")
        lines.append(
            "Prices are JLCPCB quantity-tier prices for the order quantity shown "
            "and exclude assembly, stencil and shipping fees."
        )

        detailed = [line for line in self.lines if line.notes]
        if detailed:
            lines.append("")
            lines.append("## Notes")
            lines.append("")
            for line in detailed:
                lines.append(f"**{line.mpn}** ({', '.join(line.designators)})")
                lines.append("")
                for note in line.notes:
                    lines.append(f"- {note}")
                lines.append("")

        return "\n".join(lines)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "boards": self.boards,
            "source": self.source,
            "lines": [line.to_dict() for line in self.lines],
            "total_cost": round(self.total_cost, 4),
            "total_parts": self.total_parts,
            "orderable_lines": len(self.orderable_lines),
            "unorderable_lines": len(self.unorderable_lines),
            "out_of_stock_lines": len(self.out_of_stock_lines),
            "warnings": self.warnings(),
        }


# ---------------------------------------------------------------------------
# Building the list
# ---------------------------------------------------------------------------

# The component type's value doubles as the platform's category name for most
# types; these are the exceptions.
_CATEGORY_OVERRIDES: Dict[str, str] = {
    "chip": "",
    "custom": "",
    "voltage_source": "",
    "current_source": "",
    "testpoint": "",
}

# How many candidates to consider when looking for the orderable equivalent of a
# design part. Small: the first few by stock are the realistic choices, and a
# long list only invites a poor match.
_CANDIDATE_LIMIT = 5


def _category_for(component: Any) -> str:
    component_type = getattr(component, "component_type", None)
    name = getattr(component_type, "value", "") or ""
    return _CATEGORY_OVERRIDES.get(name, name)


def _design_value(component: Any) -> str:
    """
    The value to search the catalogue with.

    A component that came from the catalogue already states its specification
    ("10kΩ 100mW ±1%"), which searches badly because the parser reads the first
    number and ignores the rest. The bare value ("10k") is what to ask for, and
    the catalogue attributes carry the rest.
    """
    value = (getattr(component, "value", "") or "").strip()
    return value


# Component categories with exactly two interchangeable terminals. Swapping one
# for another of the same value is genuinely harmless, so the pinout warning
# would be noise — and noise in a warning list is what makes real warnings get
# ignored.
_NON_POLARISED_PASSIVES = frozenset({"resistor", "capacitor", "inductor"})


def _match_notes(
    design: Dict[str, Any], catalog: Dict[str, Any], category: str = ""
) -> List[str]:
    """
    Caveats for using a catalogue part in place of the designed one.

    Only differences that were actually observed are reported. The point is to
    leave the buyer with an honest account, not a reassuring one — nor a
    frightening one: a 10 kΩ resistor is a 10 kΩ resistor whichever factory made
    it, and saying otherwise would train the reader to skip the warnings.
    """
    notes: List[str] = []

    if catalog.get("package") and design.get("package"):
        catalog_package = str(catalog["package"]).upper().replace(" ", "")
        design_package = str(design["package"]).upper().replace(" ", "")
        if catalog_package != design_package:
            notes.append(
                f"Package differs: the design uses {design['package']}, this part "
                f"is {catalog['package']}. The footprint will not fit."
            )

    design_mpn = (design.get("mpn") or "").strip()
    order_mpn = (catalog.get("mpn") or "").strip()
    if design_mpn and order_mpn and design_mpn.lower() != order_mpn.lower():
        if category in _NON_POLARISED_PASSIVES:
            notes.append(
                f"Different manufacturer's part: the design names {design_mpn}, "
                f"this is {order_mpn}. Same value and package; a two-terminal "
                f"passive has no pinout to check."
            )
        else:
            notes.append(
                f"Different part number: the design names {design_mpn}, this is "
                f"{order_mpn}. Same value and package, but verify the pinout "
                f"before ordering — matching values do not guarantee matching pins."
            )

        # A near-miss is the dangerous case, not a completely different number.
        # "LM337L" and "LM317L" are one character apart and one is a negative
        # regulator while the other is positive; a value of "Adjustable" cannot
        # tell them apart, so the difference has to be stated in words.
        similarity = SequenceMatcher(
            None, design_mpn.lower(), order_mpn.lower()
        ).ratio()
        if similarity >= 0.7:
            notes.append(
                f"**The two part numbers are nearly identical** "
                f"({design_mpn} vs {order_mpn}, {similarity:.0%} alike). Part "
                f"numbers one character apart are often different parts — check "
                f"the datasheet before ordering."
            )

    # A value like "Green" or "Adjustable" describes a class of part, not one
    # part. Matching on it alone can land on the wrong function.
    if design.get("value") and not re.search(r"\d", str(design["value"])):
        notes.append(
            f"The value {design['value']!r} does not contain a number, so it does "
            f"not identify a specific part. Confirm the orderable part is the "
            f"same function, not just the same kind of component."
        )

    return notes


def build_purchase_list(
    circuit: Any,
    db: Any,
    boards: int = 1,
    spare_fraction: float = 0.0,
    min_stock: int = 0,
    source: str = "",
) -> PurchaseList:
    """
    Turn a Circuit IR into a purchase list.

    Parts already in the catalogue are looked up by exact part number, which
    keeps the design's own part when it is real. Otherwise the catalogue is
    searched for the same value and package, and the line says that the orderable
    part is a different one.

    Args:
        circuit: A ``CircuitIR``.
        db: A ``ComponentDatabase``. Without a catalogue, every line falls back
            to placeholder pricing and is marked accordingly.
        boards: How many copies of the board are being built.
        spare_fraction: Extra allowance, e.g. ``0.1`` for 10% spares, for hand
            assembly.
        min_stock: Ignore catalogue candidates below this stock level.
        source: A description of where the parts data came from, for the output.
    """
    purchase = PurchaseList(boards=max(int(boards), 1), source=source or getattr(db, "data_source", ""))

    # Group by part number first: three 100 nF capacitors are one line.
    grouped: Dict[str, List[Any]] = {}
    for component in circuit.components.values():
        key = component.mpn or f"{component.value}|{component.footprint}"
        grouped.setdefault(key, []).append(component)

    for components in grouped.values():
        design = components[0]
        line = PurchaseLine(
            mpn=design.mpn or design.value,
            value=str(design.value or ""),
            footprint=design.footprint or "",
            designators=[c.ref for c in components],
            quantity=len(components),
            package=getattr(design, "package", "") or package_from_footprint(
                design.footprint or ""
            ),
        )

        candidate = _find_orderable_part(design, db, line.package, min_stock)
        if candidate is None:
            line.notes.append(
                "No catalog part matched this value and package, so it cannot be "
                "ordered from JLCPCB through this list. Search for it by hand."
            )
            if getattr(db, "using_jlcparts", False) is False:
                line.notes.append(
                    "The full component catalog is not installed; run "
                    "'ai-electronics-design catalog-setup' and rebuild."
                )
            # Even without a catalogue part the line still needs a quantity, so
            # the reader sees how many pieces the boards need.
            line.order_quantity = order_quantity_for(
                needed=line.quantity, boards=purchase.boards,
                spare_fraction=spare_fraction,
            )
            purchase.lines.append(line)
            continue

        _apply_candidate(
            line, design, candidate, purchase.boards, spare_fraction,
            category=_category_for(design),
        )
        purchase.lines.append(line)

    # Biggest spend first: that is the order in which a buyer wants to look.
    purchase.lines.sort(key=lambda line: (-line.line_total, line.mpn))
    return purchase


def _find_orderable_part(
    design: Any, db: Any, package: str, min_stock: int
) -> Optional[Dict[str, Any]]:
    """
    The catalogue entry to order for a designed component.

    Order of preference:

    1. The design's own part number, if the catalogue has it. This is the only
       case where the schematic and the order agree exactly.
    2. The best in-stock part with the same value and package.
    """
    mpn = (design.mpn or "").strip()
    if mpn:
        for spec in _safe(lambda: db.find_in_catalog(mpn)) or []:
            entry = spec.to_dict()
            if not min_stock or (entry.get("stock") or 0) >= min_stock:
                return entry

    category = _category_for(design)
    value = _design_value(design)
    if not value:
        return None

    query = f"{value} {package}".strip()

    def search(**kwargs: Any) -> List[Any]:
        return _safe(lambda: db.search(**kwargs)) or []

    candidates = search(query=query, category=category or None, min_stock=min_stock, limit=_CANDIDATE_LIMIT)
    if not candidates and min_stock:
        candidates = search(query=query, category=category or None, limit=_CANDIDATE_LIMIT)
    if not candidates and package:
        # The package may be the reason nothing matched — a part in another
        # package is still useful if the footprint is checked, but it is not a
        # substitute for a missing value.
        candidates = search(query=value, category=category or None, limit=_CANDIDATE_LIMIT)
    if not candidates:
        return None

    # Prefer a candidate whose package matches, then the most stock.
    wanted = (package or "").upper().replace(" ", "")

    def rank(spec: Any) -> Tuple[int, int]:
        spec_package = str(getattr(spec, "package", "")).upper().replace(" ", "")
        matches = 0 if (not wanted or wanted in spec_package) else 1
        return (matches, -int(getattr(spec, "stock", 0) or 0))

    candidates.sort(key=rank)
    return candidates[0].to_dict()


def _safe(action: Any) -> Any:
    """Run a database call, turning an unexpected failure into no result."""
    try:
        return action()
    except Exception:  # pragma: no cover - defensive against DB quirks
        return None


def _apply_candidate(
    line: PurchaseLine,
    design: Any,
    candidate: Dict[str, Any],
    boards: int,
    spare_fraction: float,
    category: str = "",
) -> None:
    """Copy the catalogue part's ordering data onto the line, with caveats."""
    line.lcsc_part = candidate.get("lcsc_part") or None
    line.order_mpn = candidate.get("mpn") or None
    line.manufacturer = candidate.get("manufacturer") or ""
    line.package = candidate.get("package") or line.package
    line.stock = candidate.get("stock")
    line.min_order = int(candidate.get("min_order") or 1)
    line.attrition = dict(candidate.get("attrition") or {})
    line.prices = list(candidate.get("prices") or [])
    line.datasheet_url = candidate.get("datasheet_url") or ""
    line.product_url = candidate.get("product_url") or ""

    if not line.lcsc_part:
        # The only thing that matched is a built-in placeholder part. It gives a
        # rough cost and nothing else: with no LCSC number it cannot go on an
        # order, and its price is not a distributor price.
        line.notes.append(
            f"Matched the built-in list part {line.order_mpn or line.mpn}, which "
            "has no LCSC number and cannot be ordered from JLCPCB. The price "
            "shown is an estimate, not a quote."
        )

    line.order_quantity = order_quantity_for(
        needed=line.quantity,
        min_order=line.min_order,
        attrition=line.attrition,
        boards=boards,
        spare_fraction=spare_fraction,
    )

    tier_price = unit_price_at(line.prices, line.order_quantity)
    if tier_price is not None:
        line.unit_price = tier_price
        line.price_source = PRICE_CATALOG
    elif candidate.get("lcsc_part") and candidate.get("price"):
        # In the catalogue but without a usable tier table: the single price is
        # still a distributor price.
        line.unit_price = float(candidate["price"])
        line.price_source = PRICE_CATALOG
        line.notes.append(
            "No quantity price breaks published for this part; the single unit "
            "price is used."
        )
    elif candidate.get("price"):
        # A built-in placeholder part. The price is an estimate, not a quote.
        line.unit_price = float(candidate["price"])
        line.price_source = PRICE_PLACEHOLDER
    else:
        line.unit_price = 0.0
        line.price_source = PRICE_UNKNOWN

    line.notes.extend(
        _match_notes(
            {
                "mpn": line.mpn,
                "value": line.value,
                "package": design_package(design),
            },
            candidate,
            category,
        )
    )
    line.pinout_check_required = (
        category not in _NON_POLARISED_PASSIVES
        and bool(line.order_mpn)
        and bool(line.mpn)
        and line.order_mpn.lower() != line.mpn.lower()
    )

    # Show the arithmetic whenever the order is larger than the design needs, so
    # a quantity is never just a number the buyer has to trust.
    minimum = minimum_order_quantity(line.attrition, line.min_order)
    spare = attrition_allowance(line.attrition) * boards
    if line.order_quantity != line.quantity * boards:
        reasons: List[str] = []
        if spare:
            reasons.append(f"attrition {attrition_allowance(line.attrition)}/board")
        if minimum > line.quantity * boards:
            reasons.append(f"minimum order {minimum}")
        if spare_fraction > 0:
            reasons.append(f"{spare_fraction * 100:g}% spares")
        if reasons:
            line.notes.append(
                f"Quantity {line.order_quantity} = {line.quantity} x {boards} "
                f"board(s) + {' + '.join(reasons)}."
            )


def design_package(design: Any) -> str:
    """The design's package name, from the field or the footprint."""
    return getattr(design, "package", "") or package_from_footprint(
        getattr(design, "footprint", "") or ""
    )
