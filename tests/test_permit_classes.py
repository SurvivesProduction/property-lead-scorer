from __future__ import annotations

from datetime import date

import pytest

from extscorer.normalize.permits import (
    OTHER_EXTERIOR,
    ROOF,
    SIDING,
    classify_exterior_permit,
    dated_permits_by_class,
)
from extscorer.scoring.basic import (
    rank_candidates,
    siding_age_score,
    real_siding_age_score,
    score_property,
    willingness_to_spend_score,
)

_AS_OF = 2026


@pytest.mark.parametrize(
    "text,expected",
    [
        ("strip existing siding, install house wrap and vinyl siding", {SIDING}),
        ("replace damaged sidewall", {SIDING}),
        ("new side wall shingles", {SIDING}),  # names the walls and has no roof signal: siding only
        ("re-side the garage", {SIDING}),
        ("replace clapboards on front", {SIDING}),
        ("full roof replacement", {ROOF}),
        ("re-roof and reshingle garage", {ROOF}),
        ("tear off roofing, new shingles", {ROOF}),
        ("replace 6 windows", {OTHER_EXTERIOR}),
        ("build 12x14 deck and covered porch", {OTHER_EXTERIOR}),
        ("new entry door and storm doors", {OTHER_EXTERIOR}),
        ("re-roof and new vinyl siding", {SIDING, ROOF}),
        ("replace roof and windows", {ROOF, OTHER_EXTERIOR}),
        # wall shingles are siding when the text names the walls and nothing marks it as a roof job
        ("reshingle front and side of house", {SIDING}),
        ("replace wood shingles on walls", {SIDING}),
        ("new cedar shakes on exterior walls", {SIDING}),
        ("re-shingle the back of the home", {SIDING}),
        # ...and stay ROOF when they do not, or when a roof signal is present
        ("reshingle 17 sq", {ROOF}),
        ("strip shingles off house, 24 squares", {ROOF}),
        ("reshingle roof and wall shingles", {ROOF}),
        ("new asphalt shingles", {ROOF}),
        ("strip existing shingles off of house and garage", {ROOF}),
        # the bare word \"exterior\" is an upgrade only when the permit is not a siding or roof job
        ("replace exterior siding", {SIDING}),
        ("Exterior: full roof replacement", {ROOF}),
        ("exterior painting and trim", {OTHER_EXTERIOR}),
        # roof decking is sheathing, not a deck
        ("strip shingles, replace roof deck", {ROOF}),
        ("replace roof decking", {ROOF}),
        # interior-room wording needs an explicit outside word before a door or deck counts
        ("bathroom remodel incl. new shower door", set()),
        ("finish basement: interior and closet doors", set()),
        ("interior remodel: new kitchen, doors and trim", set()),
        ("kitchen remodel and new cabinet doors", set()),
        ("kitchen remodel plus new back door", {OTHER_EXTERIOR}),
        ("bedroom addition with new entry door", {OTHER_EXTERIOR}),
        ("bathroom remodel, replace storm door", {OTHER_EXTERIOR}),
        ("basement finish and garage door replacement", {OTHER_EXTERIOR}),
        ("kitchen remodel and new porch", {OTHER_EXTERIOR}),
        # real outside work in a permit that also remodels an interior room is kept
        ("remodel kitchen and add 12x16 deck", {OTHER_EXTERIOR}),
        ("addition with bed and bath, 8x12 deck", {OTHER_EXTERIOR}),
        ("open up kitchen wall and rebuild rear deck", {OTHER_EXTERIOR}),
        ("finish basement rooms, new walkout with slider door", {OTHER_EXTERIOR}),
        ("basement bath, install patio door", {OTHER_EXTERIOR}),
        # ...while interior work that merely mentions a deck or door is not
        ("gas line routed beneath the deck and into the basement utility room", set()),
        ("interior reno, move door between rooms", set()),
        ("bathroom remodel and replace window", {OTHER_EXTERIOR}),  # a window is in the shell wherever the room is
        ("waterproofing the basement", set()),
        ("install fire door and interior doors", set()),
        ("replace fire-rated door", set()),
        ("new int. door to basement", set()),
        ("replace exterior door and storm door", {OTHER_EXTERIOR}),
        ("new garage door", {OTHER_EXTERIOR}),  # "roof" inside "waterproofing" is not a roof
        ("fireproof door seal", {OTHER_EXTERIOR}),
        ("install heat pump", set()),
        ("generator on the right side of the home", set()),
    ],
)
def test_permits_are_classified_into_siding_roof_and_other_exterior(text: str, expected: set[str]) -> None:
    assert classify_exterior_permit("Building", text) == frozenset(expected)


