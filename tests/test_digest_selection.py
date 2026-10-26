from __future__ import annotations

from extscorer.digest.selection import (
    DEFAULT_LEADS_PER_DIGEST,
    filter_sold_territory,
    is_likely_unreachable_owner,
    select_new_leads_for_pipeline,
    select_unsent_leads,
)


class _FakeLead:
    def __init__(self, parcel_id: str) -> None:
        self.parcel_id = parcel_id


def test_selects_top_n_leads_in_ranked_order() -> None:
    pairs = [
        (_FakeLead("A"), {"id": "row-a"}),
        (_FakeLead("B"), {"id": "row-b"}),
        (_FakeLead("C"), {"id": "row-c"}),
    ]
    selected = select_unsent_leads(pairs, already_sent_parcel_row_ids=set(), limit=2)
    assert [p["id"] for _, p in selected] == ["row-a", "row-b"]


def test_skips_already_sent_parcels() -> None:
    pairs = [
        (_FakeLead("A"), {"id": "row-a"}),
        (_FakeLead("B"), {"id": "row-b"}),
        (_FakeLead("C"), {"id": "row-c"}),
    ]
    selected = select_unsent_leads(pairs, already_sent_parcel_row_ids={"row-a"}, limit=2)
    assert [p["id"] for _, p in selected] == ["row-b", "row-c"]


def test_returns_fewer_than_limit_if_not_enough_unsent_leads_remain() -> None:
    pairs = [(_FakeLead("A"), {"id": "row-a"}), (_FakeLead("B"), {"id": "row-b"})]
    selected = select_unsent_leads(pairs, already_sent_parcel_row_ids={"row-a"}, limit=10)
    assert len(selected) == 1


def test_returns_empty_when_everything_already_sent() -> None:
    pairs = [(_FakeLead("A"), {"id": "row-a"})]
    selected = select_unsent_leads(pairs, already_sent_parcel_row_ids={"row-a"}, limit=10)
    assert selected == []


def test_default_leads_per_digest_is_twenty() -> None:
    # Widened from 10 to 20 (2026-09-15, Prompt U) now that likely-
    # vacant/absentee-owned properties are excluded from candidacy.
    assert DEFAULT_LEADS_PER_DIGEST == 20


def test_is_likely_unreachable_owner_true_for_absentee_owner() -> None:
    assert is_likely_unreachable_owner({"is_absentee_owner": True}) is True


def test_is_likely_unreachable_owner_true_for_tax_delinquency() -> None:
    assert is_likely_unreachable_owner({"has_tax_delinquency": True}) is True


def test_is_likely_unreachable_owner_false_when_neither_signal_present() -> None:
    # Unknown/absent must not be treated as confirmed vacant -- an older
    # row from before this signal existed, or one not yet enriched.
    assert is_likely_unreachable_owner({}) is False
    assert is_likely_unreachable_owner({"is_absentee_owner": False, "has_tax_delinquency": False}) is False


def test_select_unsent_leads_excludes_likely_unreachable_owners() -> None:
    pairs = [
        (_FakeLead("A"), {"id": "row-a", "is_absentee_owner": True}),
        (_FakeLead("B"), {"id": "row-b", "has_tax_delinquency": True}),
        (_FakeLead("C"), {"id": "row-c"}),
    ]
    selected = select_unsent_leads(pairs, already_sent_parcel_row_ids=set(), limit=10)
    assert [p["id"] for _, p in selected] == ["row-c"]


def test_select_unsent_leads_excluded_owner_does_not_count_against_limit() -> None:
    # An excluded parcel must not consume a limit slot -- the next real
    # candidate should still make it in.
    pairs = [
        (_FakeLead("A"), {"id": "row-a", "is_absentee_owner": True}),
        (_FakeLead("B"), {"id": "row-b"}),
    ]
    selected = select_unsent_leads(pairs, already_sent_parcel_row_ids=set(), limit=1)
    assert [p["id"] for _, p in selected] == ["row-b"]


def test_select_unsent_leads_returns_empty_for_zero_limit() -> None:
    # A naive "append then check len >= limit" loop still appends one
    # lead before its break check fires on limit=0 -- must short-circuit
    # before the loop instead.
    pairs = [(_FakeLead("A"), {"id": "row-a"})]
    selected = select_unsent_leads(pairs, already_sent_parcel_row_ids=set(), limit=0)
    assert selected == []


