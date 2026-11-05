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