def test_the_permit_type_text_counts_too() -> None:
    assert classify_exterior_permit("Roof", None) == frozenset({ROOF})


@pytest.mark.parametrize("status", ["Canceled", "Denied", "Void", "Withdrawn"])
def test_never_built_permits_are_in_no_class(status: str) -> None:
    assert classify_exterior_permit("Building", "full roof replacement and siding", status) == frozenset()


def test_dated_permits_are_grouped_by_class_newest_first_and_drafts_are_skipped() -> None:
    history = [
        {"permit_type": "Building", "reason": "new siding", "date_opened": "03/01/2012"},
        {"permit_type": "Building", "reason": "re-roof and siding", "date_opened": "05/01/2020"},
        {"permit_type": "Building", "reason": "replace windows", "date_opened": "01/01/2018"},
        {"permit_type": "Building", "reason": "roof", "date_opened": ""},  # draft, no date
        {"permit_type": "Building", "reason": "roof", "date_opened": "01/01/1900"},  # placeholder date
    ]
    by_class = dated_permits_by_class(history)
    assert by_class[SIDING] == [date(2020, 5, 1), date(2012, 3, 1)]
    assert by_class[ROOF] == [date(2020, 5, 1)]
    assert by_class[OTHER_EXTERIOR] == [date(2018, 1, 1)]
    assert dated_permits_by_class(None) == {SIDING: [], ROOF: [], OTHER_EXTERIOR: []}


def _old_wood_house(history: list[dict], legacy_date: date | None, **extra) -> dict:
    return {
        "permit_data_available": True, "exterior_wall_1": "Clapboards", "year_built": 1900,
        "permit_history": history, "most_recent_exterior_permit_date": legacy_date, **extra,
    }


_ROOF_2024 = {"permit_type": "Building", "reason": "full roof replacement", "date_opened": "06/01/2024"}
_SIDING_2024 = {"permit_type": "Building", "reason": "new vinyl siding", "date_opened": "06/01/2024"}


def test_a_roof_permit_resets_the_siding_age_in_the_legacy_score_but_not_in_the_split() -> None:
    parcel = _old_wood_house([_ROOF_2024], date(2024, 6, 1))
    legacy = real_siding_age_score(parcel, as_of_year=_AS_OF)
    split = real_siding_age_score(parcel, as_of_year=_AS_OF, permit_class_split=True)
    assert legacy < 0.2  # "recently redone"
    assert split > 0.9  # a roof says nothing about the siding
    # no siding permit: the material-based proxy, the same answer a town with no permit data gets
    assert split == siding_age_score(parcel)


def test_a_siding_permit_resets_the_siding_age_in_both_modes() -> None:
    parcel = _old_wood_house([_SIDING_2024], date(2024, 6, 1))
    assert real_siding_age_score(parcel, as_of_year=_AS_OF, permit_class_split=True) == pytest.approx(
        real_siding_age_score(parcel, as_of_year=_AS_OF)
    )
    assert real_siding_age_score(parcel, as_of_year=_AS_OF, permit_class_split=True) < 0.2


def test_the_split_uses_the_newest_siding_permit_even_when_a_newer_roof_permit_exists() -> None:
    older_siding = {"permit_type": "Building", "reason": "vinyl siding", "date_opened": "01/01/2000"}
    parcel = _old_wood_house([older_siding, _ROOF_2024], date(2024, 6, 1))
    split = real_siding_age_score(parcel, as_of_year=_AS_OF, permit_class_split=True)
    only_old_siding = real_siding_age_score(_old_wood_house([older_siding], date(2000, 1, 1)), as_of_year=_AS_OF)
    assert split == pytest.approx(only_old_siding)


def test_rows_without_a_permit_history_list_fall_back_to_the_legacy_date() -> None:
    parcel = {"permit_data_available": True, "exterior_wall_1": "Clapboards", "year_built": 1900,
              "most_recent_exterior_permit_date": date(2024, 6, 1)}
    assert real_siding_age_score(parcel, as_of_year=_AS_OF, permit_class_split=True) == real_siding_age_score(
        parcel, as_of_year=_AS_OF
    )


def test_the_split_still_respects_the_short_permit_window_fallback() -> None:
    parcel = _old_wood_house([_ROOF_2024], date(2024, 6, 1), permit_history_since=date(2023, 6, 8))
    # no siding permit on file, window under 20 years: unknown, scored from the proxy (not "never redone")
    from extscorer.scoring.basic import siding_age_score

    assert real_siding_age_score(parcel, as_of_year=_AS_OF, permit_class_split=True) == siding_age_score(parcel)


