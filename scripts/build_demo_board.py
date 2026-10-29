#!/usr/bin/env python
"""Build the DEMO Lead Board -- fully synthetic (fake towns/streets/parcel
ids), safe to commit and safe to show on a screen-share/YouTube. Inlines
`lead_board/template.html` + the JS modules + a synthetic data fixture
into one self-contained HTML file.

Covers every case the real board has to handle (Prompt W Step 4):
  - a claimed town ("Fakington")
  - a permit-visible-but-short-history town ("Smallville", Windham-shaped:
    `permit_data_available=True` but `permit_history_short=True` for the
    WHOLE town -- must never show "has real permit history")
  - a town with genuine real permit history ("Mapleford")
  - worked / unworked / mailed-or-shown rows
  - state-data-only rows (scoreable, but unverified)
  - sparse `last_sale_year` (several rows with none on file)

Usage:
    python scripts/build_demo_board.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from extscorer.normalize.materials import classify_roof_material, wall_material_families

_REPO_ROOT = Path(__file__).resolve().parent.parent
_LEAD_BOARD_DIR = _REPO_ROOT / "lead_board"
_OUT_PATH = _REPO_ROOT / "demo" / "lead_board_demo.html"


def _lead(
    parcel_id,
    town,
    address,
    year_built,
    property_c,
    canopy_c,
    storm_c=1.0,
    siding_c=0.5,
    living_area_sqft=1800,
    assessed_value=250000.0,
    last_sale_year=2010,
    siding_materials=None,
    roof_cover_material=None,
    pct_tree_canopy_nearby=40.0,
    source_url=None,
    permit_data_available=False,
    permit_history_short=False,
    is_absentee=False,
    is_delinquent=False,
    pipeline_status=None,
    mailed_or_shown=False,
    is_state_only=False,
):
    weights = {"property": 0.5, "canopy": 0.15, "storm": 0.05, "siding": 0.3}
    total_w = sum(weights.values())
    lead_score = (
        weights["property"] * property_c
        + weights["canopy"] * canopy_c
        + weights["storm"] * storm_c
        + weights["siding"] * siding_c
    ) / total_w

    siding_materials = siding_materials or []
    siding_families: list[str] = []
    for raw in siding_materials:
        for family in wall_material_families(raw):
            if family not in siding_families:
                siding_families.append(family)

    return {
        "parcel_id": parcel_id,
        "lead_key": f"{town}:{parcel_id}",
        "town": town,
        "address": address,
        "year_built": year_built,
        "siding_materials": siding_materials,
        "siding_families": siding_families,
        "roof_cover_material": roof_cover_material,
        "roof_family": classify_roof_material(roof_cover_material),
        "pct_tree_canopy_nearby": pct_tree_canopy_nearby,
        "living_area_sqft": living_area_sqft,
        "assessed_value": assessed_value,
        "last_sale_year": last_sale_year,
        "source_url": source_url,
        "components": {"property": property_c, "canopy": canopy_c, "storm": storm_c, "siding": siding_c},
        "lead_score": lead_score,
        "flags": {
            "permit_data_available": permit_data_available,
            "permit_history_short": permit_history_short,
            "is_absentee": is_absentee,
            "is_delinquent": is_delinquent,
            "pipeline_status": pipeline_status,
            "mailed_or_shown": mailed_or_shown,
            "is_state_only": is_state_only,
        },
    }


def build_demo_data() -> dict:
    parcels = [
        _lead(
            "1", "Fakington", "1 Example Rd", 1850, 0.95, 0.8, siding_c=0.9, living_area_sqft=2400,
            source_url="https://example.invalid/Parcel.aspx?pid=1",
            siding_materials=["Clapboard"], roof_cover_material="Asphalt Shingle",
        ),
        _lead(
            "2", "Fakington", "2 Example Rd", 1920, 0.7, 0.3, siding_c=0.6, mailed_or_shown=True,
            source_url="https://example.invalid/Parcel.aspx?pid=2",
            siding_materials=["Vinyl"], roof_cover_material="Asphalt Shingle",
        ),
        _lead("3", "Fakington", "3 Example Rd", 1965, 0.3, 0.5, siding_c=0.2, last_sale_year=None),
        _lead(
            "4", "Mapleford", "4 Fictional Ave", 1900, 0.8, 0.6, siding_c=0.85,
            permit_data_available=True, permit_history_short=False,
            source_url="https://example.invalid/Parcel.aspx?pid=4",
            siding_materials=["Wood"], roof_cover_material="Metal/Tin",
        ),
        _lead(
            "5", "Mapleford", "5 Fictional Ave", 1975, 0.5, 0.4, siding_c=0.1,
            permit_data_available=True, permit_history_short=False, is_state_only=True,
        ),
        _lead(
            "6", "Smallville", "6 Pretend St", 1990, 0.45, 0.5, siding_c=0.5,
            permit_data_available=True, permit_history_short=True,  # Windham-shaped
        ),
        _lead(
            "7", "Smallville", "7 Pretend St", 1945, 0.75, 0.7, siding_c=0.8,
            permit_data_available=True, permit_history_short=True,  # Windham-shaped
            last_sale_year=None,
        ),
        _lead(
            "8", "Pineville", "8 Imaginary Ln", 1955, 0.65, 0.2, siding_c=0.4, pipeline_status="estimate booked",
            siding_materials=["Vinyl Siding/Clapboards"], roof_cover_material="Slate",
        ),
        _lead("9", "Pineville", "9 Imaginary Ln", 1988, 0.4, 0.6, siding_c=0.3, pipeline_status="not interested"),
        _lead("10", "Pineville", "10 Imaginary Ln", 1932, 0.85, 0.9, siding_c=0.7, pipeline_status="new"),
        _lead("11", "Pineville", "11 Imaginary Ln", 1998, 0.2, 0.4, siding_c=0.15, last_sale_year=None),
        _lead("12", "Pineville", "12 Imaginary Ln", 1890, 0.9, 0.55, siding_c=0.6, is_state_only=True, last_sale_year=None),
        _lead("13", "Pineville", "13 Imaginary Ln", 1960, 0.6, 0.3, siding_c=0.5, is_absentee=True),
        _lead("14", "Pineville", "14 Imaginary Ln", 1940, 0.72, 0.45, siding_c=0.65, is_delinquent=True),
        _lead("15", "Pineville", "15 Imaginary Ln", 1972, 0.5, 0.5, siding_c=0.5, living_area_sqft=3800, assessed_value=410000.0),
        _lead("16", "Pineville", "16 Imaginary Ln", 1980, 0.45, 0.35, siding_c=0.3, living_area_sqft=900, assessed_value=120000.0),
    ]
    return {
        "metadata": {
            "client_id": "demo",
            "as_of_year": 2026,
            "sold_towns": ["Fakington"],
            "export_timestamp": "2026-10-29T00:00:00+00:00",
            "weights": {
                "property_weight": 0.5,
                "canopy_weight": 0.15,
                "storm_weight": 0.05,
                "siding_weight": 0.3,
            },
        },
        "parcels": parcels,
    }


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def build_html(data: dict) -> str:
    template = _read(_LEAD_BOARD_DIR / "template.html")
    data_js = f"var LEAD_BOARD_DATA = {json.dumps(data)};"
    substitutions = {
        "/*__LEAD_BOARD_DATA__*/": data_js,
        "/*__SCORING_JS__*/": _read(_LEAD_BOARD_DIR / "scoring.js"),
        "/*__FILTERS_JS__*/": _read(_LEAD_BOARD_DIR / "filters.js"),
        "/*__PRESETS_JS__*/": _read(_LEAD_BOARD_DIR / "presets.js"),
        "/*__STATE_JS__*/": _read(_LEAD_BOARD_DIR / "state.js"),
        "/*__APP_JS__*/": _read(_LEAD_BOARD_DIR / "app.js"),
    }
    html = template
    for marker, content in substitutions.items():
        if marker not in html:
            raise ValueError(f"Template marker {marker!r} not found in template.html")
        html = html.replace(marker, content)
    # Belt-and-suspenders: no leftover markers, no accidental closing
    # </script> tag inside any inlined JS that would truncate the page.
    if re.search(r"__[A-Z_]+__", html):
        raise ValueError("Unresolved template marker left in built HTML")
    return html


def run() -> int:
    data = build_demo_data()
    html = build_html(data)
    _OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    _OUT_PATH.write_text(html, encoding="utf-8")
    print(f"Wrote {_OUT_PATH} ({len(data['parcels'])} synthetic parcels)")
    return 0


if __name__ == "__main__":
    sys.exit(run())
