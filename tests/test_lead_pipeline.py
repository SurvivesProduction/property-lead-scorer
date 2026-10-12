"""Key stability for `extscorer.lead_pipeline.lead_key` (Prompt V)."""
from __future__ import annotations

from extscorer.lead_pipeline import lead_key


def test_lead_key_is_deterministic() -> None:
    assert lead_key("Canterbury", "1329") == lead_key("Canterbury", "1329")


def test_lead_key_format_is_town_colon_parcel_id() -> None:
    assert lead_key("Canterbury", "1329") == "Canterbury:1329"


def test_lead_key_distinguishes_same_parcel_id_in_different_towns() -> None:
    assert lead_key("Canterbury", "1") != lead_key("Pomfret", "1")


def test_lead_key_distinguishes_different_parcel_ids_in_same_town() -> None:
    assert lead_key("Canterbury", "1") != lead_key("Canterbury", "2")