def test_willingness_to_spend_counts_recent_other_exterior_permits_and_caps_at_one() -> None:
    def win(y: int) -> dict:
        return {"permit_type": "Building", "reason": "replace windows", "date_opened": f"01/01/{y}"}

    assert willingness_to_spend_score({"permit_history": []}, _AS_OF) == 0.0
    assert willingness_to_spend_score({}, _AS_OF) == 0.0
    assert willingness_to_spend_score({"permit_history": [win(2022)]}, _AS_OF) == pytest.approx(1 / 3)
    assert willingness_to_spend_score({"permit_history": [win(2020), win(2021), win(2022), win(2023)]}, _AS_OF) == 1.0
    assert willingness_to_spend_score({"permit_history": [win(2005)]}, _AS_OF) == 0.0  # outside the 15-year lookback
    # a roof or siding permit is a reset, not "other exterior"
    assert willingness_to_spend_score({"permit_history": [_ROOF_2024, _SIDING_2024]}, _AS_OF) == 0.0


def _scoreable(history: list[dict], **extra) -> dict:
    return {
        "parcel_id": "1", "town": "T", "address": "1 TEST RD", "year_built": 1900, "living_area_sqft": 1500,
        "exterior_wall_1": "Clapboards", "permit_data_available": True, "permit_history": history,
        "most_recent_exterior_permit_date": None, **extra,
    }


def test_the_spend_bonus_only_adds_is_off_by_default_and_is_capped_at_one() -> None:
    window = {"permit_type": "Building", "reason": "replace windows", "date_opened": "01/01/2023"}
    with_permit, without = _scoreable([window] * 3), _scoreable([])
    base = score_property(with_permit, as_of_year=_AS_OF).score
    assert score_property(with_permit, as_of_year=_AS_OF, spend_bonus=0.0).score == base  # off by default
    boosted = score_property(with_permit, as_of_year=_AS_OF, spend_bonus=0.03).score
    assert boosted == pytest.approx(min(1.0, base + 0.03))
    # a parcel with no such permit is never marked down
    assert score_property(without, as_of_year=_AS_OF, spend_bonus=0.03).score == score_property(without, as_of_year=_AS_OF).score
    assert score_property(with_permit, as_of_year=_AS_OF, spend_bonus=5.0).score <= 1.0


def test_rank_candidates_passes_the_switches_through() -> None:
    reroofed = _scoreable([_ROOF_2024], most_recent_exterior_permit_date=date(2024, 6, 1), parcel_id="roofed")
    never = _scoreable([], parcel_id="never")
    legacy = [lead.parcel_id for lead in rank_candidates([reroofed, never], as_of_year=_AS_OF)]
    split = rank_candidates([reroofed, never], as_of_year=_AS_OF, permit_class_split=True)
    assert legacy[0] == "never"  # legacy: the re-roofed house drops to the bottom
    assert abs(split[0].score - split[1].score) < 1e-9  # split: a roof does not touch the siding age


def test_no_siding_permit_means_the_proxy_whatever_the_permit_window() -> None:
    # A deep (28-year) window used to read "no permit" as "never redone since built". Re-siding is mostly
    # unpermitted, so with the class split absence is weak evidence and the material proxy decides.
    deep = _old_wood_house([_ROOF_2024], date(2024, 6, 1), permit_history_since=date(1998, 4, 2))
    assert real_siding_age_score(deep, as_of_year=_AS_OF, permit_class_split=True) == siding_age_score(deep)
    no_permits = _old_wood_house([], None, permit_history_since=date(1998, 4, 2))
    assert real_siding_age_score(no_permits, as_of_year=_AS_OF, permit_class_split=True) == siding_age_score(no_permits)
    # ...while the legacy score (split off) still reads absence as "never redone" for a deep window
    assert real_siding_age_score(no_permits, as_of_year=_AS_OF) != siding_age_score(no_permits)


def test_an_old_vinyl_house_with_only_a_roof_permit_gets_the_proxys_low_score() -> None:
    # The proxy assumes old vinyl was probably already replaced, so a roof-only history does not make it a
    # "never redone" lead the way an absent history used to.
    vinyl = _old_wood_house([_ROOF_2024], date(2024, 6, 1), exterior_wall_1="Vinyl Siding")
    assert real_siding_age_score(vinyl, as_of_year=_AS_OF, permit_class_split=True) == siding_age_score(vinyl)
    assert siding_age_score(vinyl) < 0.3


def test_a_siding_permit_still_resets_the_age_with_a_deep_window() -> None:
    parcel = _old_wood_house([_SIDING_2024], date(2024, 6, 1), permit_history_since=date(1998, 4, 2))
    assert real_siding_age_score(parcel, as_of_year=_AS_OF, permit_class_split=True) < 0.2