# --- select_new_leads_for_pipeline (Prompt V: lead_pipeline replaces lead_digest_sends as the dedup source) ---


def _pipeline_parcel(parcel_id: str, town: str = "Canterbury", **extra: object) -> dict[str, object]:
    return {"id": f"row-{parcel_id}", "town": town, "parcel_id": parcel_id, **extra}


def test_select_new_leads_for_pipeline_selects_top_n_in_ranked_order() -> None:
    pairs = [
        (_FakeLead("A"), _pipeline_parcel("A")),
        (_FakeLead("B"), _pipeline_parcel("B")),
        (_FakeLead("C"), _pipeline_parcel("C")),
    ]
    selected = select_new_leads_for_pipeline(pairs, existing_pipeline_lead_keys=set(), limit=2)
    assert [p["id"] for _, p in selected] == ["row-A", "row-B"]


def test_select_new_leads_for_pipeline_skips_any_lead_key_already_in_pipeline() -> None:
    pairs = [
        (_FakeLead("A"), _pipeline_parcel("A")),
        (_FakeLead("B"), _pipeline_parcel("B")),
    ]
    # "Canterbury:A" already in lead_pipeline -- skipped regardless of what
    # status it might carry there (this function never reads status).
    selected = select_new_leads_for_pipeline(pairs, existing_pipeline_lead_keys={"Canterbury:A"}, limit=10)
    assert [p["id"] for _, p in selected] == ["row-B"]


def test_select_new_leads_for_pipeline_keys_are_town_scoped() -> None:
    # A lead_key already in the pipeline for a DIFFERENT town must not
    # suppress a same-parcel_id lead in this town.
    pairs = [(_FakeLead("A"), _pipeline_parcel("A", town="Pomfret"))]
    selected = select_new_leads_for_pipeline(pairs, existing_pipeline_lead_keys={"Canterbury:A"}, limit=10)
    assert len(selected) == 1


def test_select_new_leads_for_pipeline_excludes_likely_unreachable_owners() -> None:
    pairs = [
        (_FakeLead("A"), _pipeline_parcel("A", is_absentee_owner=True)),
        (_FakeLead("B"), _pipeline_parcel("B")),
    ]
    selected = select_new_leads_for_pipeline(pairs, existing_pipeline_lead_keys=set(), limit=10)
    assert [p["id"] for _, p in selected] == ["row-B"]


def test_select_new_leads_for_pipeline_returns_empty_when_everything_already_in_pipeline() -> None:
    pairs = [(_FakeLead("A"), _pipeline_parcel("A"))]
    selected = select_new_leads_for_pipeline(pairs, existing_pipeline_lead_keys={"Canterbury:A"}, limit=10)
    assert selected == []


def test_select_new_leads_for_pipeline_returns_empty_for_zero_limit() -> None:
    # The backlog-cap feature (Tool 4) legitimately calls this with
    # limit=0 whenever the open-"new" backlog is already full.
    pairs = [(_FakeLead("A"), _pipeline_parcel("A"))]
    selected = select_new_leads_for_pipeline(pairs, existing_pipeline_lead_keys=set(), limit=0)
    assert selected == []


def test_filter_sold_territory_none_is_no_restriction() -> None:
    parcels = [{"town": "Canterbury"}, {"town": "Windham"}]
    assert filter_sold_territory(parcels, None) == parcels


def test_filter_sold_territory_excludes_unsold_town() -> None:
    parcels = [{"id": "a", "town": "Canterbury"}, {"id": "b", "town": "Windham"}]
    result = filter_sold_territory(parcels, ["Canterbury", "Pomfret"])
    assert [p["id"] for p in result] == ["a"]


def test_filter_sold_territory_is_case_insensitive() -> None:
    parcels = [{"id": "a", "town": "Windham"}]
    assert filter_sold_territory(parcels, ["windham"]) == parcels
    assert filter_sold_territory(parcels, ["WINDHAM"]) == parcels


def test_filter_sold_territory_empty_list_excludes_everyone() -> None:
    parcels = [{"town": "Canterbury"}]
    assert filter_sold_territory(parcels, []) == []
