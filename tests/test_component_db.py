"""
Unit tests for Component Database and the offline component catalog.
"""

from pathlib import Path

import pytest

from src.components.database import ComponentDatabase


def test_component_db_search():
    db = ComponentDatabase()

    if db.using_jlcparts:
        results = db.search("AMS1117")
        assert len(results) >= 1
        # Every result is an AMS1117 variant. Which variant comes first depends
        # on the catalogue — a Preferred part outranks a bigger-stock one,
        # because Preferred parts avoid JLCPCB's extended-part handling — so the
        # ordering is asserted as a property, not as one part number.
        assert all("AMS1117" in part.mpn.upper() for part in results)
        if any(part.is_preferred for part in results):
            assert results[0].is_preferred

        # "ESP32-WROOM-32E" was one of the invented part numbers this project
        # used to ship. It is not in the catalogue, so the honest answer is that
        # it does not resolve; a real ESP32 module is found by searching.
        assert db.get_by_mpn("ESP32-WROOM-32E") is None
        modules = db.search("ESP32", limit=5)
        assert modules
        assert all(module.lcsc_part for module in modules)
    else:
        # Without the catalogue the search covers the templates: values and
        # packages, no part numbers.
        results = db.search("10k", category="resistor")
        assert results
        assert all(part.mpn == "" for part in results)
        assert all(part.lcsc_part is None for part in results)

    ldos = db.search(category="regulator_ldo")
    assert len(ldos) >= 1


def test_component_db_get_by_mpn():
    """
    Part-number lookup consults the catalogue, and only the catalogue.

    The built-in templates have no part numbers, so a lookup for one of the
    numbers this project used to invent (``CC0805KRX7R9BB106``) must return
    nothing rather than a template wearing that number.
    """
    db = ComponentDatabase()
    assert db.get_by_mpn("CC0805KRX7R9BB106") is None

    # A real part number is found when the catalogue is installed.
    res = db.get_by_mpn("AMS1117-3.3")
    if db.using_jlcparts:
        assert res is not None
        assert res.category == "regulator_ldo"
        assert res.lcsc_part is not None

class TestCatalogDownload:
    """
    The catalog download is the step that makes part selection real.

    It previously pointed at a URL that no longer exists and failed with a bare
    404, so nobody could obtain the full catalog. These tests pin down the
    contract: fail early with a clear message, never install an unverified file.
    """

    def test_catalog_url_is_reachable_shape(self):
        """The configured URL must be an https SQLite endpoint."""
        from src.components.jlcparts import CATALOG_URL

        assert CATALOG_URL.startswith("https://")
        assert CATALOG_URL.endswith(".sqlite3")

    def test_default_path_follows_xdg_cache_home(self, monkeypatch, tmp_path):
        from src.components import jlcparts

        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        assert jlcparts.default_catalog_path() == (
            tmp_path / "kicad-tools" / "jlcparts.sqlite3"
        )

    def test_unwritable_destination_fails_before_downloading(
        self, tmp_path, monkeypatch
    ):
        """A 145 MB transfer must not start if the destination is unusable."""
        import errno

        from src.components import jlcparts

        def refuse(*args, **kwargs):
            raise OSError(errno.EROFS, "Read-only file system")

        monkeypatch.setattr(Path, "mkdir", refuse)
        with pytest.raises(RuntimeError, match="Cannot write to"):
            jlcparts.download_catalog(dest=tmp_path / "sub" / "c.sqlite3", progress=False)

    def test_existing_catalog_is_reused(self, tmp_path):
        """An installed catalog must not be downloaded again."""
        from src.components import jlcparts

        dest = tmp_path / "catalog.sqlite3"
        dest.write_bytes(b"placeholder")

        class Fake:
            def __init__(self, *_args, **_kwargs):
                pass

            def count(self):
                return 1234

        original = jlcparts.JLCPartsDatabase
        jlcparts.JLCPartsDatabase = Fake
        try:
            returned = jlcparts.download_catalog(dest=dest, progress=False)
        finally:
            jlcparts.JLCPartsDatabase = original
        assert returned == dest

    def test_corrupt_download_is_rejected_and_removed(self, tmp_path, monkeypatch):
        """A truncated or error-page response must never become the catalog."""
        from src.components import jlcparts

        class FakeResponse:
            headers = {"content-length": "11"}

            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def raise_for_status(self):
                return None

            def iter_content(self, chunk_size=0):
                yield b"not a sqlite file"

        import requests

        monkeypatch.setattr(requests, "get", lambda *a, **k: FakeResponse())
        with pytest.raises(RuntimeError, match="not a usable catalog"):
            jlcparts.download_catalog(
                dest=tmp_path / "catalog.sqlite3", progress=False
            )
        # The partial file must be cleaned up.
        assert not (tmp_path / "catalog.download.part").exists()
        assert not (tmp_path / "catalog.sqlite3").exists()

    def test_catalog_discovery_prefers_the_environment_variable(
        self, tmp_path, monkeypatch
    ):
        from src.components.jlcparts import JLCPartsDatabase

        catalog = tmp_path / "explicit.sqlite3"
        catalog.write_bytes(b"placeholder")
        monkeypatch.setenv("JLC_PARTS_CATALOG", str(catalog))

        # Constructing the database must pick up the explicit path.
        assert JLCPartsDatabase()._find_catalog() == catalog


class TestTemplateLookup:
    """
    Template circuits pick their parts from the component templates.

    The distinction matters: a template carries a symbol and footprint the rest
    of the pipeline has been checked against, while "whichever catalog part ranks
    first" does not. An earlier version of the orchestrator used the latter and
    silently put a 100 nF capacitor where a 10 µF input capacitor was intended.
    """

    def test_finds_a_template_by_value(self):
        db = ComponentDatabase()
        part = db.find_template("capacitor", value="10uF")
        assert part is not None
        assert part.value == "10uF"

    def test_a_template_carries_no_parts_data(self):
        """
        No part number, manufacturer, price or stock: those are the catalogue's
        job, and the second copy is what produced 28 invented part numbers.
        """
        db = ComponentDatabase()
        part = db.find_template("resistor", value="330")
        assert part is not None
        assert part.mpn == ""
        assert part.manufacturer == ""
        assert part.price == 0.0
        assert part.stock == 0
        assert part.lcsc_part is None

    def test_a_template_still_carries_the_land_pattern(self):
        """Which is the whole reason to keep it."""
        db = ComponentDatabase()
        part = db.find_template("resistor", value="330", package="0805")
        assert part.symbol == "Device:R"
        assert part.footprint == "Resistor_SMD:R_0805_2012Metric"

    def test_package_narrows_the_match(self):
        db = ComponentDatabase()
        found = db.find_template("resistor", value="10k", package="0402")
        assert found is not None
        assert found.footprint == "Resistor_SMD:R_0402_1005Metric"

    def test_a_value_that_is_not_there_returns_none(self):
        """Returning a different value instead would be worse than returning nothing."""
        db = ComponentDatabase()
        assert db.find_template("capacitor", value="47uF") is None
        assert db.find_template("resistor", value="4k7") is None

    def test_an_unknown_category_returns_none(self):
        db = ComponentDatabase()
        assert db.find_template("nonexistent_category") is None

    def test_the_data_source_says_templates_not_catalog(self):
        db = ComponentDatabase(prefer_jlcparts=False)
        assert "template" in db.data_source
        assert "no part numbers" in db.data_source
