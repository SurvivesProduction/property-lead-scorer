from __future__ import annotations

import pytest

from extscorer.normalize.permits import is_exterior_permit


@pytest.mark.parametrize(
    "description",
    [
        "strip exsting siding, install house wrap and double 4 vinyl siding",
        "Re-siding of home with vinyl",
        "re-side garage",
        "Replace siding",
        "repair side wall damaged by tree",
        "Full Roof Replacement",
        "STRIP/ RESHINGLE APPROX 1800 SF",
        "replace 6 windows",
        "new gutters",
    ],
)
def test_exterior_work_is_flagged(description: str) -> None:
    assert is_exterior_permit("Building", description) is True


@pytest.mark.parametrize(
    "description",
    [
        "Change of zoning to non conforming residential use",
        "install hvac units for the residence",
        "owner will reside in the unit",
        "Interior fit-out of existing attic space",
        "outside condenser pad",
        "poolside bathroom",
        "work alongside existing structure",
        "currently residing on the second floor",
    ],
)
def test_words_that_merely_contain_side_or_siding_are_not_flagged(description: str) -> None:
    assert is_exterior_permit("Building", description) is False


def test_type_text_is_checked_too() -> None:
    assert is_exterior_permit("Siding", None) is True
    assert is_exterior_permit(None, None) is False


@pytest.mark.parametrize(
    "description",
    ["vinyl sided house, repair", "replace damaged sidewall", "new sidewalls on addition", "SIDEWALL SHINGLES"],
)
def test_sided_and_sidewall_are_whole_words_that_hit(description: str) -> None:
    assert is_exterior_permit("Building", description) is True


@pytest.mark.parametrize("status", ["Canceled", "Cancelled", "DENIED", "Void", "withdrawn", " Withdrawn "])
def test_never_built_statuses_are_not_exterior(status: str) -> None:
    assert is_exterior_permit("Building", "full roof replacement", status) is False


@pytest.mark.parametrize("status", [None, "", "Approved", "Closed", "Under Review"])
def test_other_statuses_do_not_change_the_result(status: str | None) -> None:
    assert is_exterior_permit("Building", "full roof replacement", status) is True


def test_sidewalk_still_does_not_hit() -> None:
    assert is_exterior_permit("Zoning", "Sidewalk Extension for Elementary School") is False


@pytest.mark.parametrize(
    "description",
    [
        "14 kW standby generator to the right side of home",
        "install propane tank by chimney on side of home",
        "12x32 metal lean-to installed on left side of garage",
        "9x17 deck off the side of the front door",
        "driveway side of trailer, replace heat pump",
    ],
)
def test_the_bare_word_side_is_a_location_not_siding_work(description: str) -> None:
    assert is_exterior_permit("Building", description) is False


@pytest.mark.parametrize(
    "description",
    ["repair damaged side wall", "new side wall shingles", "re-side the garage", "Re-siding of home", "replace sidewalls"],
)
def test_side_wall_and_hyphenated_re_side_still_hit(description: str) -> None:
    assert is_exterior_permit("Building", description) is True


@pytest.mark.parametrize("description", ["the owner will reside here", "tenants re side in unit 2", "residential unit"])
def test_reside_and_unhyphenated_re_side_do_not_hit(description: str) -> None:
    assert is_exterior_permit("Building", description) is False

# --- permit-history helpers ---

from datetime import date  # noqa: E402

from extscorer.normalize.permits import merge_permit_histories, parse_permit_date, summarize_permit_history  # noqa: E402


def test_parse_permit_date_treats_blank_bad_and_1900_as_none() -> None:
    assert parse_permit_date("09/16/2026") == date(2026, 9, 16)
    for bad in (None, "", "garbage", "01/01/1900"):
        assert parse_permit_date(bad) is None


def test_summarize_permit_history_counts_dated_exterior_work_only() -> None:
    history = [
        {"permit_number": "1", "permit_type": "Building", "date_opened": "05/01/2019", "reason": "Full roof replacement"},
        {"permit_number": "2", "permit_type": "Building", "date_opened": "06/01/2023", "reason": "New siding", "status": "Approved"},
        {"permit_number": "3", "permit_type": "Building", "date_opened": "07/01/2025", "reason": "Reroof", "status": "Canceled"},
        {"permit_number": "Draft", "permit_type": "Building", "date_opened": "", "reason": "roof"},
        {"permit_number": "4", "permit_type": "Residential", "date_opened": "08/01/2024", "reason": "Finish second floor"},
    ]
    summary = summarize_permit_history(history)
    assert summary["exterior_permit_count"] == 2
    assert summary["most_recent_exterior_permit_date"] == date(2023, 6, 1)
    assert summary["most_recent_exterior_permit_type"] == "Building"
    assert summarize_permit_history([]) == {
        "exterior_permit_count": 0,
        "most_recent_exterior_permit_date": None,
        "most_recent_exterior_permit_type": None,
    }


def test_merge_dedupes_on_permit_number_and_date_and_fills_missing_fields() -> None:
    card = [{"permit_number": "B-2019-114", "permit_type": "Miscellaneous", "date_opened": "05/01/2019", "reason": "reshingle"}]
    link = [
        {"permit_number": "b2019114", "permit_type": "Building", "date_opened": "05/01/2019", "reason": "Reshingle", "status": "Closed"},
        {"permit_number": "B-2019-114", "permit_type": "Building", "date_opened": "09/09/2021", "reason": "amend", "status": "Closed"},
    ]
    merged = merge_permit_histories(card, link)
    assert len(merged) == 2  # same number + same date collapses; same number on a new date is a different permit
    assert merged[0]["permit_type"] == "Miscellaneous"  # first source wins...
    assert merged[0]["status"] == "Closed"  # ...but gains the status it lacked


def test_merge_keeps_numberless_permits_apart_unless_they_say_the_same_thing() -> None:
    a = {"permit_number": None, "permit_type": "Roof", "date_opened": "01/02/2020", "reason": "tear off"}
    assert len(merge_permit_histories([a], [dict(a)])) == 1
    assert len(merge_permit_histories([a], [dict(a, reason="gutters")])) == 2
