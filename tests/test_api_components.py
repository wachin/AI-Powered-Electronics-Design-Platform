"""
Tests for the component API endpoints.

The API is the contract the web frontend is written against, so the shape of
the search response is pinned here: results are returned *with* the
interpretation that produced them, because the frontend shows it.
"""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient


# A miniature catalog with the same schema as the real download.
SCHEMA = """
CREATE TABLE jlc_components (
    lcsc INTEGER PRIMARY KEY,
    fetched_at INTEGER DEFAULT 0,
    present INTEGER DEFAULT 1,
    sync_seen INTEGER DEFAULT 0,
    category TEXT DEFAULT '',
    subcategory TEXT DEFAULT '',
    mfr TEXT DEFAULT '',
    package TEXT DEFAULT '',
    joints INTEGER DEFAULT 0,
    manufacturer TEXT DEFAULT '',
    library_type TEXT DEFAULT 'expand',
    preferred INTEGER DEFAULT 0,
    last_on_stock INTEGER DEFAULT 0,
    description TEXT DEFAULT '',
    datasheet TEXT DEFAULT '',
    stock INTEGER DEFAULT 0,
    price TEXT DEFAULT '',
    attributes TEXT DEFAULT '{}',
    rohs INTEGER DEFAULT 1,
    eccn TEXT DEFAULT '',
    assembly INTEGER DEFAULT 1,
    assembly_process TEXT DEFAULT '',
    assembly_mode TEXT DEFAULT '',
    website_component_id TEXT DEFAULT '',
    attrition TEXT DEFAULT '',
    basic INTEGER DEFAULT 0
)
"""

ROWS = [
    (1001, "Resistors", "RC0603FR-0710KL", "0603", "10kΩ 1%",
     '{"Resistance":"10kΩ","Tolerance":"±1%","Power(Watts)":"100mW"}',
     500000, 0, "1-49:0.01,5000-:0.002"),
    (1002, "Resistors", "GENERIC10K5", "0603", "10kΩ 5%",
     '{"Resistance":"10kΩ","Tolerance":"±5%","Power(Watts)":"100mW"}',
     2000, 1, "1-49:0.02"),
    (1003, "Resistors", "R0805-110K", "0805", "110kΩ 1%",
     '{"Resistance":"110kΩ","Tolerance":"±1%"}', 50000, 0, "1-49:0.03"),
    (2001, "Capacitors", "C0805-100N", "0805", "100nF 50V",
     '{"Capacitance":"100nF","Voltage Rating":"50V"}', 8000, 1, "1-49:0.03"),
    (5001, "Embedded Processors & Controllers", "ESP32-WROOM-32E", "SMD",
     "ESP32 WiFi module", "{}", 5000, 0, "1-49:2.50"),
]


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    """A TestClient whose component database is the miniature catalog."""
    catalog = tmp_path / "catalog.sqlite3"
    conn = sqlite3.connect(catalog)
    conn.execute(SCHEMA)
    for lcsc, category, mfr, package, description, attributes, stock, preferred, price in ROWS:
        conn.execute(
            "INSERT INTO jlc_components "
            "(lcsc, category, mfr, package, description, attributes, stock, "
            " preferred, price) VALUES (?,?,?,?,?,?,?,?,?)",
            (lcsc, category, mfr, package, description, attributes, stock,
             preferred, price),
        )
    conn.commit()
    conn.close()

    monkeypatch.setenv("JLC_PARTS_CATALOG", str(catalog))

    from src.components.database import ComponentDatabase
    from src.api import main as api_main

    monkeypatch.setattr(api_main, "db", ComponentDatabase(catalog))
    with TestClient(api_main.app) as test_client:
        yield test_client


class TestSearchEndpoint:
    def test_returns_components_with_the_interpretation(self, client):
        response = client.post("/api/components/search", json={"query": "10k 0603"})
        assert response.status_code == 200
        body = response.json()
        assert "components" in body
        assert "interpretation" in body
        assert "notes" in body
        assert body["source"].startswith("JLCPCB/LCSC offline catalog")

    def test_interprets_a_parametric_query(self, client):
        body = client.post(
            "/api/components/search", json={"query": "10k 0603"}
        ).json()
        assert "10k" in body["interpretation"]
        assert "0603" in body["interpretation"]
        assert body["components"]

    def test_does_not_return_the_wrong_value(self, client):
        """The regression this whole subsystem exists to prevent."""
        body = client.post(
            "/api/components/search", json={"query": "10k"}
        ).json()
        mpns = [c["mpn"] for c in body["components"]]
        assert "R0805-110K" not in mpns

    def test_parsed_attributes_are_returned(self, client):
        body = client.post(
            "/api/components/search", json={"query": "10k 1%"}
        ).json()
        attributes = body["components"][0]["attributes"]
        assert attributes["resistance"] == pytest.approx(10000.0)
        assert attributes["tolerance"] == pytest.approx(0.01)

    def test_value_is_the_readable_specification(self, client):
        body = client.post(
            "/api/components/search", json={"query": "10k 1%"}
        ).json()
        assert "10kΩ" in body["components"][0]["value"]

    def test_named_part_uses_the_text_path(self, client):
        body = client.post(
            "/api/components/search", json={"query": "ESP32-WROOM-32E"}
        ).json()
        assert [c["mpn"] for c in body["components"]] == ["ESP32-WROOM-32E"]

    def test_empty_query_returns_an_empty_list(self, client):
        body = client.post("/api/components/search", json={"query": ""}).json()
        assert body["components"] == []


class TestCategoryEndpoint:
    def test_returns_internal_category_names(self, client):
        body = client.get("/api/components/categories").json()
        assert "resistor" in body["categories"]
        assert "capacitor" in body["categories"]

    def test_also_returns_the_catalogs_own_names(self, client):
        body = client.get("/api/components/categories").json()
        assert body["catalog_categories"]["Resistors"] == 3


class TestSubstituteEndpoint:
    def test_returns_candidates_with_reasons(self, client):
        response = client.get("/api/components/C1001/substitutes")
        assert response.status_code == 200
        body = response.json()
        assert body["substitutes"]
        candidate = body["substitutes"][0]
        assert candidate["reasons"]
        assert "caveats" in candidate
        assert "verified" in candidate

    def test_discloses_a_looser_tolerance(self, client):
        body = client.get("/api/components/C1001/substitutes").json()
        looser = [s for s in body["substitutes"] if s["mpn"] == "GENERIC10K5"]
        assert looser
        assert looser[0]["caveats"]
        assert looser[0]["verified"] is False

    def test_a_part_without_a_value_explains_itself(self, client):
        body = client.get("/api/components/C5001/substitutes").json()
        assert body["substitutes"] == []
        assert body["notes"]

    def test_lookup_by_lcsc_number(self, client):
        response = client.get("/api/components/C1001")
        assert response.status_code == 200
        assert response.json()["mpn"] == "RC0603FR-0710KL"


class TestRootAdvertising:
    def test_lists_the_substitute_endpoint(self, client):
        body = client.get("/").json()
        assert "substitutes" in body["endpoints"]
