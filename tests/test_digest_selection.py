from __future__ import annotations

from extscorer.digest.selection import DEFAULT_LEADS_PER_DIGEST, is_likely_unreachable_owner, select_unsent_leads


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
