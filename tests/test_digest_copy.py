"""Tests for the plain-language digest copy -- confirm the rendered text
reads the way Prompt O Step 2 decided (no raw scores, no internal field
names, real branching on canopy extremes), not just that it doesn't crash.
"""
from __future__ import annotations

from datetime import date

from extscorer.digest.copy import describe_lead, render_digest_html, render_digest_text

_AS_OF_YEAR = 2026


def test_describe_lead_mentions_age_in_plain_language() -> None:
    text = describe_lead({"year_built": 1900}, _AS_OF_YEAR)
    assert "1900" in text
    assert "126 years old" in text


def test_describe_lead_calls_out_heavy_canopy() -> None:
    text = describe_lead({"pct_tree_canopy_nearby": 96.0}, _AS_OF_YEAR)
    assert "Heavy tree cover" in text
    assert "96%" in text


def test_describe_lead_calls_out_low_canopy() -> None:
    text = describe_lead({"pct_tree_canopy_nearby": 2.0}, _AS_OF_YEAR)
    assert "Little tree cover" in text
    assert "exposed" in text


def test_describe_lead_mentions_storm_date_in_plain_language() -> None:
    text = describe_lead({"nearest_storm_event_date": date(2026, 5, 19)}, _AS_OF_YEAR)
    # Regression test: str.capitalize() would have lowercased "May" -> "may".
    assert "May 19, 2026" in text


def test_describe_lead_never_leaks_internal_field_or_score_names() -> None:
    text = describe_lead(
        {
            "year_built": 1900,
            "pct_tree_canopy_nearby": 96.0,
            "nearest_storm_event_date": date(2026, 5, 19),
            "lead_score": 0.981,
            "score_property_component": 0.971,
            "score_siding_component": 0.9,
        },
        _AS_OF_YEAR,
    )
    for forbidden in ("lead_score", "component", "0.981", "0.971", "0.9", "canopy_score", "pct_tree_canopy_nearby", "siding_component"):
        assert forbidden not in text


def test_describe_lead_mentions_siding_material_for_proxy_towns() -> None:
    # No permit_data_available -- the 5 proxy towns (Canterbury, Pomfret,
    # Thompson, Hampton, Brooklyn). Names the material, doesn't claim
    # permit visibility that doesn't exist for these towns.
    text = describe_lead({"exterior_wall_1": "Clapboards"}, _AS_OF_YEAR)
    assert "clapboards" in text
    assert "original to the house" in text
    assert "permit" not in text.lower()


def test_describe_lead_mentions_no_permit_on_file_for_real_towns() -> None:
    # permit_data_available true (Killingly/Ashford/Woodstock), no
    # exterior-relevant permit found -- real confirmation, not a guess.
    text = describe_lead(
        {"exterior_wall_1": "Vinyl Siding", "permit_data_available": True},
        _AS_OF_YEAR,
    )
    assert "vinyl siding" in text
    assert "no exterior work ever done" in text
    assert "permit records" in text


def test_describe_lead_mentions_when_a_real_permit_was_last_worked_on() -> None:
    text = describe_lead(
        {
            "exterior_wall_1": "Clapboards",
            "permit_data_available": True,
            "most_recent_exterior_permit_date": date(2005, 6, 1),
        },
        _AS_OF_YEAR,
    )
    assert "clapboards" in text
    assert "2005" in text
    assert "21 years ago" in text


def test_describe_lead_omits_siding_clause_when_material_unknown() -> None:
    text = describe_lead({"year_built": 1900}, _AS_OF_YEAR)
    assert "siding" not in text.lower()


def test_describe_lead_siding_clause_comes_right_after_property_age() -> None:
    # Clause order mirrors the signals' own weight order (property, then
    # siding, then canopy, then storm) -- the most important reason reads
    # first.
    text = describe_lead(
        {
            "year_built": 1900,
            "exterior_wall_1": "Clapboards",
            "pct_tree_canopy_nearby": 96.0,
            "nearest_storm_event_date": date(2026, 5, 19),
        },
        _AS_OF_YEAR,
    )
    age_idx = text.index("1900")
    siding_idx = text.index("clapboards")
    canopy_idx = text.lower().index("tree cover")
    storm_idx = text.index("May 19")
    assert age_idx < siding_idx < canopy_idx < storm_idx


def test_describe_lead_handles_missing_signals_gracefully() -> None:
    text = describe_lead({}, _AS_OF_YEAR)
    assert text  # never empty, never crashes


def test_render_digest_text_lists_every_lead_with_address_and_town() -> None:
    leads = [
        (object(), {"address": "1 Old House Rd", "town": "Canterbury", "year_built": 1900}),
        (object(), {"address": "2 New House Rd", "town": "Pomfret", "year_built": 2004}),
    ]
    text = render_digest_text(leads, _AS_OF_YEAR)
    assert "1 Old House Rd, Canterbury" in text
    assert "2 New House Rd, Pomfret" in text
    assert "2 Exterior Renovation Lead" in text


def test_render_digest_html_contains_every_lead_and_no_raw_score_fields() -> None:
    leads = [
        (object(), {"address": "1 Old House Rd", "town": "Canterbury", "year_built": 1900, "pct_tree_canopy_nearby": 96.0}),
    ]
    html = render_digest_html(leads, _AS_OF_YEAR)
    assert "1 Old House Rd" in html
    assert "Canterbury" in html
    assert "lead_score" not in html
    assert "component" not in html


def test_render_digest_html_escapes_address_content() -> None:
    leads = [(object(), {"address": "1 <script>alert(1)</script> Rd", "town": "Canterbury"})]
    html = render_digest_html(leads, _AS_OF_YEAR)
    assert "<script>" not in html
