"""
Component Database and Parts Registry for AI-Powered Electronics Design Platform.

Provides component search, parametric matching, symbol/footprint resolution,
and distributor inventory data.
"""

import sqlite3
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from pathlib import Path


@dataclass
class ComponentSpec:
    mpn: str
    manufacturer: str
    category: str
    value: str
    package: str
    symbol: str
    footprint: str
    description: str
    stock: int
    price: float
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mpn": self.mpn,
            "manufacturer": self.manufacturer,
            "category": self.category,
            "value": self.value,
            "package": self.package,
            "symbol": self.symbol,
            "footprint": self.footprint,
            "description": self.description,
            "stock": self.stock,
            "price": self.price,
            "attributes": self.attributes,
        }


class ComponentDatabase:
    """
    In-memory and persistent SQLite component database with parametric search.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path
        self._parts_catalog: List[ComponentSpec] = []
        self._load_standard_parts()

    def _load_standard_parts(self):
        """Loads a standard set of common electronic components."""
        self._parts_catalog = [
            # Regulators
            ComponentSpec(
                mpn="AMS1117-3.3",
                manufacturer="Advanced Monolithic Systems",
                category="regulator_ldo",
                value="3.3V",
                package="SOT-223",
                symbol="Regulator_Linear:AMS1117-3.3",
                footprint="Package_TO_SOT_SMD:SOT-223-3_TabPin2",
                description="1A Low Dropout Voltage Regulator 3.3V",
                stock=50000,
                price=0.15,
                attributes={"v_in_max": 15.0, "v_out": 3.3, "i_max": 1.0},
            ),
            ComponentSpec(
                mpn="LM7805",
                manufacturer="Texas Instruments",
                category="regulator_ldo",
                value="5V",
                package="TO-220",
                symbol="Regulator_Linear:LM7805",
                footprint="Package_TO_SOT_THT:TO-220-3_Vertical",
                description="1.5A Positive Voltage Regulator 5V",
                stock=25000,
                price=0.35,
                attributes={"v_in_max": 35.0, "v_out": 5.0, "i_max": 1.5},
            ),
            # Passives
            ComponentSpec(
                mpn="C-10uF-0805",
                manufacturer="Yageo",
                category="capacitor",
                value="10uF",
                package="0805",
                symbol="Device:C",
                footprint="Capacitor_SMD:C_0805_2012Metric",
                description="Capacitor MLCC 10uF 25V X7R 0805",
                stock=100000,
                price=0.02,
                attributes={"voltage_rating": 25.0},
            ),
            ComponentSpec(
                mpn="C-22uF-0805",
                manufacturer="Yageo",
                category="capacitor",
                value="22uF",
                package="0805",
                symbol="Device:C",
                footprint="Capacitor_SMD:C_0805_2012Metric",
                description="Capacitor MLCC 22uF 16V X5R 0805",
                stock=80000,
                price=0.03,
                attributes={"voltage_rating": 16.0},
            ),
            ComponentSpec(
                mpn="R-330-0805",
                manufacturer="Yageo",
                category="resistor",
                value="330",
                package="0805",
                symbol="Device:R",
                footprint="Resistor_SMD:R_0805_2012Metric",
                description="Resistor 330 Ohm 1% 1/8W 0805",
                stock=200000,
                price=0.01,
                attributes={"power_rating": 0.125},
            ),
            ComponentSpec(
                mpn="R-10K-0805",
                manufacturer="Yageo",
                category="resistor",
                value="10k",
                package="0805",
                symbol="Device:R",
                footprint="Resistor_SMD:R_0805_2012Metric",
                description="Resistor 10k Ohm 1% 1/8W 0805",
                stock=200000,
                price=0.01,
                attributes={"power_rating": 0.125},
            ),
            # LEDs
            ComponentSpec(
                mpn="LED-GREEN-0805",
                manufacturer="Lite-On",
                category="led",
                value="Green",
                package="0805",
                symbol="Device:LED",
                footprint="LED_SMD:LED_0805_2012Metric",
                description="LED Green Clear 0805 SMD",
                stock=150000,
                price=0.04,
                attributes={"forward_voltage": 2.1, "current_ma": 20},
            ),
            # Microcontrollers
            ComponentSpec(
                mpn="ESP32-WROOM-32E",
                manufacturer="Espressif Systems",
                category="microcontroller",
                value="ESP32",
                package="Module",
                symbol="RF_Module:ESP32-WROOM-32",
                footprint="RF_Module:ESP32-WROOM-32",
                description="Wi-Fi & Bluetooth MCU Module",
                stock=30000,
                price=2.80,
                attributes={"voltage": 3.3, "wifi": True, "bluetooth": True},
            ),
        ]

    def search(self, query: str = "", category: Optional[str] = None) -> List[ComponentSpec]:
        """
        Searches catalog matching query string or category filter.
        """
        results = []
        q = query.lower().strip()

        for part in self._parts_catalog:
            if category and part.category != category:
                continue

            if not q or (
                q in part.mpn.lower()
                or q in part.manufacturer.lower()
                or q in part.value.lower()
                or q in part.description.lower()
            ):
                results.append(part)

        return results

    def get_by_mpn(self, mpn: str) -> Optional[ComponentSpec]:
        """Finds exact component by Manufacturer Part Number (MPN)."""
        for part in self._parts_catalog:
            if part.mpn.lower() == mpn.lower():
                return part
        return None
