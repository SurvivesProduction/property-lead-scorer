"""2026-11-11 scorer changes: the log family as unsidable, cancel/deny as not-built."""
from __future__ import annotations

import pytest

from extscorer.digest.copy import _describe_siding
from extscorer.normalize.permits import NOT_BUILT_PERMIT_STATUSES, classify_exterior_permit, is_exterior_permit
from extscorer.normalize.walls import is_log_exterior, is_log_text, is_masonry_text
from extscorer.scoring.basic import masonry_roof_only, score_property, siding_age_score, siding_score


def _p(wall, year=1960, **kw):
    return {"exterior_wall_1": wall, "year_built": year, **kw}


# --- log family --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("wall", ["Log Cabin", "Logs", "Log", "LOG CABIN", "Log Cabin/Stone Veneer"])
def test_log_walls_are_unsidable(wall) -> None:
    assert is_log_text(wall) and is_log_exterior({"exterior_wall_1": wall})


@pytest.mark.parametrize("wall", ["Log Siding", "Vinyl Siding", "Wood Frame", "Clapboards", "Brick", "Catalog", "Log Cabin/Vinyl Siding", None, ""])
def test_other_walls_are_not_log(wall) -> None:
    assert not is_log_text(wall)


def test_a_second_sidable_wall_keeps_the_normal_score() -> None:
    assert not is_log_exterior({"exterior_wall_1": "Log Cabin", "exterior_wall_2": "Vinyl Siding"})
    assert is_log_exterior({"exterior_wall_1": "Log Cabin", "exterior_wall_2": "Stone Veneer"})


def test_log_houses_score_zero_on_siding_and_are_roof_only_when_the_switch_is_on() -> None:
    parcel = _p("Log Cabin", 1900, permit_data_available=False)
    assert masonry_roof_only(parcel)
    assert siding_score(parcel, masonry_siding_zero=True) == 0.0
    assert siding_score(parcel, masonry_siding_zero=False) == siding_age_score(parcel) > 0.5
    base = {"parcel_id": "1", "town": "T", "address": "1 A ST", "living_area_sqft": 1500, **parcel}
    assert score_property(base, as_of_year=2026, masonry_siding_zero=True).roof_only_candidate
    assert not score_property(dict(base, exterior_wall_1="Log Siding"), as_of_year=2026, masonry_siding_zero=True).roof_only_candidate


def test_a_real_siding_permit_on_a_log_house_wins_like_it_does_for_masonry() -> None:
    permit = {"permit_number": "1", "date_opened": "06/01/2020", "reason": "install siding", "status": "complete"}
    parcel = _p("Logs", 1900, permit_data_available=True, permit_history=[permit])
    assert not masonry_roof_only(parcel)


def test_the_digest_says_logs_cannot_be_re_sided() -> None:
    text = _describe_siding(_p("Log Cabin", 1900), 2026, masonry_siding_zero=True)
    assert text == "Log Cabin exterior: logs can't be re-sided, so this one is a roof job only"
    assert "masonry can't be re-sided" in _describe_siding(_p("Brick", 1900), 2026, masonry_siding_zero=True)
    assert _describe_siding(_p("Log Cabin", 1900), 2026, masonry_siding_zero=False) != text


def test_masonry_text_is_unchanged() -> None:
    assert is_masonry_text("Brick") and not is_masonry_text("Wood Frame/Masonry")


# --- cancel / deny -----------------------------------------------------------------------------------------------


def test_cancel_and_deny_are_not_built() -> None:
    assert {"cancel", "deny"} <= NOT_BUILT_PERMIT_STATUSES
    for status in ("cancel", "Cancel", " deny ", "DENY"):
        assert not is_exterior_permit(None, "replace siding", status)
        assert not classify_exterior_permit(None, "replace siding", status)


def test_statuses_are_whole_words_not_substrings() -> None:
    for status in ("candidate", "denying", "cancellation", "complete", "hold", "expired", "other", None):
        assert is_exterior_permit(None, "replace siding", status)
        assert classify_exterior_permit(None, "replace siding", status)


def test_wood_frame_scores_exactly_as_before() -> None:
    import math

    assert siding_age_score(_p("Wood Frame", 1900)) == pytest.approx(0.85 + 0.15 * (1 - math.exp(-90 / 25)))
