"""
Unit tests for Component Database.
"""

from src.components.database import ComponentDatabase


def test_component_db_search():
    db = ComponentDatabase()

    results = db.search("AMS1117")
    assert len(results) >= 1
    assert results[0].mpn == "AMS1117-3.3"

    ldos = db.search(category="regulator_ldo")
    assert len(ldos) >= 1

    mcu = db.get_by_mpn("ESP32-WROOM-32E")
    assert mcu is not None
    assert mcu.category == "microcontroller"


def test_component_db_get_by_mpn():
    db = ComponentDatabase()
    res = db.get_by_mpn("C-10uF-0805")
    assert res is not None
    assert res.value == "10uF"
    assert res.package == "0805"
